from fastapi import APIRouter
from ..services.data import all_symbols
from ..services.signals import analyse

router = APIRouter(prefix="/api", tags=["signals"])

@router.get("/signals")
def signals(market: str | None = None, triggered_only: bool = True):
    out = [analyse(s["symbol"]) for s in all_symbols(market)]
    out = [a for a in out if "error" not in a]
    return [a for a in out if a["signals"]] if triggered_only else out

@router.get("/signals/{symbol}")
def one(symbol: str):
    return analyse(symbol.upper())
