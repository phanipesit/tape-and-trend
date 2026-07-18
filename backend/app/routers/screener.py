from fastapi import APIRouter, HTTPException
from ..services.data import all_symbols, refresh_fundamentals
from ..services.signals import analyse
import time
router = APIRouter(prefix="/api", tags=["screener"])

@router.get("/screener")
def screener(market: str | None = None, max_pe: float = 1e9, min_roe: float = -1e9,
             max_de: float = 1e9, rsi_lo: float = 0, rsi_hi: float = 100,
             above_ema50: bool = False, min_rvol: float = 0):
    out = []
    for s in all_symbols(market):
        a = analyse(s["symbol"])
        if "error" in a:
            continue
        pe, roe, de = s.get("pe"), s.get("roe"), s.get("de")
        if pe is not None and pe > max_pe: continue
        if roe is not None and roe < min_roe: continue
        if de is not None and de > max_de: continue
        if not (rsi_lo <= (a["rsi"] or 50) <= rsi_hi): continue
        if above_ema50 and a["close"] <= a["ema50"]: continue
        if a["rvol"] < min_rvol: continue
        out.append({**s, **{k: a[k] for k in ("close", "rsi", "trend", "rvol", "score")},
                    "mcap": float(s["mcap"]) if s.get("mcap") else None})
    return sorted(out, key=lambda r: -r["score"])

@router.post("/fundamentals/{symbol}/refresh")
def refresh(symbol: str):
    try:
        return refresh_fundamentals(symbol.upper())
    except Exception as e:
        raise HTTPException(502, str(e))

@router.post("/fundamentals/refresh-all")
def refresh_all():
    done = {}
    for s in all_symbols():
        try:
            done[s["symbol"]] = refresh_fundamentals(s["symbol"])
        except Exception as e:
            done[s["symbol"]] = {"error": str(e)}
        time.sleep(1.5)
    return done