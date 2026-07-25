# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

Tape & Trend: a full-stack trading workbench (educational, not investment advice) covering
IN (NSE/BSE) + US equities — watchlist/quotes, TradingView charts, a swing-signal engine,
fundamental+technical screener, sector rotation view, options payoff lab, backtester,
portfolio/journal, price/RSI alerts, risk sizing, and news. Next.js frontend, FastAPI backend, PostgreSQL as cache + system of record.

## Commands

**Database** (PostgreSQL must be running locally, db name `tapetrend`):
```bash
createdb tapetrend
psql -d tapetrend -f db/schema.sql                        # base tables + seed symbols/watchlist
psql -d tapetrend -f db/migration_002.sql                 # AI-stocks universe (see Known inconsistency)
psql -d tapetrend -f db/migration_003_nifty_universe.sql  # NIFTY 50 + NEXT 50 universe
psql -d tapetrend -f db/migration_004_alerts_table.sql    # alerts table
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

**Backend tests** (pytest, from `backend/` with the venv active):
```bash
python -m pytest          # fast, DB-free: synthetic candles + monkeypatched q()
```
Tests live in `backend/tests/` and cover indicators, signal rules (`analyse_df`), the
signal-outcome scorer (`score_signal`), portfolio replay/stats, and backtester math.
There is still no frontend test runner, linter, or type checker — don't invent commands
for those.

## Architecture

```
Next.js (frontend/)                 fetch → http://localhost:8000/api/*
   │  app/<page>/page.jsx  (one route per feature, "use client")
   │  components/          (Nav, TickerTape, TVChart — TradingView widget wrapper)
   │  lib/api.js            single fetch wrapper `api(path, opts)` + tvSymbol()/fmt() helpers
   ▼
