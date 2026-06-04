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
import time

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

# S&P 500 constituents (Yahoo Finance symbols) — used for ATH scan
_SP500_FALLBACK = [
    "A","AAPL","ABBV","ACGL","ACN","ADBE","ADI","ADP","ADSK","AEE","AEP","AES","AFL","AIG","AIZ","AJG",
    "AKAM","ALB","ALGN","ALL","ALLE","AMAT","AMCR","AMD","AME","AMGN","AMP","AMT","AMZN","ANET","ANSS",
    "AON","AOS","APA","APD","APH","APTV","ARE","ATO","AVB","AVGO","AVY","AWK","AXON","AXP","AZO",
    "BA","BAC","BALL","BAX","BBWI","BBY","BDX","BEN","BG","BIO","BIIB","BK","BKNG","BKR","BLK",
    "BMY","BR","BRK-B","BSX","BWA","BX","BXP",
    "C","CAG","CAH","CARR","CAT","CB","CBOE","CBRE","CCI","CCL","CDNS","CDW","CE","CEG","CF","CFG",
    "CHD","CHRW","CHTR","CI","CINF","CL","CLX","CMA","CMCSA","CME","CMG","CMI","CMS","CNC","CNP",
    "COF","COO","COP","COR","COST","CPAY","CPB","CPT","CRL","CRM","CSCO","CSGP","CSX","CTAS","CTLT",
    "CTSH","CTVA","CVS","CVX","CZR",
    "D","DAL","DAY","DD","DE","DECK","DFS","DG","DGX","DHI","DHR","DIS","DLTR","DOC","DOV","DOW",
    "DPZ","DRI","DTE","DUK","DVA","DVN","DXCM",
    "EA","EBAY","ECL","ED","EFX","EG","EIX","EL","ELV","EMN","EMR","ENPH","EOG","EPAM","EQIX",
    "EQR","EQT","ES","ESS","ETN","ETR","ETSY","EVRG","EW","EXC","EXPD","EXPE","EXR",
    "F","FANG","FAST","FCX","FDS","FDX","FE","FFIV","FI","FICO","FIS","FITB","FMC","FOX","FOXA",
    "FRT","FSLR","FTV",
    "GD","GE","GEHC","GEN","GILD","GIS","GL","GLW","GM","GNRC","GOOG","GOOGL","GPC","GPN","GRMN",
    "GS","GWW",
    "HAL","HAS","HBAN","HD","HES","HIG","HII","HLT","HON","HPE","HPQ","HRL","HSIC","HST",
    "HSY","HUBB","HUM","HWM",
    "IBM","ICE","IDXX","IEX","IFF","ILMN","INCY","INTC","INTU","INVH","IP","IPG","IQV","IR","IRM",
    "ISRG","IT","ITW","IVZ",
    "J","JBHT","JCI","JKHY","JNJ","JNPR","JPM",
    "K","KDP","KEY","KEYS","KHC","KIM","KLAC","KMB","KMI","KMX","KO","KR",
    "L","LDOS","LEN","LH","LHX","LIN","LKQ","LLY","LMT","LNT","LOW","LRCX","LUV","LVS","LW",
    "LYB","LYV",
    "MA","MAA","MAR","MAS","MCD","MCHP","MCK","MCO","MDLZ","MDT","MET","META","MGM","MHK","MKC",
    "MKTX","MLM","MMC","MMM","MNST","MO","MOH","MOS","MPC","MPWR","MRK","MRO","MS","MSCI","MSFT",
    "MSI","MTB","MTCH","MTD","MU",
    "NCLH","NDAQ","NEE","NEM","NFLX","NI","NKE","NOC","NOW","NRG","NSC","NTAP","NTRS","NUE","NVDA",
    "NVR","NWS","NWSA","NXPI",
    "O","ODFL","OKE","OMC","ON","ORCL","ORLY","OTIS","OXY",
    "PARA","PAYC","PAYX","PCAR","PCG","PEG","PEP","PFE","PFG","PG","PGR","PH","PHM","PKG","PLTR",
    "PLD","PM","PNC","POOL","PPG","PPL","PRU","PSA","PSX","PTC","PVH","PWR","PYPL",
    "QCOM","QRVO",
    "RCL","REG","REGN","RF","RHI","RJF","RL","RMD","ROK","ROL","ROP","ROST","RSG","RTX",
    "SBAC","SBUX","SCHW","SHW","SJM","SLB","SMCI","SNA","SNPS","SO","SPG","SPGI","SRE","STE",
    "STLD","STT","STX","STZ","SWK","SYF","SYK","SYY",
    "T","TAP","TDG","TDY","TECH","TEL","TER","TFC","TFX","TGT","TJX","TMO","TMUS","TPR","TRGP",
    "TRMB","TROW","TRV","TSCO","TSLA","TSN","TT","TTWO","TXN","TXT","TYL",
    "UAL","UDR","UHS","ULTA","UNH","UNP","UPS","URI","USB",
    "V","VFC","VICI","VLO","VMC","VNO","VRSK","VRSN","VRTX","VTR","VZ",
    "WAB","WAT","WBA","WBD","WDC","WEC","WELL","WFC","WHR","WM","WMB","WMT","WRB","WRK","WST",
    "WTW","WY","WYNN",
    "XEL","XOM","XRAY","XYL",
    "YUM",
    "ZBH","ZBRA","ZION","ZTS",
]

