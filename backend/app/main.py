import asyncio
import logging
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from .config import CORS_ORIGINS
from .routers import (quotes, candles, screener, signals, backtest,
                      portfolio, news, alerts, symbols_admin)
from .services.alerts_check import check_all

log = logging.getLogger(__name__)

app = FastAPI(title="Tape & Trend API", version="1.2")
app.add_middleware(CORSMiddleware, allow_origins=CORS_ORIGINS,
                   allow_methods=["*"], allow_headers=["*"])

for r in (quotes, candles, screener, signals, backtest,
          portfolio, news, alerts, symbols_admin):
    app.include_router(r.router)

@app.on_event("startup")
async def alert_loop():
    async def loop():
        while True:
            try:
                await asyncio.to_thread(check_all)
            except Exception:
                log.exception("alert check loop failed; will retry in 5 min")
            await asyncio.sleep(300)
    asyncio.create_task(loop())

@app.get("/")
def root():
    return {"ok": True, "docs": "/docs"}
