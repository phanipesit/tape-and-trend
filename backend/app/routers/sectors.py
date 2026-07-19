from fastapi import APIRouter
from ..services.sectors import analyse

router = APIRouter(prefix="/api", tags=["sectors"])

@router.get("/sectors")
def sectors(market: str = "IN"):
    return analyse(market if market in ("IN", "US") else "IN")
