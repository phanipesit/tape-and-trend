# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

Tape & Trend: a full-stack trading workbench (educational, not investment advice) covering
IN (NSE/BSE) + US equities — watchlist/quotes, TradingView charts, a swing-signal engine,
fundamental+technical screener, backtester, portfolio/journal, price/RSI alerts, risk sizing,
and news. Next.js frontend, FastAPI backend, PostgreSQL as cache + system of record.

## Commands

**Database** (PostgreSQL must be running locally, db name `tapetrend`):
```bash
createdb tapetrend
psql -d tapetrend -f db/schema.sql          # base tables + seed symbols/watchlist
psql -d tapetrend -f db/migration_002.sql   # additive migrations, run in order if present
```

**Backend** (FastAPI, port 8000, from `backend/`):
```bash
python -m venv .venv && .venv\Scripts\activate      # Windows
pip install -r requirements.txt
uvicorn app.main:app --reload
```
Interactive API docs at http://localhost:8000/docs. Config comes from `backend/.env`
(`DATABASE_URL`, `TWELVEDATA_KEY`, `NEWSAPI_KEY`, `CORS_ORIGINS`), templated by `.env.example`.

**Frontend** (Next.js 14 App Router, port 3000, from `frontend/`):
```bash
npm install
npm run dev      # dev server
npm run build    # production build
npm run start    # serve production build
```

**Both at once**: `start.bat` (Windows) launches backend + frontend in separate windows and
opens the browser — paths inside it are hardcoded to this checkout's location.

There is no test suite, linter, or type checker configured in this repo (no pytest/jest/eslint
config present) — don't invent commands for these.

## Architecture

```
Next.js (frontend/)                 fetch → http://localhost:8000/api/*
   │  app/<page>/page.jsx  (one route per feature, "use client")
   │  components/          (Nav, TickerTape, TVChart — TradingView widget wrapper)
   │  lib/api.js            single fetch wrapper `api(path, opts)` + tvSymbol()/fmt() helpers
   ▼
FastAPI (backend/app/)
   main.py            — creates app, mounts every router, runs a background asyncio task
                         that calls services/alerts_check.check_all() every 5 min
   routers/*.py        — thin: parse request, call a service function, return dict/list
   services/*.py        — all business logic lives here (see below)
   db.py                — single helper `q(sql, **params)` over SQLAlchemy Core; no ORM models
   config.py             — env vars via python-dotenv
   ▼
PostgreSQL: symbols · ohlcv · watchlist · portfolio_tx · backtest_runs · alerts (+ whatever
            each migration_NNN.sql under db/ adds)
```

**Router ↔ service split is the core convention.** Routers under `backend/app/routers/`
should stay thin (FastAPI decorators, Pydantic request models, calling into a service);
actual computation belongs in `backend/app/services/`. Each new feature area gets its own
router + service pair, both included in `main.py`'s router tuple.

**Data flow for prices**: `services/data.py` is the only place that talks to yfinance. Candles
are cached in the `ohlcv` table and refreshed lazily (`refresh_candles`) when stale
(`CANDLE_STALE_HOURS` / `_cache_fresh`) rather than on a schedule — every read-path (`quote`,
`get_candles`) triggers a refresh-if-needed and falls back to stale cache on fetch failure. Indian
symbols map to Yahoo's `.NS` (NSE) suffix by default, `.BO` (BSE) for names listed in
`BSE_OVERRIDE` (known-bad NSE data on Yahoo, e.g. `HDFCBANK`). Fundamentals are refreshed
separately (`refresh_fundamentals`, on-demand via `/api/fundamentals/{symbol}/refresh` or
`/refresh-all`) and cached on the `symbols` row, not versioned in `ohlcv`.

**Indicators are computed on demand, not stored.** `services/indicators.py` has raw pandas
implementations (no TA-Lib) — sma/ema/rsi/macd/bollinger/atr — and `enrich(df)` attaches the
standard set (ema20/ema50/sma200/rsi14/macd_h/bollinger/atr14/vol20/hi20/lo20) used everywhere
else. `services/signals.py` (`analyse`) runs a fixed rule set over the enriched last two bars to
emit BUY/SELL/WATCH signals with a conviction `score`, plus an ATR-based entry/stop/target —
this is the shared building block for the signals page, the screener's ranking, and alerts.

**Backtester** (`services/backtest.py`) is vectorized numpy over `enrich()`'d candles, long-only,
three built-in strategies (`emax`, `rsi`, `macd`) selected by string, with per-side fee/slippage
in bps. Every run is persisted to `backtest_runs` as a side effect of `run()` — there's no
separate "save" step. The `/runs` frontend page reads that table back.

**Alerts**: `services/alerts_check.check_all()` polls all rows in `alerts` against live
price/RSI and marks `triggered_at`/`triggered_value` when a condition fires; it's called both
by the startup background loop in `main.py` (every 5 min) and synchronously via
`POST /api/alerts/check`. Alert conditions are one of `price_above|price_below|rsi_above|rsi_below`.

**No ORM.** All SQL is raw, parameterized text via `db.q()` (`SELECT ... WHERE x=:x`,
called as `q(sql, x=val)`), returning `list[dict]`. Writes that need transactional multi-row
inserts (e.g. `refresh_candles`) go through `engine.begin()` directly instead of `q()`.

**Frontend conventions**: every page under `frontend/app/<route>/page.jsx` is a client
component that calls the backend exclusively through `lib/api.js`'s `api()` wrapper (throws on
non-2xx). Charts use `components/TVChart.jsx` (TradingView widget) for candles and Recharts for
everything else (equity curves, etc). `lib/api.js`'s `tvSymbol()` is the single place mapping
IN symbols to `BSE:<symbol>` for TradingView — there's no other symbol-mapping table on the
frontend. Styling is Tailwind with a fixed dark palette defined in `tailwind.config.js`
(`bg/panel/panel2/line/line2/txt/mut/dim/brass/up/down/info`) — reuse these tokens rather than
introducing new colors.

**Adding a new backend feature** typically means: a new table (new `db/migration_NNN.sql`,
additive only — never edit `schema.sql` or a shipped migration in place), a service module with
the logic, a router module exposing it under `/api`, registering the router in `main.py`, and a
corresponding page under `frontend/app/<route>/` plus a `Nav.jsx` entry.

## Known inconsistency

`db/migration_002.sql`'s content is actually the "AI-focused universe expansion" migration
(its own header comment calls it `migration_003_ai_stocks.sql`), while `UPDATE-INSTRUCTIONS.md`
describes a *different* migration (journal/risk/alerts schema changes) as "migration_002". If
you're adding a new migration file, check what's actually in `db/` rather than trusting either
document's numbering, and pick the next free `migration_NNN.sql` number.