FastAPI (backend/app/)
   main.py            — creates app, mounts every router, runs a background asyncio task
                         that calls services/alerts_check.check_all() every 5 min and the
                         signal tracker (services/signal_eval snapshot+evaluate) once a day
   routers/*.py        — thin: parse request, call a service function, return dict/list
   services/*.py        — all business logic lives here (see below)
   db.py                — single helper `q(sql, **params)` over SQLAlchemy Core; no ORM models
   config.py             — env vars via python-dotenv
   ▼
PostgreSQL: symbols · ohlcv · intraday_ohlcv · watchlist · portfolio_tx · backtest_runs ·
            alerts · signal_outcomes · rotation_runs (+ whatever each migration_NNN.sql under db/ adds)
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

**Intraday data is a separate, parallel cache**, not a variant of the daily one:
`intraday_ohlcv` is timestamp-grained (`PRIMARY KEY (symbol, interval, ts)` — `interval`
is part of the key because 1m/5m/15m bars for the same symbol land on overlapping
timestamps) rather than date-grained. Still fetched through `services/data.py` (the
"only place that talks to yfinance" rule holds): `refresh_intraday`/`get_intraday`
mirror `refresh_candles`/`get_candles`'s shape but with their own short staleness
window (`INTRADAY_STALE_MINUTES`, minutes not hours) and their own period-per-interval
map (Yahoo's real limits, verified live: `1m` → 7 days of history, `5m`/`15m` → 60
days). Refresh is always lazy/on-demand per symbol — there's no background task
pre-fetching an intraday universe, since day trading only cares about whatever symbol
is actually open on the `/daytrading` page right now.

**Indicators are computed on demand, not stored.** `services/indicators.py` has raw pandas
implementations (no TA-Lib) — sma/ema/rsi/macd/bollinger/atr — and `enrich(df)` attaches the
standard set (ema20/ema50/sma200/rsi14/macd_h/bollinger/atr14/vol20/hi20/lo20) used everywhere
else. `services/signals.py` (`analyse`) runs a fixed rule set over the enriched last two bars to
emit BUY/SELL/WATCH signals with a direction-aware conviction `score` (conflicting BUY/SELL
signals net out; the RVOL bonus only counts when at least one rule fired), plus an ATR-based
entry/stop/target that follows the dominant `direction` (`LONG`/`SHORT`; long when there is no
edge, so the risk calculator can always load a plan) — this is the shared building block for
the signals page, Today's Focus, the screener's ranking, and alerts.

**Day trading is a parallel indicator/signal stack, not a variant of the swing one.**
`enrich_intraday(df, interval)` (in `indicators.py`, separate from `enrich()` since
VWAP's session-reset grouping — by UTC date, safe because NSE/US session hours don't
cross UTC midnight — is a different shape of computation) attaches `vwap`, `or_hi`/
`or_lo` (opening-range high/low), `ema9`/`ema20` (fast pair vs. daily's 20/50), and
`rsi7`. `services/intraday_signals.py` (`analyse`) mirrors `signals.py`'s conviction-
score shape exactly but with intraday rules (VWAP reclaim/reject, opening-range
breakout/breakdown, EMA9/20 cross) and its own tighter ATR stop/target multiples
(`INTRADAY_STOP_ATR`/`INTRADAY_TARGET_ATR`, 1×/2× vs. daily's 1.5×/3×). Index symbols
report zero intraday volume from Yahoo, so `vwap` comes back `null` and volume-gated
rules never fire for them — expected, not a bug. No backtester for this yet (would need
session-aware handling — forced end-of-day exits, no overnight holds).

**Backtester** (`services/backtest.py`) is vectorized numpy over `enrich()`'d candles, long-only,
six built-in strategies (`emax`, `rsi`, `macd`, `signal`, `rsi2`, `donchian`) selected by string,
with per-side
fee/slippage in bps. `signal` replays the live swing engine's BUY/SELL rules — its thresholds
are imported from `services/signals.py` (`RSI_OVERSOLD`, `RSI_OVERBOUGHT`, `BREAKOUT_RVOL`,
`STOP_ATR`, `TARGET_ATR`), so changing them there updates the live engine, the backtester and
signal_eval's plans together; the *structure* of the rules (crossover logic etc.) is still
mirrored by hand in both files. Every run is persisted to `backtest_runs` as a side effect of
`run()` — there's no separate "save" step. The `/runs` frontend page reads that table back.
`services/perf.py`'s `perf_stats(curve)` (CAGR/Sharpe/max-drawdown/total-return) is shared
between `backtest.py` and `rotation.py` so both engines report numbers the same way.

**Rotation backtester** (`services/rotation.py`) is a separate, portfolio-level engine —
`backtest.py` only ever tests one symbol against itself, but momentum rotation
(Clenow's "Stocks on the Move") ranks a whole market universe and rotates a basket of the
top N, which needs cross-symbol bookkeeping the single-symbol engine can't do. It reads
only cached candles in one batched query per run (same precondition as `services/sectors.py`
— never a live yfinance refresh per symbol, since that's what `routers/screener.py`'s
"multi-minute run" comment warns against for a ~100-symbol universe). Momentum is a
closed-form rolling OLS on log(close) (`(1+slope)**252 * r_squared`, Clenow's published
formula) — not `rolling().apply()`, which would be far slower. The market-regime filter
(index above its own 200-day SMA) needs index-level price data; `^NSEI`/`^GSPC` are seeded
as ordinary `symbols` rows with `is_index=true`, cached through the exact same
`refresh_candles`/`get_candles` path as any stock, but excluded from `all_symbols()` by
default (pass `include_index=True` to see them) so they never show up in stock-picker
dropdowns. Persists summaries to `rotation_runs`, read back by the `/rotation` page.
`^NSEBANK` (Bank Nifty) is seeded the same way for the Options page's index underlyings —
that page is the one exception that passes `include_index=True`, since Nifty/Bank Nifty are
the most-traded index options on NSE, unlike every other picker (watchlist, portfolio, alerts,
backtest) where an index row would be meaningless clutter.

**AI analysis** (`services/ai_analysis.py`): Claude (`claude-opus-4-8`) when `ANTHROPIC_API_KEY`
is set, otherwise — and on any Claude failure — a rule-based Markdown narrative; either way the
response shape is `{source, analysis, ...}` so the frontend doesn't care which path ran. Two
entry points share a `_run(ctx, system, task)` helper: `analyze(symbol)` (the Charts page's
plain stock read) and `analyze_options(symbol, strategy, legs, ...)` (the Options page's
strategy-aware read, adding a "Strategy fit" section that compares the strategy's stated bias
against the underlying's mechanical signals). Both must treat `direction` defaulting to `LONG`
with an empty `mechanical_signals` as "no signal fired," never as a real bullish read — see the
`SYSTEM_OPTIONS` prompt and `_rule_based`'s strategy branch for why.

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
describes a *different* migration (journal/risk/alerts schema changes) as "migration_002".
`db/` currently contains `migration_002.sql` (AI universe), `migration_003_nifty_universe.sql`,
`migration_004_alerts_table.sql`, `migration_005_paper_trades.sql` (also adds the setup/notes
journal columns the phantom "migration_002" was supposed to create), and
`migration_006_signal_outcomes.sql` — so the next free number is `migration_007`. If you're
adding a new migration file, check what's actually in `db/` rather than trusting either
document's numbering.
