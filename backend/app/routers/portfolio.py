from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from ..db import q
from ..services.data import quote, usd_inr_rate

router = APIRouter(prefix="/api", tags=["portfolio"])

class Tx(BaseModel):
    symbol: str
    side: str                  # BUY | SELL
    qty: float
    price: float | None = None
    setup: str = ""            # e.g. "EMA cross", "Breakout", "RSI pullback"
    notes: str = ""            # journal: reason, plan, lesson

@router.post("/portfolio/tx")
def add_tx(tx: Tx):
    if tx.side not in ("BUY", "SELL"):
        raise HTTPException(400, "side must be BUY or SELL")
    px = tx.price or quote(tx.symbol.upper())["price"]
    if not px:
        raise HTTPException(400, "no price available; pass price explicitly")
    q("""INSERT INTO portfolio_tx (symbol,side,qty,price,setup,notes)
         VALUES (:s,:sd,:q,:p,:st,:n)""",
      s=tx.symbol.upper(), sd=tx.side, q=tx.qty, p=px, st=tx.setup, n=tx.notes)
    return {"ok": True, "price": px}

def _replay(txs):
    """Average-cost replay -> open holdings + realized (closed) trades."""
    hold, realized = {}, []
    for t in txs:
        s, qty, px = t["symbol"], float(t["qty"]), float(t["price"])
        h = hold.setdefault(s, {"qty": 0.0, "cost": 0.0})
        if t["side"] == "BUY":
            h["qty"] += qty; h["cost"] += qty * px
        else:
            avg = h["cost"] / h["qty"] if h["qty"] else px
            sell_qty = min(qty, h["qty"]) if h["qty"] else qty
            pnl = (px - avg) * sell_qty
            realized.append({"id": t["id"], "symbol": s, "qty": sell_qty,
                             "avg_in": round(avg, 2), "out": px,
                             "pnl": round(pnl, 2),
                             "ret_pct": round((px / avg - 1) * 100, 2) if avg else None,
                             "setup": t.get("setup") or "", "notes": t.get("notes") or "",
                             "traded_at": t["traded_at"]})
            h["qty"] -= sell_qty; h["cost"] -= sell_qty * avg
    return hold, realized

def _stats(realized):
    if not realized:
        return {"n": 0}
    rets = [r["ret_pct"] for r in realized if r["ret_pct"] is not None]
    wins = [r for r in rets if r > 0]
    losses = [r for r in rets if r <= 0]
    wr = len(wins) / len(rets) if rets else 0
    avg_w = sum(wins) / len(wins) if wins else 0.0
    avg_l = sum(losses) / len(losses) if losses else 0.0
    return {"n": len(rets), "win_rate": round(wr * 100, 1),
            "avg_win_pct": round(avg_w, 2), "avg_loss_pct": round(avg_l, 2),
            "expectancy_pct": round(wr * avg_w + (1 - wr) * avg_l, 2),
            "best_pct": round(max(rets), 2), "worst_pct": round(min(rets), 2)}

@router.get("/portfolio")
def positions():
    txs = q("SELECT * FROM portfolio_tx ORDER BY traded_at, id")
    hold, realized = _replay(txs)
    fx = usd_inr_rate()   # USD->INR, so US and IN positions can share one total
    out, total_inr = [], 0.0
    for s, h in hold.items():
        if h["qty"] <= 0:
            continue
        qt = quote(s)
        avg = h["cost"] / h["qty"]
        val = (qt["price"] or 0) * h["qty"]
        market = q("SELECT market FROM symbols WHERE symbol=:s", s=s)[0]["market"]
        value_inr = val * fx if market == "US" else val
        total_inr += value_inr
        out.append({"symbol": s, "qty": h["qty"], "avg": round(avg, 2),
                    "last": qt["price"], "value": round(val, 2),
                    "value_inr": round(value_inr, 2),
                    "pnl": round(val - h["cost"], 2),
                    "pnl_pct": round((qt["price"] / avg - 1) * 100, 2) if qt["price"] else None,
                    "market": market})
    return {"positions": out, "transactions": txs,
            "journal": realized[::-1], "stats": _stats(realized),
            "total_inr": round(total_inr, 2), "usd_inr": fx}

@router.delete("/portfolio/tx/{tx_id}")
def delete_tx(tx_id: int):
    q("DELETE FROM portfolio_tx WHERE id=:i", i=tx_id)
    return {"ok": True}
