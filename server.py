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
import datetime
import calendar

PORT = int(os.environ.get('PORT', 3000))
YAHOO_BASE = 'https://query2.finance.yahoo.com/v8/finance/chart/'
HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Accept': 'application/json',
    'Accept-Language': 'en-US,en;q=0.9',
}

MARKET_SYMBOLS = ["QQQ", "SPY", "DIA", "IWM", "BTC-USD", "ETH-USD", "TA35.TA", "TA90.TA"]

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

    # Previous close = second-to-last valid daily bar (skips holidays correctly)
    closes_d = res_d["indicators"]["quote"][0].get("close", [])
    valid_d  = [c for c in closes_d if c is not None]
    prev     = valid_d[-2] if len(valid_d) >= 2 else None
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
        "price":     price,
        "change":    change_pct,
        "time":      reg_time,
        "prePrice":  pre_price,
        "preChange": pre_change,
    }

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
            except Exception as e:
                self.send_response(502)
                self.send_header('Content-Type', 'application/json')
                self.send_header('Access-Control-Allow-Origin', '*')
                self.end_headers()
                self.wfile.write(json.dumps({'error': str(e)}).encode())
        else:
            super().do_GET()

    def log_message(self, fmt, *args):
        # Only log API calls, not static files
        path = args[0] if args else ''
        if '/api/' in path or '/proxy/' in path:
            print(f'  → {path} {args[1] if len(args) > 1 else ""}')

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
