from fastapi import APIRouter, BackgroundTasks, HTTPException
from ..services.data import all_symbols, refresh_fundamentals
from ..services.signals import analyse
import time
router = APIRouter(prefix="/api", tags=["screener"])

# Refreshing the whole universe is a multi-minute run (one throttled Yahoo call
# per symbol) — too long for a single blocking request. It runs in the
# background; the frontend polls /fundamentals/refresh-status for progress.
_refresh_state = {"running": False, "done": 0, "total": 0, "errors": {}}

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

def _run_refresh_all():
    syms = all_symbols()
    _refresh_state.update(running=True, done=0, total=len(syms), errors={})
    for s in syms:
        try:
            refresh_fundamentals(s["symbol"])
        except Exception as e:
            _refresh_state["errors"][s["symbol"]] = str(e)
        _refresh_state["done"] += 1
        time.sleep(1.5)
    _refresh_state["running"] = False

@router.post("/fundamentals/refresh-all")
def refresh_all(background_tasks: BackgroundTasks):
    if _refresh_state["running"]:
        return {"already_running": True, **_refresh_state}
    background_tasks.add_task(_run_refresh_all)
    return {"started": True, "total": len(all_symbols())}

@router.get("/fundamentals/refresh-status")
def refresh_status():
    return _refresh_state