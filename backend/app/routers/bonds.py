from fastapi import APIRouter
from ..services import bonds

router = APIRouter(prefix="/api", tags=["bonds"])

@router.get("/bonds")
def bonds_board():
    """India G-Sec par curve + US Treasuries from cache: points, bp changes, curve shape."""
    return bonds.board()

@router.post("/bonds/refresh")
def bonds_refresh():
    """Fetch any FBIL curves not yet stored, and fresh Treasury candles. The first run
    backfills ~a year of FBIL files and takes a few minutes."""
    return bonds.refresh()
