"""
MaakavStocks - Local server + Yahoo Finance proxy
Run: python server.py
"""
from http.server import HTTPServer, SimpleHTTPRequestHandler
from concurrent.futures import ThreadPoolExecutor, as_completed
import urllib.request
import urllib.parse
import json
import os
import sys
import datetime
import calendar

# Load .env if present (local development)
_env_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), '.env')
if os.path.exists(_env_file):
    with open(_env_file) as _f:
        for _line in _f:
            _line = _line.strip()
            if _line and not _line.startswith('#') and '=' in _line:
                _k, _v = _line.split('=', 1)
                os.environ.setdefault(_k.strip(), _v.strip())

PORT = int(os.environ.get('PORT', 3000))
OPENAI_API_KEY = os.environ.get('OPENAI_API_KEY', '')
print(f"[init] OPENAI_API_KEY {'SET (' + OPENAI_API_KEY[:8] + '...)' if OPENAI_API_KEY else 'NOT SET'}", file=sys.stderr)
YAHOO_BASE = 'https://query2.finance.yahoo.com/v8/finance/chart/'
HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Accept': 'application/json',
    'Accept-Language': 'en-US,en;q=0.9',
}

MARKET_SYMBOLS = ["QQQ", "SPY", "DIA", "IWM", "BTC-USD", "ETH-USD", "TA35.TA", "TA90.TA", "EURILS=X"]

def fetch_quote(symbol):
    """Fetch real-time quote + daily change + pre/after-hours price."""
    base = "https://query1.finance.yahoo.com/v8/finance/chart/"

    # 1. Daily bars (5d) — accurate previous close even after holidays
    url_d = base + symbol + "?interval=1d&range=5d"
    req = urllib.request.Request(url_d, headers=HEADERS)
    with urllib.request.urlopen(req, timeout=12) as r:
        data_d = json.loads(r.read())
    res_d    = data_d["chart"]["result"][0]
    meta     = res_d["meta"]
    price    = meta.get("regularMarketPrice")
    reg_time = meta.get("regularMarketTime") or 0
    name     = meta.get("longName") or meta.get("shortName") or symbol
    currency = meta.get("currency") or ""

    # Previous close: try meta fields first (reliable for forex), fallback to daily bars
    prev = (meta.get("regularMarketPreviousClose")
            or meta.get("previousClose")
            or meta.get("chartPreviousClose"))
    if prev is None:
        closes_d = res_d["indicators"]["quote"][0].get("close", [])
        valid_d  = [c for c in closes_d if c is not None]
        prev = valid_d[-2] if len(valid_d) >= 2 else None
    change_pct = ((price - prev) / prev * 100) if (price and prev) else None

    # 2. 1m intraday — pre/after-market detection
    pre_price  = None
    pre_change = None
    try:
        url_m = base + symbol + "?interval=1m&range=1d&includePrePost=true"
        req2 = urllib.request.Request(url_m, headers=HEADERS)
        with urllib.request.urlopen(req2, timeout=10) as r2:
            data_m = json.loads(r2.read())
        res_m      = data_m["chart"]["result"][0]
        timestamps = res_m.get("timestamp", [])
        closes_m   = res_m["indicators"]["quote"][0].get("close", [])
        for t, c in reversed(list(zip(timestamps, closes_m))):
            if t > reg_time and c is not None:
                pre_price  = c
                pre_change = ((pre_price - price) / price * 100) if price else None
                break
    except Exception:
        pass  # pre-market optional

    return {
        "symbol":    symbol,
        "name":      name,
        "currency":  currency,
        "price":     price,
        "change":    change_pct,
        "time":      reg_time,
        "prePrice":  pre_price,
        "preChange": pre_change,
    }

