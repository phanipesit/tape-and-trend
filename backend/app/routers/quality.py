import logging

from fastapi import APIRouter, HTTPException

from ..db import q
from ..services.data import (all_symbols, get_fundamentals_history,
                             get_fundamentals_history_all,
                             refresh_fundamentals_history)
from ..services.quality import evaluate, screen
from ..services.sectors import sector_group

log = logging.getLogger(__name__)
router = APIRouter(prefix="/api", tags=["quality"])


def _sector(symbol: str) -> str | None:
    rows = q("SELECT sector FROM symbols WHERE symbol=:s", s=symbol)
    return sector_group(rows[0]["sector"]) if rows else None


@router.get("/quality/{symbol}")
def quality_one(symbol: str):
    sym = symbol.upper()
    rows = get_fundamentals_history(sym)
    if not rows:
        raise HTTPException(404, f"no cached statements for {sym} — "
                                 f"POST /api/quality/{sym}/refresh first")
    return evaluate(sym, rows, _sector(sym))


@router.post("/quality/{symbol}/refresh")
def quality_refresh(symbol: str):
    sym = symbol.upper()
    try:
        return {"symbol": sym, "years": refresh_fundamentals_history(sym)}
    except Exception as e:
        raise HTTPException(502, f"statements unavailable for {sym}: {e}")


@router.get("/quality")
def quality_all(market: str | None = None, verdict: str | None = None):
    """Screen the cached universe. Reads cache only — never fetches, since a live pull
    per symbol across ~124 names is the multi-minute stall screener.py warns about."""
    # P/E rides along deliberately. The seven tests contain no price data whatsoever,
    # so a company can clear all of them and still be expensive. Showing the valuation
    # the screen is blind to is what stops "passes" being read as "buy".
    pe = {r["symbol"]: r["pe"] for r in q("SELECT symbol, pe FROM symbols")}
    syms = all_symbols(market)
    history = get_fundamentals_history_all([s["symbol"] for s in syms])
    sector_of = {s["symbol"]: sector_group(s.get("sector")) for s in syms}
    meta = {s["symbol"]: s for s in syms}
    out = []
    for sym, r in screen(syms, history, sector_of).items():
        r["name"] = meta[sym].get("name")
        r["market"] = meta[sym].get("market")
        r["pe"] = float(pe[sym]) if pe.get(sym) is not None else None
        out.append(r)
    if verdict:
        out = [r for r in out if r["verdict"] == verdict]
    # Cleanest first, then strongest, then by how much of the screen could actually be
    # scored — a company judged on 7 tests is a stronger pass than one judged on 3.
    out.sort(key=lambda r: (len(r["failed"]), -(r["strength"] or 0), -r["scored"],
                            r["symbol"]))
    return {"count": len(out), "market": market, "results": out}


@router.post("/quality/refresh-all")
def quality_refresh_all(market: str | None = None):
    """Populate statements for the universe. Slow (one yfinance call per symbol) and
    deliberately explicit — annual statements change four times a year, so this is a
    manual job rather than anything on a read path."""
    ok, failed = 0, []
    for s in all_symbols(market):
        try:
            if refresh_fundamentals_history(s["symbol"]):
                ok += 1
        except Exception:
            failed.append(s["symbol"])
            log.warning("fundamentals history failed for %s", s["symbol"], exc_info=True)
    return {"refreshed": ok, "failed": failed}
