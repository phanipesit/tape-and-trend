from fastapi import APIRouter, HTTPException

from ..services import flows as svc

router = APIRouter(prefix="/api", tags=["flows"])


@router.get("/flows")
def flows(days: int = 30):
    """FII/DII daily flows plus the regime read. Cache only — never fetches on read."""
    return svc.board(days)


@router.post("/flows/refresh")
def flows_refresh():
    """Capture the latest trading day. Also called by the daily scheduled task, which is
    the path that matters: NSE serves no history, so a day missed here is lost."""
    try:
        return svc.refresh()
    except Exception as e:
        raise HTTPException(502, f"NSE flows unavailable: {e}")
