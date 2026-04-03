# MaakavStocks - הוראות לClaude Code

## מה הפרויקט
אפליקציית מעקב מניות אישית. קובץ HTML יחיד + Python server.
עובד מקומית דרך `start.bat` ופרוס ב-Render.

## קבצים
| קובץ | תפקיד |
|------|--------|
| `index.html` | כל האפליקציה — HTML + CSS + JS |
| `server.py` | Python HTTP server + Yahoo Finance proxy |
| `start.bat` | הפעלה מקומית (localhost:3000) |
| `MaakavStocksPush.bat` | git push לGitHub |
| `requirements.txt` | ריק — stdlib בלבד |

## הפעלה מקומית
```
start.bat → python server.py → http://localhost:3000
```
פורט **3000** (8080 תפוס ע"י פרויקט אחר).

## פריסה
- GitHub: `https://github.com/kleinda/MaakavStocks.git`
- Render: מתעדכן אוטומטית בכל push ל-main

## Firebase
- פרויקט: `stockprofitproject`
- Collection: `watchlist`
- Rules: `allow read, write: if true`

## כללים חשובים
- **אל תשנה `server.py`** ללא בקשה מפורשת
- **אל תיצור קבצים חדשים** — הכל בתוך `index.html`
- **אל תעשה git push** ללא אישור מפורש
- **שמור RTL** — האפליקציה בעברית, dir=rtl
- **פורט 3000** — אל תשנה
- אחרי כל שינוי ב-`index.html` — הצע לעשות push עם `MaakavStocksPush.bat`

## קטגוריות
| שם | צבע | סמל |
|----|-----|-----|
| מניות חול | `#ef5350` | 🏢 |
| מניות ישראל | `#f57f17` | 🇮🇱 |
| מדדים ותעודות סל | `#1976d2` | 📊 |
| מטבעות | `#2e7d32` | 💱 |
| אגחים | `#7b1fa2` | 📄 |
| מעקב | `#00838f` | 👁️ |

## סמלים קבועים (MARKET_META)
`QQQ, SPY, DIA, IWM, TA35.TA, TA90.TA, BTC-USD, ETH-USD`

## API Endpoints (server.py)
- `/proxy/market` — quotes לכל הסמלים הקבועים
- `/proxy/market/chart?symbol=X` — YTD data
- `/api/chart/{symbol}?...` — Yahoo Finance proxy כללי
