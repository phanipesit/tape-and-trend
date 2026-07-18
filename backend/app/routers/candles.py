from fastapi import APIRouter
from ..services.data import get_candles, refresh_candles
from ..services.indicators import enrich

router = APIRouter(prefix="/api", tags=["candles"])

@router.get("/candles/{symbol}")
def candles(symbol: str, limit: int = 300, indicators: bool = True):
    df = get_candles(symbol.upper(), limit=limit)
    if df.empty:
        return {"symbol": symbol, "candles": []}
    if indicators:
        df = enrich(df)
    df = df.where(df.notna(), None)
    return {"symbol": symbol.upper(),
            "candles": df.assign(d=df["d"].astype(str)).to_dict("records")}

@router.post("/candles/{symbol}/refresh")
def refresh(symbol: str, period: str = "2y"):
    return {"rows": refresh_candles(symbol.upper(), period)}
