from fastapi import APIRouter
from ..services import news as svc

router = APIRouter(prefix="/api", tags=["news"])

@router.get("/news/{symbol}")
def by_symbol(symbol: str):
    return svc.ticker_news(symbol.upper())

@router.get("/news")
async def feed(limit: int = 30):
    return await svc.wire(limit)