def _fetch_nasdaq_day(args):
    """Fetch one day from Nasdaq earnings calendar."""
    i, d, symbols_set = args
    HDRS = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            'Accept': 'application/json,text/plain,*/*'}
    url = f"https://api.nasdaq.com/api/calendar/earnings?date={d}"
    req = urllib.request.Request(url, headers=HDRS)
    matches = {}
    try:
        with urllib.request.urlopen(req, timeout=6) as r:
            data = json.loads(r.read())
        rows = data.get("data", {}).get("rows") or []
        for row in rows:
            sym = row.get("symbol", "")
            if sym in symbols_set:
                matches[sym] = {
                    "earningsDate":   int(datetime.datetime.combine(d, datetime.time()).timestamp()),
                    "daysToEarnings": i,
                    "earningsTime":   row.get("time", ""),
                }
    except Exception:
        pass
    return matches


def fetch_nasdaq_earnings(symbols_set, days_ahead=21):
    """Fetch earnings dates from Nasdaq calendar — parallel requests."""
    today = datetime.date.today()
    days = [(i, today + datetime.timedelta(days=i), symbols_set) for i in range(days_ahead)]
    result = {}
    try:
        with ThreadPoolExecutor(max_workers=8) as ex:
            for matches in ex.map(_fetch_nasdaq_day, days, timeout=18):
                for sym, val in matches.items():
                    if sym not in result:
                        result[sym] = val
    except Exception as e:
        print(f"[nasdaq] earnings fetch error: {e}", file=sys.stderr)
    return result


def fetch_research(symbol):
    """Fetch research data for a US stock: MA150, earnings date (Yahoo), news."""
    base2 = "https://query2.finance.yahoo.com"
    now_ts = int(datetime.datetime.utcnow().timestamp())
    today  = datetime.date.today()

    result = {"symbol": symbol, "ma150": None, "price": None, "aboveMa150": None,
               "ma150Pct": None, "earningsDate": None, "daysToEarnings": None,
               "earningsTime": None, "news": []}

    # 1. 1-year daily history → MA150 + earnings from chart meta
    try:
        url = "https://query1.finance.yahoo.com/v8/finance/chart/" + symbol + "?interval=1d&range=1y"
        req = urllib.request.Request(url, headers=HEADERS)
        with urllib.request.urlopen(req, timeout=12) as r:
            data = json.loads(r.read())
        res  = data["chart"]["result"][0]
        meta = res["meta"]
        closes = [c for c in res["indicators"]["quote"][0].get("close", []) if c is not None]
        price = meta.get("regularMarketPrice")
        result["price"] = price
        if len(closes) >= 150:
            ma150 = sum(closes[-150:]) / 150
            result["ma150"] = round(ma150, 4)
            if price:
                result["aboveMa150"] = price > ma150
                result["ma150Pct"]   = round((price - ma150) / ma150 * 100, 2)
    except Exception as e:
        print(f"[research] chart error {symbol}: {e}", file=sys.stderr)

    # 2. News headlines (last 48h)
    try:
        url = base2 + "/v1/finance/search?q=" + urllib.parse.quote(symbol) + "&newsCount=5&enableFuzzyQuery=false&quotesCount=0"
        req = urllib.request.Request(url, headers=HEADERS)
        with urllib.request.urlopen(req, timeout=10) as r:
            data = json.loads(r.read())
        news_items = data.get("news", [])
        cutoff_news = now_ts - 48 * 3600
        result["news"] = [
            {"title": n.get("title", ""), "publishTime": n.get("providerPublishTime")}
            for n in news_items
            if n.get("providerPublishTime", 0) >= cutoff_news
        ][:3]
    except Exception:
        pass

    return result


def ask_openai(symbol, research):
    """Send research data to OpenAI and get Hebrew summary."""
    if not OPENAI_API_KEY:
        raise ValueError("no_key")
    news_str = ' | '.join(n['title'] for n in research.get('news', [])[:3]) or 'אין חדשות'
    earn_str = f"בעוד {research['daysToEarnings']} ימים" if research.get('daysToEarnings') is not None else 'לא ידוע'
    ma_pct   = research.get('ma150Pct', 0) or 0
    ma_dir   = 'מעל' if research.get('aboveMa150') else 'מתחת'
    ma_str   = f"{ma_dir} MA150 ב-{ma_pct:.1f}%" if research.get('ma150') else 'לא זמין'

    prompt = (
        f"אתה אנליסט מניות. סכם בעברית בקצרה (3-4 שורות) את מצב המניה {symbol}:\n"
        f"- מחיר: {research.get('price','?')}, {ma_str}\n"
        f"- דוח רווחים: {earn_str}\n"
        f"- חדשות אחרונות: {news_str}\n"
        f"מה כדאי לשים לב? היה ממוקד ומעשי."
    )
    payload = json.dumps({
        "model": "gpt-4o-mini",
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": 220,
        "temperature": 0.4,
    }).encode('utf-8')
    req = urllib.request.Request(
        'https://api.openai.com/v1/chat/completions',
        data=payload,
        headers={'Authorization': f'Bearer {OPENAI_API_KEY}', 'Content-Type': 'application/json'},
        method='POST'
    )
    with urllib.request.urlopen(req, timeout=20) as r:
        resp = json.loads(r.read())
    return resp['choices'][0]['message']['content'].strip()


