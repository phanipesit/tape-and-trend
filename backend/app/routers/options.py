from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from ..services import nse_chain
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
    use_implied: bool = True

@router.post("/options/price")
def options_price(req: PriceReq):
    try:
        return price_strategy(req.symbol.upper(), [L.model_dump() for L in req.legs],
                              req.days, req.use_implied)
    except ValueError as e:
        raise HTTPException(404, str(e))

@router.get("/options/vol/{symbol}")
def options_vol(symbol: str, days: int = 30):
    """Realized vol, plus at-the-money implied when NSE carries the symbol."""
    sym = symbol.upper()
    try:
        rv = realized_vol(sym)
    except ValueError as e:
        raise HTTPException(404, str(e))
    out = {"symbol": sym, "vol_pct": round(rv * 100, 1), "realized_pct": round(rv * 100, 1),
           "implied": None}
    try:
        from ..services.data import get_candles
        spot = float(get_candles(sym, auto=False)["c"].iloc[-1])
        iv = nse_chain.implied_vol(sym, spot, "call", days)
        if iv:
            out["implied"] = iv
            out["vol_pct"] = iv["iv_pct"]
    except Exception:
        pass   # IV is a bonus; never fail the endpoint over it
    return out

@router.get("/options/chain/{symbol}")
def options_chain(symbol: str):
    """Cached chain summary — what's available and how fresh it is."""
    sym = symbol.upper()
    if not nse_chain.nse_target(sym):
        raise HTTPException(404, f"{sym} has no NSE option chain")
    rows = nse_chain.get_chain(sym)
    return {
        "symbol": sym,
        "expiries": [str(e) for e in nse_chain.expiries(sym)],
        "rows": len(rows),
        "spot": float(rows[0]["spot"]) if rows else None,
        "fetched_at": str(max(r["fetched_at"] for r in rows)) if rows else None,
    }

@router.post("/options/chain/{symbol}/refresh")
def options_chain_refresh(symbol: str):
    sym = symbol.upper()
    try:
        return {"symbol": sym, "rows": nse_chain.refresh_chain(sym)}
    except Exception as e:
        # NSE is undocumented and rate-limited; surface the reason rather than a 500.
        raise HTTPException(502, f"NSE chain unavailable for {sym}: {e}")