_sp500_ath_cache      = None
_sp500_ath_cache_time = 0.0
SP500_ATH_CACHE_TTL   = 7200   # 2 hours

_SP500_CACHE_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'sp500_symbols_cache.json')
_SP500_CACHE_DAYS = 90  # refresh every 3 months

def _load_sp500_symbols():
    """Return S&P 500 symbols: from 3-month cache if fresh, else fetch Wikipedia, else fallback."""
    # Try cache
    if os.path.exists(_SP500_CACHE_FILE):
        try:
            with open(_SP500_CACHE_FILE, encoding='utf-8') as f:
                cached = json.load(f)
            saved = datetime.datetime.fromisoformat(cached['date'])
            if (datetime.datetime.now() - saved).days < _SP500_CACHE_DAYS:
                return cached['symbols']
        except Exception:
            pass
    # Fetch from Wikipedia
    try:
        url = 'https://en.wikipedia.org/wiki/List_of_S%26P_500_companies'
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req, timeout=15) as r:
            html = r.read().decode('utf-8')
        import re
        # First table: wikitable, tickers in first <td> of each row
        tickers = re.findall(r'<td><a[^>]*>([A-Z]{1,5}(?:\.[A-Z])?)</a></td>', html)
        tickers = [t.replace('.', '-') for t in tickers if t]  # BRK.B → BRK-B
        if len(tickers) > 400:
            with open(_SP500_CACHE_FILE, 'w', encoding='utf-8') as f:
                json.dump({'date': datetime.datetime.now().isoformat(), 'symbols': tickers}, f)
            print(f'[sp500] fetched {len(tickers)} symbols from Wikipedia, cached.')
            return tickers
    except Exception as e:
        print(f'[sp500] Wikipedia fetch failed: {e}')
    # Fallback to hardcoded list
    print('[sp500] using hardcoded fallback list')
    return _SP500_FALLBACK

SP500_SYMBOLS = _load_sp500_symbols()


def fetch_sp500_phase1(symbol):
    """Quick check: is symbol near its 52-week high? Returns basic dict or None."""
    try:
        url = 'https://query1.finance.yahoo.com/v8/finance/chart/' + symbol + '?interval=1d&range=5d'
        req = urllib.request.Request(url, headers=HEADERS)
        with urllib.request.urlopen(req, timeout=8) as r:
            data = json.loads(r.read())
        res  = data['chart']['result'][0]
        meta = res['meta']
        price = meta.get('regularMarketPrice')
        if not price:
            return None
        w52h = meta.get('fiftyTwoWeekHigh')
        if not w52h:
            closes = [c for c in res['indicators']['quote'][0].get('close', []) if c]
            w52h = max(closes) if closes else None
        if not w52h or price < w52h * 0.98:
            return None
        name  = meta.get('shortName') or meta.get('longName') or symbol
        prev  = meta.get('chartPreviousClose') or meta.get('previousClose')
        chg   = round((price - prev) / prev * 100, 2) if (price and prev) else None
        mst   = meta.get('marketState') or ''
        return {'symbol': symbol, 'name': name, 'price': round(price, 2),
                'change': chg, 'week52High': round(w52h, 2), 'marketState': mst}
    except Exception:
        return None


