import asyncio

from fastapi import APIRouter
from ..services import news as svc
from ..db import q

router = APIRouter(prefix="/api", tags=["news"])

@router.get("/news/{symbol}")
def by_symbol(symbol: str):
    return svc.ticker_news(symbol.upper())

@router.get("/news")
async def feed():
    """Blend NewsAPI headlines (if key set) with watchlist ticker news."""
    # ticker_news (yfinance, behind YF_LOCK) and q() are blocking. In an async
    # endpoint they'd run *on* the event loop and stall every other request plus
    # the alert loop for the length of ~4 network calls — hence to_thread.
    in_, us = await asyncio.gather(svc.market_headlines("in"), svc.market_headlines("us"))
    items = in_ + us
    rows = await asyncio.to_thread(q, "SELECT symbol FROM watchlist LIMIT 4")
    for batch in await asyncio.gather(
            *(asyncio.to_thread(svc.ticker_news, r["symbol"], 3) for r in rows)):
        items += batch
    return items[:30]
