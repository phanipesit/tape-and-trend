from fastapi import APIRouter
from ..services import heatmap as svc

router = APIRouter(prefix="/api", tags=["heatmap"])

@router.get("/heatmap")
def board(market: str | None = None):
    return svc.board(market.upper() if market else None)
