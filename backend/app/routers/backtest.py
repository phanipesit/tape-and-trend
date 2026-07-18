from fastapi import APIRouter
from pydantic import BaseModel
from ..services import backtest as bt
from ..db import q

router = APIRouter(prefix="/api", tags=["backtest"])

class BTReq(BaseModel):
    symbol: str
    strategy: str = "emax"          # emax | rsi | macd
    params: dict = {}

@router.post("/backtest")
def run(req: BTReq):
    return bt.run(req.symbol.upper(), req.strategy, req.params)

@router.get("/backtest/history")
def history(limit: int = 100):
    return q("SELECT * FROM backtest_runs ORDER BY ran_at DESC LIMIT :n", n=limit)

@router.delete("/backtest/history/{run_id}")
def delete_run(run_id: int):
    q("DELETE FROM backtest_runs WHERE id=:i", i=run_id)
    return {"ok": True}
