from fastapi import APIRouter, HTTPException
from ..services import intraday_signals as isig
from ..services.data import refresh_intraday

router = APIRouter(prefix="/api", tags=["intraday"])

@router.get("/intraday/signals/{symbol}")
def signals(symbol: str, interval: str = "5m"):
    try:
        return isig.analyse(symbol.upper(), interval)
    except ValueError as e:
        raise HTTPException(400, str(e))

@router.post("/intraday/{symbol}/refresh")
def refresh(symbol: str, interval: str = "5m"):
    try:
        return {"rows": refresh_intraday(symbol.upper(), interval)}
    except ValueError as e:
        raise HTTPException(400, str(e))
