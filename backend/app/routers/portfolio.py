from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from ..db import q
from ..services.data import quote

router = APIRouter(prefix="/api", tags=["portfolio"])

class Tx(BaseModel):
    symbol: str
    side: str          # BUY | SELL
    qty: float
    price: float | None = None

@router.post("/portfolio/tx")
def add_tx(tx: Tx):
    if tx.side not in ("BUY", "SELL"):
        raise HTTPException(400, "side must be BUY or SELL")
    px = tx.price or quote(tx.symbol.upper())["price"]
    if not px:
        raise HTTPException(400, "no price available; pass price explicitly")
    q("INSERT INTO portfolio_tx (symbol,side,qty,price) VALUES (:s,:sd,:q,:p)",
      s=tx.symbol.upper(), sd=tx.side, q=tx.qty, p=px)
    return {"ok": True, "price": px}

@router.get("/portfolio")
def positions():
    txs = q("SELECT * FROM portfolio_tx ORDER BY traded_at")
    hold: dict[str, dict] = {}
    for t in txs:
        h = hold.setdefault(t["symbol"], {"qty": 0.0, "cost": 0.0})
        qty, px = float(t["qty"]), float(t["price"])
        if t["side"] == "BUY":
            h["qty"] += qty; h["cost"] += qty * px
        else:
            avg = h["cost"] / h["qty"] if h["qty"] else 0
            h["qty"] -= qty; h["cost"] -= qty * avg
    out = []
    for s, h in hold.items():
        if h["qty"] <= 0: continue
        qt = quote(s)
        avg = h["cost"] / h["qty"]
        val = (qt["price"] or 0) * h["qty"]
        out.append({"symbol": s, "qty": h["qty"], "avg": round(avg, 2),
                    "last": qt["price"], "value": round(val, 2),
                    "pnl": round(val - h["cost"], 2),
                    "pnl_pct": round((qt["price"] / avg - 1) * 100, 2) if qt["price"] else None,
                    "market": q("SELECT market FROM symbols WHERE symbol=:s", s=s)[0]["market"]})
    return {"positions": out, "transactions": txs}

@router.delete("/portfolio/tx/{tx_id}")
def delete_tx(tx_id: int):
    q("DELETE FROM portfolio_tx WHERE id=:i", i=tx_id)
    return {"ok": True}
