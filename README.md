# Tape & Trend — IN + US Trading Dashboard

Full-stack trading workbench: **Next.js + Tailwind + TradingView + Recharts** frontend,
**FastAPI + pandas + yfinance** backend, **PostgreSQL** cache and system of record.

Covers: live-ish quotes & watchlist · TradingView charts (NSE + US) · swing-signal
engine · fundamental + technical screener · backtester with costs/slippage (runs
saved to psql) · portfolio manager · news feed.

> Educational tool — not investment advice. Signals are mechanical rules;
> backtests are approximations. Verify everything before trading.

## Prerequisites
- Python 3.11+, Node 18+, PostgreSQL running locally

## 1 · Database
```bash
createdb tapetrend
psql -d tapetrend -f db/schema.sql        # tables + 20 seeded IN/US symbols
```

## 2 · Backend (port 8000)
```bash
cd backend
python -m venv .venv && source .venv/bin/activate    # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp ../.env.example .env                   # edit DATABASE_URL if your psql creds differ
uvicorn app.main:app --reload
```
Open http://localhost:8000/docs for the interactive API.

First-time warm-up (fills the psql cache from yfinance):
```bash
curl -X POST http://localhost:8000/api/fundamentals/refresh-all
# candles auto-fetch lazily per symbol on first request
```

## 3 · Frontend (port 3000)
```bash
cd frontend
npm install
npm run dev
```
Open http://localhost:3000.

## Architecture
```
Next.js (TradingView charts, Recharts curves, Tailwind)
   │  fetch http://localhost:8000/api/*
   ▼
FastAPI ── services: data (yfinance→psql cache) · indicators (pandas)
   │                 signals · backtest (fees+slippage) · news
   ▼
PostgreSQL: symbols · ohlcv · watchlist · portfolio_tx · backtest_runs
```

## Key API routes
| Route | What |
|---|---|
| `GET /api/watchlist` · `POST/DELETE /api/watchlist/{sym}` | quotes for saved symbols |
| `GET /api/candles/{sym}?indicators=true` | OHLCV + EMA/RSI/MACD/BB/ATR |
| `GET /api/signals` | triggered swing setups across the universe |
| `GET /api/screener?max_pe=30&min_roe=15&above_ema50=true` | blended screen |
| `POST /api/backtest` `{symbol,strategy,params}` | emax / rsi / macd with fee_bps, slip_bps |
| `GET /api/portfolio` · `POST /api/portfolio/tx` | positions, avg cost, P&L |
| `GET /api/news` | yfinance ticker news + NewsAPI headlines (optional key) |

## Extending
- **Real-time India**: plug Zerodha Kite Connect or ICICI Breeze into
  `services/data.py` (note SEBI's static-IP rule for API *trading* from Apr 2026).
- **Better backtests**: swap `services/backtest.py` for `vectorbt` or `backtesting.py`.
- **Intraday**: add an `interval` column to `ohlcv` and fetch `1h`/`15m` from yfinance.
- **Options**: add an option-chain service (broker API or `nsepython`) and port the
  payoff builder from the HTML prototype.
- **Time-series speed**: install the TimescaleDB extension and make `ohlcv` a hypertable.