def fetch_sp500_phase2(d):
    """Enrich near-ATH stock with YTD%, MA150%, ATH-break count from 1-year daily data."""
    symbol = d['symbol']
    try:
        url = 'https://query1.finance.yahoo.com/v8/finance/chart/' + symbol + '?interval=1d&range=1y'
        req = urllib.request.Request(url, headers=HEADERS)
        with urllib.request.urlopen(req, timeout=12) as r:
            data = json.loads(r.read())
        res    = data['chart']['result'][0]
        ts_all = res.get('timestamp', [])
        cl_all = res['indicators']['quote'][0].get('close', [])
        pairs  = [(t, c) for t, c in zip(ts_all, cl_all) if c is not None]
        if not pairs:
            return d
        price = res['meta'].get('regularMarketPrice') or d['price']
        now_yr = datetime.datetime.now().year
        jan1   = int(datetime.datetime(now_yr, 1, 1).timestamp())
        pre    = [c for t, c in pairs if t < jan1]
        ytd    = [(t, c) for t, c in pairs if t >= jan1]
        dec31  = pre[-1] if pre else None
        ytd_pct = round((price - dec31) / dec31 * 100, 1) if dec31 else None
        closes = [c for _, c in pairs]
        ma150  = round((price - sum(closes[-150:]) / 150) / (sum(closes[-150:]) / 150) * 100, 1) \
                 if len(closes) >= 150 else None
        breaks = 0
        if ytd:
            hi = dec31 or ytd[0][1]
            for _, c in ytd:
                if c > hi:
                    breaks += 1
                hi = max(hi, c)
        # After market close: require today's close to be a new high vs all previous closes.
        # During trading (REGULAR/PRE): Phase-1 price-vs-52wkHigh filter is sufficient.
        market_state = d.get('marketState', '')
        if market_state in ('POST', 'CLOSED', '') and len(pairs) >= 2:
            today_close = pairs[-1][1]
            prev_max    = max(c for _, c in pairs[:-1])
            if today_close < prev_max * 0.998:
                return None

        out = dict(d)
        out.update({'ytd': ytd_pct, 'ma150Pct': ma150, 'athBreaks': breaks})
        return out
    except Exception:
        return d

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

    # Placeholder — prev_close resolved after 1m fetch (chartPreviousClose is accurate there)
    prev_from_bars = None
    closes_d = res_d["indicators"]["quote"][0].get("close", [])
    valid_d  = [c for c in closes_d if c is not None]
    if len(valid_d) >= 2:
        prev_from_bars = valid_d[-2]

    # 2. 1m intraday — pre/after-market detection + accurate previous close
    pre_price   = None
    pre_change  = None
    prev_close  = None  # from 1m/1d: chartPreviousClose = yesterday's official close
    try:
        url_m = base + symbol + "?interval=1m&range=1d&includePrePost=true"
        req2 = urllib.request.Request(url_m, headers=HEADERS)
        with urllib.request.urlopen(req2, timeout=10) as r2:
            data_m = json.loads(r2.read())
        res_m      = data_m["chart"]["result"][0]
        meta_m     = res_m["meta"]
        # chartPreviousClose from 1d range = yesterday's official close (same source as chart modal)
        prev_close = (meta_m.get("chartPreviousClose")
                      or meta_m.get("previousClose")
                      or meta_m.get("regularMarketPreviousClose"))
        timestamps = res_m.get("timestamp", [])
        closes_m   = res_m["indicators"]["quote"][0].get("close", [])
        for t, c in reversed(list(zip(timestamps, closes_m))):
            if t > reg_time and c is not None:
                pre_price  = c
                pre_change = ((pre_price - price) / price * 100) if price else None
                break
    except Exception:
        pass  # pre-market optional

    prev = prev_close or prev_from_bars
    change_pct = ((price - prev) / prev * 100) if (price and prev) else None

    return {
        "symbol":      symbol,
        "name":        name,
        "currency":    currency,
        "price":       price,
        "change":      change_pct,
        "time":        reg_time,
        "prePrice":    pre_price,
        "preChange":   pre_change,
        "marketState": meta.get("marketState") or "",
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

        # S&P 500 ATH scan
        if parsed.path.startswith('/proxy/sp500-ath'):
            global _sp500_ath_cache, _sp500_ath_cache_time
            params = dict(urllib.parse.parse_qsl(parsed.query))
            force  = params.get('force', '').lower() == 'true'
            now_t  = time.time()
            if not force and _sp500_ath_cache is not None and (now_t - _sp500_ath_cache_time) < SP500_ATH_CACHE_TTL:
                body = json.dumps(_sp500_ath_cache, ensure_ascii=False).encode('utf-8')
                self.send_response(200)
                self.send_header('Content-Type', 'application/json; charset=utf-8')
                self.send_header('Access-Control-Allow-Origin', '*')
                self.send_header('Content-Length', str(len(body)))
                self.end_headers()
                self.wfile.write(body)
                return
            try:
                # Phase 1: quick scan — find near-ATH stocks
                phase1 = []
                with ThreadPoolExecutor(max_workers=15) as ex:
                    futs = {ex.submit(fetch_sp500_phase1, s): s for s in SP500_SYMBOLS}
                    for fut in as_completed(futs, timeout=90):
                        try:
                            r = fut.result()
                            if r:
                                phase1.append(r)
                        except Exception:
                            pass
                # Phase 2: YTD%, MA150%, ATH-breaks for near-ATH stocks
                final = []
                if phase1:
                    with ThreadPoolExecutor(max_workers=10) as ex:
                        futs2 = [ex.submit(fetch_sp500_phase2, r) for r in phase1]
                        for fut in as_completed(futs2, timeout=60):
                            try:
                                r = fut.result()
                                if r is not None:
                                    final.append(r)
                            except Exception:
                                pass
                final.sort(key=lambda x: x['symbol'])
                _sp500_ath_cache      = final
                _sp500_ath_cache_time = now_t
                body = json.dumps(final, ensure_ascii=False).encode('utf-8')
                self.send_response(200)
                self.send_header('Content-Type', 'application/json; charset=utf-8')
                self.send_header('Access-Control-Allow-Origin', '*')
                self.send_header('Content-Length', str(len(body)))
                self.end_headers()
                self.wfile.write(body)
            except Exception as e:
                self.send_error(502, 'ATH scan error: ' + str(e))
            return

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
