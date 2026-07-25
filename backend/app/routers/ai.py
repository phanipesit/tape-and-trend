from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from ..services.ai_analysis import analyze, analyze_options

router = APIRouter(prefix="/api", tags=["ai"])

@router.get("/ai/analyze/{symbol}")
def ai_analyze(symbol: str):
    try:
        return analyze(symbol.upper())
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

@router.post("/ai/analyze-options")
def ai_analyze_options(req: OptionsReq):
    try:
        return analyze_options(req.symbol.upper(), req.strategy_name, req.strategy_desc,
                               [L.model_dump() for L in req.legs], req.net_premium,
                               req.max_profit, req.max_loss, req.breakevens)
    except ValueError as e:
        raise HTTPException(404, str(e))
