from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from ..services.ai_analysis import analyze, analyze_options

router = APIRouter(prefix="/api", tags=["ai"])

# `deep` opts into the slow local reasoning model (OLLAMA_DEEP_MODEL) for this one call.
# Per request rather than per deployment because it is a real trade: measured at 26s
# against 321s on the same prompt. Ignored when that env var is unset.
@router.get("/ai/analyze/{symbol}")
def ai_analyze(symbol: str, deep: bool = False):
    try:
        return analyze(symbol.upper(), deep)
    except ValueError as e:
        raise HTTPException(404, str(e))

class Leg(BaseModel):
    type: str        # call | put
    strike: float
    qty: int
    premium: float

class OptionsReq(BaseModel):
    symbol: str
    strategy_name: str
    strategy_desc: str
    legs: list[Leg]
    net_premium: float
    max_profit: str    # pre-formatted, matching what the UI shows (e.g. "Unlimited ↑" or a number)
    max_loss: str
    breakevens: list[float]
    days_to_expiry: int | None = None
    vol_pct: float | None = None          # realized vol the premiums were priced off
    greeks: dict[str, float] | None = None   # position-level, qty-weighted
    deep: bool = False                       # use OLLAMA_DEEP_MODEL for this call

@router.post("/ai/analyze-options")
def ai_analyze_options(req: OptionsReq):
    try:
        return analyze_options(req.symbol.upper(), req.strategy_name, req.strategy_desc,
                               [L.model_dump() for L in req.legs], req.net_premium,
                               req.max_profit, req.max_loss, req.breakevens,
                               req.days_to_expiry, req.vol_pct, req.greeks, req.deep)
    except ValueError as e:
        raise HTTPException(404, str(e))
