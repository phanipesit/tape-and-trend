from fastapi import APIRouter, HTTPException
from ..services.ai_analysis import analyze

router = APIRouter(prefix="/api", tags=["ai"])

@router.get("/ai/analyze/{symbol}")
def ai_analyze(symbol: str):
    try:
        return analyze(symbol.upper())
    except ValueError as e:
        raise HTTPException(404, str(e))
