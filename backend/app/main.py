import asyncio
import logging
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from .config import CORS_ORIGINS
from .routers import (quotes, candles, screener, signals, backtest,
                      portfolio, news, alerts, symbols_admin, sectors, ai,
                      performance, rotation, intraday, options, markets, heatmap)
from .services.alerts_check import check_all
from .services.signal_eval import snapshot_today, evaluate_open
from .db import q

log = logging.getLogger(__name__)

ROUTERS = (quotes, candles, screener, signals, backtest, portfolio, news, alerts,
           symbols_admin, sectors, ai, performance, rotation, intraday, options, markets,
           heatmap)

# Every table a feature reads. This check exists to catch a migration that was never
# run (see db/migration_004's header), so it has to cover the newest tables too —
# an entry missing here is a silent failure inside feature code at request time.
TABLES = ("symbols", "ohlcv", "intraday_ohlcv", "watchlist", "portfolio_tx",
          "backtest_runs", "alerts", "signal_outcomes", "rotation_runs")


def _check_tables():
    for t in TABLES:
        try:
            q(f"SELECT 1 FROM {t} LIMIT 1")
        except Exception:
            log.error("table %s is missing — run db/schema.sql and the db/migration_*.sql files", t)


async def _background_loop():
    signal_day = None   # signal tracker runs once per calendar day, alerts every pass
    while True:
        try:
            await asyncio.to_thread(check_all)
        except Exception:
            log.exception("alert check loop failed; will retry in 5 min")
        today = datetime.now(timezone.utc).date()
        if signal_day != today:
            try:
                logged = await asyncio.to_thread(snapshot_today)
                scored = await asyncio.to_thread(evaluate_open)
                log.info("signal tracker: %d new signals logged, %d scored", logged, scored)
                signal_day = today
            except Exception:
                log.exception("signal tracking failed; will retry in 5 min")
        await asyncio.sleep(300)


@asynccontextmanager
async def lifespan(app: FastAPI):
    _check_tables()
    task = asyncio.create_task(_background_loop())
    yield
    task.cancel()   # otherwise reload/shutdown leaves the 5-min loop running


app = FastAPI(title="Tape & Trend API", version="1.2", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=CORS_ORIGINS,
                   allow_methods=["*"], allow_headers=["*"])

for r in ROUTERS:
    app.include_router(r.router)

@app.get("/")
def root():
    return {"ok": True, "docs": "/docs"}
