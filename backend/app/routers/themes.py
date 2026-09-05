from fastapi import APIRouter

from ..services import themes as svc

router = APIRouter(prefix="/api", tags=["themes"])


@router.get("/themes")
def themes(market: str | None = None):
    """Revenue acceleration by theme. Cache only — never fetches; statements move four
    times a year and are refreshed explicitly via /api/quality/refresh-all."""
    return svc.board(market.upper() if market else None)