class Handler(SimpleHTTPRequestHandler):
    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)

        # Market chart (YTD) — must come BEFORE /proxy/market
        if parsed.path.startswith('/proxy/market/chart'):
            params = {}
            if '?' in self.path:
                qs = self.path.split('?', 1)[1]
                for part in qs.split('&'):
                    if '=' in part:
                        k, v = part.split('=', 1)
                        params[k] = urllib.parse.unquote(v)
            symbol = params.get('symbol', '')
            if not symbol:
                self.send_error(400, 'Missing symbol')
                return
            try:
                url = ('https://query1.finance.yahoo.com/v8/finance/chart/'
                       + symbol + '?interval=1d&range=ytd&includePrePost=false')
                req = urllib.request.Request(url, headers=HEADERS)
                with urllib.request.urlopen(req, timeout=10) as r:
                    data = json.loads(r.read())
                res = data['chart']['result'][0]
                timestamps = res.get('timestamp', [])
                closes = res['indicators']['quote'][0].get('close', [])
                pairs = [(t, c) for t, c in zip(timestamps, closes) if c is not None]
                meta = res.get('meta', {})
                prev_close = meta.get('previousClose') or meta.get('chartPreviousClose')
                body = json.dumps({
                    'timestamps': [p[0] for p in pairs],
                    'closes':     [p[1] for p in pairs],
                    'prevClose':  prev_close,
                }, ensure_ascii=False).encode('utf-8')
                self.send_response(200)
                self.send_header('Content-Type', 'application/json; charset=utf-8')
                self.send_header('Access-Control-Allow-Origin', '*')
                self.send_header('Content-Length', str(len(body)))
                self.end_headers()
                self.wfile.write(body)
            except Exception as e:
                self.send_error(502, 'Chart error: ' + str(e))
            return

        # AI summary for multiple symbols (bulk) — must come BEFORE single
        if parsed.path.startswith('/proxy/ai-summary-bulk'):
            params = dict(urllib.parse.parse_qsl(parsed.query))
            symbols_str = params.get('symbols', '')
            symbols = [s.strip() for s in symbols_str.split(',') if s.strip()]
            if not symbols:
                self.send_error(400, 'Missing symbols')
                return
            if not OPENAI_API_KEY:
                body = json.dumps({"error": "no_key"}).encode()
                self.send_response(200)
                self.send_header('Content-Type', 'application/json')
                self.send_header('Access-Control-Allow-Origin', '*')
                self.end_headers()
                self.wfile.write(body)
                return
            try:
                # Fetch research for all in parallel
                research_map = {}
                with ThreadPoolExecutor(max_workers=min(len(symbols), 8)) as ex:
                    futures = {ex.submit(fetch_research, sym): sym for sym in symbols}
                    for fut in as_completed(futures, timeout=30):
                        sym = futures[fut]
                        try:
                            research_map[sym] = fut.result()
                        except Exception:
                            research_map[sym] = {'symbol': sym}
                # Call OpenAI for each symbol (sequential — avoids rate limits)
                results = []
                for sym in symbols:
                    try:
                        summary = ask_openai(sym, research_map.get(sym, {}))
                        results.append({'symbol': sym, 'summary': summary})
                    except Exception as e:
                        results.append({'symbol': sym, 'error': str(e)})
                body = json.dumps(results, ensure_ascii=False).encode('utf-8')
                self.send_response(200)
                self.send_header('Content-Type', 'application/json; charset=utf-8')
                self.send_header('Access-Control-Allow-Origin', '*')
                self.send_header('Content-Length', str(len(body)))
                self.end_headers()
                self.wfile.write(body)
            except Exception as e:
                self.send_error(502, 'Bulk AI error: ' + str(e))
            return

        # AI summary for a single symbol
        if parsed.path.startswith('/proxy/ai-summary'):
            params = dict(urllib.parse.parse_qsl(parsed.query))
            symbol = params.get('symbol', '').strip()
            if not symbol:
                self.send_error(400, 'Missing symbol')
                return
            try:
                research = fetch_research(symbol)
                summary = ask_openai(symbol, research)
                body = json.dumps({"symbol": symbol, "summary": summary}, ensure_ascii=False).encode('utf-8')
                self.send_response(200)
                self.send_header('Content-Type', 'application/json; charset=utf-8')
                self.send_header('Access-Control-Allow-Origin', '*')
                self.send_header('Content-Length', str(len(body)))
                self.end_headers()
                self.wfile.write(body)
            except ValueError as e:
                if 'no_key' in str(e):
                    body = json.dumps({"error": "no_key"}).encode()
                    self.send_response(200)
                    self.send_header('Content-Type', 'application/json')
                    self.send_header('Access-Control-Allow-Origin', '*')
                    self.end_headers()
                    self.wfile.write(body)
                else:
                    self.send_error(502, str(e))
            except Exception as e:
                self.send_error(502, 'AI error: ' + str(e))
            return

        # Research data — MA150, earnings (Nasdaq), news for US stocks
        if parsed.path.startswith('/proxy/research'):
            params = dict(urllib.parse.parse_qsl(parsed.query))
            symbols_str = params.get('symbols', '')
            symbols = [s.strip() for s in symbols_str.split(',') if s.strip()]
            if not symbols:
                self.send_error(400, 'Missing symbols')
                return
            try:
                # Fetch MA150 + news per symbol in parallel
                research_map = {}
                with ThreadPoolExecutor(max_workers=min(len(symbols), 8)) as ex:
                    futures = {ex.submit(fetch_research, sym): sym for sym in symbols}
                    for fut in as_completed(futures, timeout=25):
                        sym = futures[fut]
                        try:
                            research_map[sym] = fut.result()
                        except Exception:
                            research_map[sym] = {"symbol": sym}
                # Fetch earnings from Nasdaq calendar once for all symbols
                earn_map = fetch_nasdaq_earnings(set(symbols))
                for sym, earn_data in earn_map.items():
                    if sym in research_map:
                        research_map[sym].update(earn_data)
                result = [research_map[sym] for sym in symbols if sym in research_map]
                body = json.dumps(result, ensure_ascii=False).encode('utf-8')
                self.send_response(200)
                self.send_header('Content-Type', 'application/json; charset=utf-8')
                self.send_header('Access-Control-Allow-Origin', '*')
                self.send_header('Content-Length', str(len(body)))
                self.end_headers()
                self.wfile.write(body)
            except Exception as e:
                self.send_error(502, 'Research proxy error: ' + str(e))
            return

        # Quotes for arbitrary symbols — used by watchlist
        if parsed.path.startswith('/proxy/quotes'):
            params = dict(urllib.parse.parse_qsl(parsed.query))
            symbols_str = params.get('symbols', '')
            symbols = [s.strip() for s in symbols_str.split(',') if s.strip()]
            if not symbols:
                self.send_error(400, 'Missing symbols')
                return
            try:
                quotes_map = {}
                with ThreadPoolExecutor(max_workers=min(len(symbols), 10)) as ex:
                    futures = {ex.submit(fetch_quote, sym): sym for sym in symbols}
                    for fut in as_completed(futures, timeout=20):
                        sym = futures[fut]
                        try:
                            quotes_map[sym] = fut.result()
                        except Exception:
                            quotes_map[sym] = {'symbol': sym, 'name': sym, 'currency': '',
                                               'price': None, 'change': None, 'time': None,
                                               'prePrice': None, 'preChange': None}
                result = [quotes_map[sym] for sym in symbols if sym in quotes_map]
                body = json.dumps(result, ensure_ascii=False).encode('utf-8')
                self.send_response(200)
                self.send_header('Content-Type', 'application/json; charset=utf-8')
                self.send_header('Access-Control-Allow-Origin', '*')
                self.send_header('Content-Length', str(len(body)))
                self.end_headers()
                self.wfile.write(body)
            except Exception as e:
                self.send_error(502, 'Quotes proxy error: ' + str(e))
            return

        # Market quotes — all symbols in parallel
        if parsed.path.startswith('/proxy/market'):
            try:
                quotes_map = {}
                with ThreadPoolExecutor(max_workers=len(MARKET_SYMBOLS)) as ex:
                    futures = {ex.submit(fetch_quote, sym): sym for sym in MARKET_SYMBOLS}
                    for fut in as_completed(futures, timeout=12):
                        sym = futures[fut]
                        try:
                            quotes_map[sym] = fut.result()
                        except Exception:
                            quotes_map[sym] = {'symbol': sym, 'price': None, 'change': None,
                                               'time': None, 'prePrice': None, 'preChange': None}
                result = [quotes_map[sym] for sym in MARKET_SYMBOLS if sym in quotes_map]
                body = json.dumps(result, ensure_ascii=False).encode('utf-8')
                self.send_response(200)
                self.send_header('Content-Type', 'application/json; charset=utf-8')
                self.send_header('Access-Control-Allow-Origin', '*')
                self.send_header('Content-Length', str(len(body)))
                self.end_headers()
                self.wfile.write(body)
            except Exception as e:
                self.send_error(502, 'Market proxy error: ' + str(e))
            return

        if parsed.path.startswith('/api/chart/'):
            # Extract symbol (everything after /api/chart/)
            symbol = parsed.path[len('/api/chart/'):]
            symbol = urllib.parse.unquote(symbol)
            qs = parsed.query or 'interval=1d&range=ytd'
            yahoo_url = YAHOO_BASE + urllib.parse.quote(symbol) + '?' + qs

            try:
                req = urllib.request.Request(yahoo_url, headers=HEADERS)
                with urllib.request.urlopen(req, timeout=12) as resp:
                    data = resp.read()
                self.send_response(200)
                self.send_header('Content-Type', 'application/json')
                self.send_header('Access-Control-Allow-Origin', '*')
                self.end_headers()
                self.wfile.write(data)
            except ConnectionAbortedError:
                pass  # client disconnected (timeout/abort) — not an error
            except Exception as e:
                try:
                    self.send_response(502)
                    self.send_header('Content-Type', 'application/json')
                    self.send_header('Access-Control-Allow-Origin', '*')
                    self.end_headers()
                    self.wfile.write(json.dumps({'error': str(e)}).encode())
                except ConnectionAbortedError:
                    pass
        else:
            super().do_GET()

    def end_headers(self):
        # No-cache for HTML/JS/CSS and root path so browser always gets latest version
        p = self.path.split('?')[0]
        if p in ('/', '') or p.endswith(('.html', '.js', '.css')):
            self.send_header('Cache-Control', 'no-store, no-cache, must-revalidate')
            self.send_header('Pragma', 'no-cache')
            self.send_header('Expires', '0')
        super().end_headers()

    def log_message(self, fmt, *args):
        # Only log API calls, not static files
        path = args[0] if args else ''
        if '/api/' in path or '/proxy/' in path:
            print(f'  → {path} {args[1] if len(args) > 1 else ""}')

    def log_error(self, fmt, *args):
        pass  # suppress default error output

if __name__ == '__main__':
    os.chdir(os.path.dirname(os.path.abspath(__file__)))
    print('=' * 40)
    print('  MaakavStocks - שרת מקומי')
    print('=' * 40)
    print(f'  http://localhost:{PORT}')
    print('  Ctrl+C לעצירה')
    print('=' * 40)
    try:
        HTTPServer(('', PORT), Handler).serve_forever()
    except KeyboardInterrupt:
        print('\nServer stopped.')
