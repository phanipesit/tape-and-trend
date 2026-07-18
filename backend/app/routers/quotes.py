from fastapi import APIRouter
from ..services.data import quote, all_symbols
from ..db import q

router = APIRouter(prefix="/api", tags=["quotes"])

@router.get("/symbols")
def symbols(market: str | None = None):
    return all_symbols(market)

@router.get("/quote/{symbol}")
def one(symbol: str):
    return quote(symbol.upper())

@router.get("/watchlist")
def watchlist():
    rows = q("SELECT symbol FROM watchlist ORDER BY added_at")
    return [quote(r["symbol"]) for r in rows]

@router.post("/watchlist/{symbol}")
def add(symbol: str):
    q("INSERT INTO watchlist(symbol) VALUES (:s) ON CONFLICT DO NOTHING", s=symbol.upper())
    return {"ok": True}

@router.delete("/watchlist/{symbol}")
def remove(symbol: str):
    q("DELETE FROM watchlist WHERE symbol=:s", s=symbol.upper())
    return {"ok": True}
