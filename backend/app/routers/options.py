from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from ..services.options import price_strategy, realized_vol

router = APIRouter(prefix="/api", tags=["options"])

class Leg(BaseModel):
    type: str        # call | put
    strike: float
    qty: int

class PriceReq(BaseModel):
    symbol: str
    legs: list[Leg]
    days: int = 30   # calendar days to expiry

@router.post("/options/price")
def options_price(req: PriceReq):
    try:
        return price_strategy(req.symbol.upper(), [L.model_dump() for L in req.legs], req.days)
    except ValueError as e:
        raise HTTPException(404, str(e))

@router.get("/options/vol/{symbol}")
def options_vol(symbol: str):
    try:
        return {"symbol": symbol.upper(), "vol_pct": round(realized_vol(symbol.upper()) * 100, 1)}
    except ValueError as e:
        raise HTTPException(404, str(e))
