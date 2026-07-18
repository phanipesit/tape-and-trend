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
    items = await svc.market_headlines("in") + await svc.market_headlines("us")
    for r in q("SELECT symbol FROM watchlist LIMIT 4"):
        items += svc.ticker_news(r["symbol"], limit=3)
    return items[:30]
