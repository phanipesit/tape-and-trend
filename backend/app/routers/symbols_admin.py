import logging
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
import yfinance as yf
from ..db import q
from ..services.data import yf_symbol, refresh_candles

log = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["symbols"])

class NewSymbol(BaseModel):
    symbol: str
    market: str               # IN | US
    name: str | None = None
    watch: bool = True

@router.post("/symbols")
def add_symbol(s: NewSymbol):
    sym = s.symbol.upper().strip()
    if s.market not in ("IN", "US"):
        raise HTTPException(400, "market must be IN or US")
    if q("SELECT 1 FROM symbols WHERE symbol=:s", s=sym):
        raise HTTPException(409, f"{sym} already exists")
    # validate against yahoo before inserting
    try:
        df = yf.download(yf_symbol(sym, s.market), period="5d",
                         interval="1d", progress=False, auto_adjust=True)
    except Exception:
        log.warning("yahoo validation fetch failed for %s (%s)", sym, s.market, exc_info=True)
        df = None
    if df is None or df.empty:
        raise HTTPException(404,
            f"No data found for {sym} ({s.market}). Check the ticker spelling — "
            f"use the NSE/BSE code for Indian stocks (e.g. ZOMATO) or the US ticker (e.g. CRWD).")
    q("""INSERT INTO symbols (symbol,name,market,sector) VALUES (:s,:n,:m,'Custom')""",
      s=sym, n=s.name or sym.title(), m=s.market)
    if s.watch:
        q("INSERT INTO watchlist(symbol) VALUES (:s) ON CONFLICT DO NOTHING", s=sym)
    try:
        rows = refresh_candles(sym)
    except Exception:
        log.warning("initial candle load failed for %s after insert", sym, exc_info=True)
        rows = 0
    return {"ok": True, "symbol": sym, "candles_loaded": rows}

@router.delete("/symbols/{symbol}")
def remove_symbol(symbol: str):
    sym = symbol.upper()
    if q("SELECT 1 FROM portfolio_tx WHERE symbol=:s LIMIT 1", s=sym):
        raise HTTPException(409, f"{sym} has portfolio transactions — remove those first.")
    q("DELETE FROM alerts WHERE symbol=:s", s=sym)
    q("DELETE FROM watchlist WHERE symbol=:s", s=sym)
    q("DELETE FROM ohlcv WHERE symbol=:s", s=sym)
    q("DELETE FROM symbols WHERE symbol=:s", s=sym)
    return {"ok": True}
