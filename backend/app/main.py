import asyncio
import logging
from datetime import datetime, timezone
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from .config import CORS_ORIGINS
from .routers import (quotes, candles, screener, signals, backtest,
                      portfolio, news, alerts, symbols_admin, sectors, ai,
                      performance, rotation, intraday)
from .services.alerts_check import check_all
from .services.signal_eval import snapshot_today, evaluate_open
from .db import q

log = logging.getLogger(__name__)

app = FastAPI(title="Tape & Trend API", version="1.2")
app.add_middleware(CORSMiddleware, allow_origins=CORS_ORIGINS,
                   allow_methods=["*"], allow_headers=["*"])

for r in (quotes, candles, screener, signals, backtest,
          portfolio, news, alerts, symbols_admin, sectors, ai, performance, rotation, intraday):
    app.include_router(r.router)

@app.on_event("startup")
async def table_check():
    # a missing table otherwise fails silently inside feature code (see db/migration_004 header)
    for t in ("symbols", "ohlcv", "watchlist", "portfolio_tx", "backtest_runs", "alerts"):
        try:
            q(f"SELECT 1 FROM {t} LIMIT 1")
        except Exception:
            log.error("table %s is missing — run db/schema.sql and the db/migration_*.sql files", t)

@app.on_event("startup")
async def alert_loop():
    async def loop():
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
    asyncio.create_task(loop())

@app.get("/")
def root():
    return {"ok": True, "docs": "/docs"}
