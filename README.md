# Tape & Trend — IN + US Trading Dashboard

Full-stack trading workbench: **Next.js + Tailwind + TradingView + Recharts** frontend,
**FastAPI + pandas + yfinance** backend, **PostgreSQL** cache and system of record.

Covers: live-ish quotes & watchlist · TradingView charts (NSE + US) · swing-signal
engine with ATR trade plans (long & short) · fundamental + technical screener with
RVOL · sector rotation view · options payoff lab · backtester with costs/slippage
(runs saved to psql) · portfolio manager + trade journal (win rate, expectancy) ·
price/RSI alerts (auto-checked every 5 min) · position-size/risk calculator ·
"Today's focus" dashboard card · news feed.

> Educational tool — not investment advice. Signals are mechanical rules;
> backtests are approximations. Verify everything before trading.

## Prerequisites
- Python 3.11+, Node 18+, PostgreSQL running locally

## 1 · Database
```bash
createdb tapetrend
psql -d tapetrend -f db/schema.sql                        # base tables + seeded IN/US symbols
psql -d tapetrend -f db/migration_002.sql                 # AI-stocks universe expansion
psql -d tapetrend -f db/migration_003_nifty_universe.sql  # NIFTY 50 + NEXT 50 universe
psql -d tapetrend -f db/migration_004_alerts_table.sql    # alerts table
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
# runs in the background (~1.5 s per symbol); poll progress with:
curl http://localhost:8000/api/fundamentals/refresh-status
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
   │                 signals · sectors · backtest (fees+slippage) · news
   │                 alerts_check (background loop, every 5 min)
   ▼
PostgreSQL: symbols · ohlcv · watchlist · portfolio_tx · backtest_runs · alerts
```

## Key API routes
| Route | What |
|---|---|
| `GET /api/watchlist` · `POST/DELETE /api/watchlist/{sym}` | quotes for saved symbols |
| `POST /api/symbols` · `DELETE /api/symbols/{sym}` | add/remove any Yahoo-valid ticker |
| `GET /api/candles/{sym}?indicators=true` | OHLCV + EMA/RSI/MACD/BB/ATR |
| `GET /api/signals` · `GET /api/signals/{sym}` | triggered swing setups + ATR trade plan |
| `GET /api/screener?max_pe=30&min_roe=15&above_ema50=true&min_rvol=1.5` | blended screen, ranked by score |
| `GET /api/sectors?market=IN` | sector rotation snapshot |
| `POST /api/backtest` `{symbol,strategy,params}` | emax / rsi / macd / signal (live engine) with fee_bps, slip_bps |
| `GET /api/portfolio` · `POST /api/portfolio/tx` | positions, avg cost, P&L, journal |
| `GET/POST /api/alerts` · `POST /api/alerts/check` | price/RSI alerts, manual check-now |
| `GET /api/news` | yfinance ticker news + NewsAPI headlines (optional key) |

## Extending
- **Real-time India**: plug Zerodha Kite Connect or ICICI Breeze into
  `services/data.py` (note SEBI's static-IP rule for API *trading* from Apr 2026).
- **Better backtests**: swap `services/backtest.py` for `vectorbt` or `backtesting.py`.
- **Intraday**: add an `interval` column to `ohlcv` and fetch `1h`/`15m` from yfinance.
- **Real option chains**: the Options lab uses synthetic strikes/premiums — wire an
  option-chain service (broker API or `nsepython`) into it for live quotes.
- **Time-series speed**: install the TimescaleDB extension and make `ohlcv` a hypertable.
