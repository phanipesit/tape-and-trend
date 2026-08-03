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
psql -d tapetrend -f db/migration_005_paper_trades.sql    # journal columns + paper-trade flag
psql -d tapetrend -f db/migration_006_signal_outcomes.sql # signal_outcomes table
psql -d tapetrend -f db/migration_007_rotation.sql        # rotation_runs + ^NSEI/^GSPC index rows
psql -d tapetrend -f db/migration_008_niftybank.sql       # ^NSEBANK index row
psql -d tapetrend -f db/migration_009_intraday.sql        # intraday_ohlcv table
psql -d tapetrend -f db/migration_010_global_markets.sql # asset_class/region + world indices, metals, macro
```
Run every migration in order — skipping any leaves tables that feature code reads at
request time missing. `main.py`'s startup check logs an error naming each absent table.

**Backend** (FastAPI, port 8000, from `backend/`):
```bash
python -m venv .venv && .venv\Scripts\activate      # Windows
pip install -r requirements.txt
python -m uvicorn app.main:app --reload   # not bare `uvicorn` — Device Guard blocks pip's unsigned .exe shims
```
Interactive API docs at http://localhost:8000/docs. Config comes from `backend/.env`
(`DATABASE_URL`, `TWELVEDATA_KEY`, `NEWSAPI_KEY`, `CORS_ORIGINS`), templated by `.env.example`.

**Frontend** (Next.js 14 App Router, port 3000, from `frontend/`):
```bash
npm install
npm run dev      # dev server
npm run build    # production build — NOT while `npm run dev` is running (see below)
npm run start    # serve production build
```
**Never run `npm run build` while the dev server is up.** Next.js uses the same `.next`
directory for both, so a production build overwrites the artifacts the running dev server
is serving and every route starts returning 500 — including routes you didn't touch, which
makes it look like a code fault rather than an artifact clash. Recovery: stop the dev
server, `rm -rf .next`, restart it. To type-check frontend changes without disturbing a
running dev server, stop it first or build from a separate checkout.

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
**`BSE_OVERRIDE` is a daily-only workaround and must never reach the intraday path.**
`yf_symbol()` takes an `intraday=True` flag that forces `.NS`. Yahoo serves no current
intraday for `.BO` at all — a 5m request for `HDFCBANK.BO` returns "possibly delisted, no
price data" — but routing intraday through BSE doesn't *error*: the 60-day request still
returns old bars, so `refresh_intraday` reports a healthy row count while the newest bar
never advances. HDFCBANK sat on the previous Friday's bars for a whole live session while
`/daytrading` scored and displayed them as current. Hence also `analyse()`'s `stale` /
`bar_age_minutes` / `venue_open` fields: a bar older than 3× the interval **while the venue
is open** is a dead feed and the page says so in red. While the venue is shut it is just the
weekend — same distinction the daily quote path already makes.

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

**Global market board** (`services/markets.py` + `services/market_hours.py`) powers the
dashboard's top section. `market_hours.py` is pure — venue sessions over `zoneinfo`, no DB
or network, `now` injectable — so it is fully unit-testable. Everything is rendered in
**both** venue-local and home time (`config.HOME_TZ`, default `Asia/Kolkata`): an India-based
user wants "NYSE opens 19:00 IST", not an offset to compute. Times come from concrete
datetimes rather than fixed offsets, so DST is tracked (the US open is 19:00 IST in summer,
20:00 in winter — there's a test pinning both). Two modelling notes: COMEX metals sessions
start **Sunday** 18:00 ET and wrap past midnight to 17:00 ET next day, so `Venue.days`
carries which weekdays *start* a session and a segment with `end <= start` means it wraps —
treating futures as weekday-only put the Sunday reopen a full day late. And there is
**deliberately no holiday calendar**: every response carries `holidays_applied=false` and the
UI says so, because a silently holiday-blind clock would be trusted and wrong.

`markets.py` reads **cached candles only** (`auto=False`) — same precondition as `sectors.py`
and `rotation.py`; 18 sequential yfinance fetches on a dashboard render is exactly the
multi-minute stall `routers/screener.py` warns about. `refresh_board()` is the explicit
opt-in path behind the ↻ button. `_trend()` synthesises the one-line read (regime from the
share of indices above their 200DMA, VIX bucketed <20 calm / <30 elevated / else stressed,
gold-silver ratio) so the frontend renders rather than computes.

**`asset_class`, not `is_index`, is what keeps these out of pickers** (migration_010).
`is_index` means "tradeable options underlying" — `get_index_symbol()` uses it for the
rotation regime filter and the Options page shows exactly those three. The board's world
indices, metals and macro rows are `is_index=false` with `asset_class` in
`global`/`metal`/`macro`, and `all_symbols()` filters on `asset_class` — otherwise gold
futures would have appeared in every stock dropdown. Foreign venues use `market='GLOBAL'`
(the CHECK constraint was widened); `yf_symbol()` only special-cases `'IN'`, so anything
else passes the ticker through unchanged, which is what Yahoo wants for `^FTSE`/`^N225`/
`000001.SS`.

**Options pricing** (`services/options.py`) is Black-Scholes with **realized** volatility standing in
for implied — there's no option-chain feed, so `realized_vol()` annualises the stdev of 60 days of
log returns from the same cached candles everything else uses (clamped to `MIN_VOL`/`MAX_VOL` so a
flat history can't produce absurd premiums). Before this, the frontend hardcoded premiums as fixed
percentages of spot (a long call was always 3% of spot), so time to expiry wasn't modelled at all
and every break-even, max-profit and max-loss level was arbitrary — a 7-day OTM NIFTY leg priced at
364 where the model says 0.05. Those levels are what the AI analysis reasons over, hence the fix.
`black_scholes()` degenerates to intrinsic value at `t<=0` or `vol<=0` (Greeks zeroed rather than
dividing by zero); `price_strategy()` returns per-leg premium+Greeks plus qty-weighted position
totals, so a short leg flips delta/theta signs the way the real position would. Theta is per
calendar day and vega per 1 percentage point of vol, matching how traders quote them. Premiums stay
editable on the frontend — the model is a starting point, not a quote.

**AI analysis** (`services/ai_analysis.py`): a provider chain, not a single backend. `_providers()`
lists the configured ones best-first — Claude (`claude-opus-4-8`) when `ANTHROPIC_API_KEY` is set,
then a local model through Ollama (`OLLAMA_MODEL`, default `llama3`, via `/api/chat`) — and `_run`
walks it, falling through to the next on any exception and finally to a rule-based Markdown
narrative. Adding a provider means appending to `_providers()`, nothing else. Every path returns
the same `{source, analysis, ...}` shape so the frontend doesn't care which one ran; it renders
attribution via `lib/api.js`'s `aiCredit()`, the single place that maps `source` to a label. The
Ollama call must set `options.num_ctx` explicitly — Ollama truncates to 4096 by default, which
would silently cut the tail off the JSON snapshot.

**Hand the model conclusions, not numbers to derive.** Small local models reliably misread raw
indicator values — llama3 called RSI 48.8 "oversold", RVOL 1.02 "relatively high", and a break-even
*inside* the 20-day range "outside" it, then built a risk conclusion on that inversion. So
`_context()` attaches a `derived` block (`rsi_zone`, `volume_vs_20d_average`, `price_vs_sma200`,
`ema_stack`, `any_signal_fired`) and `analyze_options` adds `breakevens_vs_range`, all pre-computed
by the same `_rsi_zone`/`_rvol_note`/`_range_note` helpers `_rule_based` uses so the two paths can't
drift. Both system prompts instruct the model to restate those fields rather than do arithmetic.
That eliminated all five factual errors in the options narrative. Keep this in mind when adding
fields: anything requiring a comparison or threshold judgement belongs in `derived`, not raw. Two
entry points share a `_run(ctx, system, task)` helper: `analyze(symbol)` (the Charts page's
plain stock read) and `analyze_options(symbol, strategy, legs, ...)` (the Options page's
strategy-aware read, adding a "Strategy fit" section that compares the strategy's stated bias
against the underlying's mechanical signals). Both must treat `direction` defaulting to `LONG`
with an empty `mechanical_signals` as "no signal fired," never as a real bullish read — see the
`SYSTEM_OPTIONS` prompt and `_rule_based`'s strategy branch for why.

**Market heatmap** (`services/heatmap.py` + `frontend/lib/treemap.js`) is the treemap view of
the equity universe — tile area is activity, colour is the day's move. It reads cached candles
only, like `sectors.py`/`rotation.py`/`markets.py`, and pulls the last two bars for every symbol
in **one** windowed query rather than per-symbol reads.

**Every weight is a share, never a raw value.** `symbols.mcap` and turnover are denominated in
each listing's own currency: Reliance's market cap reads 17.3T (₹) against NVIDIA's 5.0T ($),
so raw sizing would draw Reliance ~3× NVIDIA's tile when it is roughly a twenty-fifth of it.
`_shares()` normalises against the row's **own market's** total, which is what makes an
IN+US board meaningful at all. Consequence to keep in mind: unfiltered, each market fills half
the canvas; inside a filter the split shows what fraction of each market's activity that theme
is (AI is ~55% of US turnover, ~2.6% of India's) — that's a real reading, not a bug.

Buckets reuse `sectors.py`'s `sector_group()` (the 51 seeded labels folded into ~16 groups) —
don't add a second mapping. The **AI theme is orthogonal to it**: `is_ai()` matches `ai` as a
standalone regex token, plus `Semiconductors` (the chipmakers never say "AI" in their label but
are the trade). Plain `Technology` is deliberately excluded — that bucket is AAPL/MSFT/GOOGL/
META, and four of the largest listings on earth would dominate every tile, making the AI filter
a megacap-tech filter wearing an AI label. The token boundary is load-bearing — a substring
match also tags Ret**ai**l, **Ai**rlines and P**ai**nts, all three of which are in the seeded
Indian universe; there are tests pinning exactly that.

`lib/treemap.js` implements squarified layout (Bruls/Huizing/van Wijk) rather than using
Recharts' `<Treemap>`, which owns its own label rendering — tiles here need four lines plus a
click target, so they have to be ordinary DOM. Squarified rather than slice-and-dice because
slivers can't be labelled or clicked.

**News wire** (`services/news.py`) blends two sources with incompatible timestamp shapes —
yfinance per-ticker stories (epoch seconds on the legacy field, a Zulu ISO string on the new
one) and NewsAPI business headlines (ISO with an offset) — so `_iso()` normalises everything
to one UTC ISO-8601 string. That's not cosmetic: `order()` sorts the blended feed
lexicographically on that string, so a source left un-normalised would silently sort wrong.
Naive timestamps are assumed UTC rather than passed to `astimezone()`, which would read them
as the server's local time. `order()` also dedupes by lower-cased title (the same story
reaches us from both a ticker feed and a headline feed) and sorts undated items last.
`wire()` owns the blending — the router is a one-liner — and keeps the blocking calls
(`ticker_news` behind `YF_LOCK`, `q()`) in `asyncio.to_thread` so they never run on the event
loop. The dashboard renders it via `components/NewsWire.jsx` (5-min poll, not the 1-min the
price panels use — headlines move slower and each poll costs ~4 upstream fetches); `/news` is
the full-page view. With no `NEWSAPI_KEY` set the feed degenerates to watchlist ticker news
only, which is a working state, not an error.

**The dashboard has no watchlist table** — the news wire took that column. Two capabilities
rode along with it and were rehomed rather than dropped: adding a ticker that isn't in the
universe yet (`POST /api/symbols`, still the only entry point anywhere) is now a compact strip
at the bottom of `app/page.jsx`, and un-watching is now the ★/☆ button on `/screener`, which
became a DELETE/POST toggle instead of add-only.

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
`migration_006_signal_outcomes.sql`, `migration_007_rotation.sql`,
`migration_008_niftybank.sql`, `migration_009_intraday.sql`, and
`migration_010_global_markets.sql` — so the next free number is `migration_011`. If you're
adding a new migration file, check what's actually in `db/` rather than trusting either
document's numbering, this line included.
