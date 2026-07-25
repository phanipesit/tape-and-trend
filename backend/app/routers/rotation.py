from fastapi import APIRouter
from pydantic import BaseModel
from ..services import rotation as rot

router = APIRouter(prefix="/api", tags=["rotation"])

class RotReq(BaseModel):
    market: str = "IN"
    params: dict = {}

@router.post("/rotation")
def run(req: RotReq):
    return rot.run(req.market.upper(), req.params)

@router.get("/rotation/history")
def history(market: str | None = None, limit: int = 20):
    return rot.history(market, limit)
