from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from ..db import q
from ..services.alerts_check import check_all

router = APIRouter(prefix="/api", tags=["alerts"])

class AlertIn(BaseModel):
    symbol: str
    condition: str            # price_above | price_below | rsi_above | rsi_below
    threshold: float

@router.get("/alerts")
def list_alerts():
    return q("SELECT * FROM alerts ORDER BY created_at DESC")

@router.post("/alerts")
def create(a: AlertIn):
    if a.condition not in ("price_above", "price_below", "rsi_above", "rsi_below"):
        raise HTTPException(400, "bad condition")
    q("INSERT INTO alerts (symbol,condition,threshold) VALUES (:s,:c,:t)",
      s=a.symbol.upper(), c=a.condition, t=a.threshold)
    return {"ok": True}

@router.delete("/alerts/{alert_id}")
def delete(alert_id: int):
    q("DELETE FROM alerts WHERE id=:i", i=alert_id)
    return {"ok": True}

@router.post("/alerts/{alert_id}/reset")
def reset(alert_id: int):
    q("UPDATE alerts SET triggered_at=NULL, triggered_value=NULL WHERE id=:i", i=alert_id)
    return {"ok": True}

@router.post("/alerts/check")
def check_now():
    return {"fired": check_all()}
