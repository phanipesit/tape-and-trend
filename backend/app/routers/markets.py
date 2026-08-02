from fastapi import APIRouter
from ..services.markets import board, refresh_board
from ..services.market_hours import all_venues

router = APIRouter(prefix="/api", tags=["markets"])

@router.get("/markets/board")
def markets_board():
    """Global index board, metals, macro and the synthesised trend read."""
    return board()

@router.get("/markets/venues")
def markets_venues():
    """Session state per venue, in both venue-local and home (config.HOME_TZ) time."""
    return all_venues()

@router.post("/markets/refresh")
def markets_refresh():
    """Pull fresh candles for every board symbol — explicit, never on the read path."""
    return refresh_board()
