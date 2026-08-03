"""NSE option chain: live implied volatility, cached in `option_chain`.

`services/options.py` prices with *realized* vol because we had no IV feed. NSE publishes
one free — no broker account, no key — and the difference is not academic: at the money on
2026-08-03 NIFTY's IV matched realized within half a point, but Bank Nifty was ~4 points
off, and RELIANCE quoted 16.6 call / 20.2 put. A single realized number cannot express a
skew, so the wings were the most wrong part of every strategy we priced.

Two things about the endpoint, both learned by getting them wrong first:

  - **v3 requires an `expiry` parameter.** Without it you get HTTP 200 with a 2-byte `{}`.
    That was originally read as "the market is closed"; re-probing at 09:34 on an open
    Monday returned the same `{}`, which disproved it. Call
    `/api/option-chain-contract-info?symbol=X` for `expiryDates` first.
  - **We are not bot-blocked.** On the session that returns `{}`, `/api/allIndices`
    returns 113KB. A cookie warm-up plus a browser User-Agent and Referer is enough.

Everything degrades to `realized_vol()` rather than failing: NSE is undocumented and
rate-limited, so an outage must cost accuracy, never availability — the same shape as the
AI provider chain.
"""
from __future__ import annotations

import logging
from datetime import date, datetime, timedelta, timezone

import httpx

from ..config import NSE_CHAIN_STALE_MINUTES
from ..db import q, engine
from sqlalchemy import text

log = logging.getLogger(__name__)

BASE = "https://www.nseindia.com/api"
WARMUP = "https://www.nseindia.com/option-chain"
HEADERS = {
    "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                   "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"),
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": WARMUP,
    "Sec-Fetch-Site": "same-origin",
    "Sec-Fetch-Mode": "cors",
}

# Our symbols are Yahoo-shaped; NSE's chain uses its own names. Only these are
# supported — anything else (US symbols, unlisted names) has no chain and falls back.
NSE_NAME = {"^NSEI": ("NIFTY", "Indices"),
            "^NSEBANK": ("BANKNIFTY", "Indices")}


def nse_target(symbol: str) -> tuple[str, str] | None:
    """(NSE symbol, v3 `type`) or None when the symbol has no NSE chain."""
    if symbol in NSE_NAME:
        return NSE_NAME[symbol]
    if symbol.startswith("^"):
        return None                      # some other index — not on NSE's chain
    try:
        from .data import get_symbol
        if get_symbol(symbol)["market"] != "IN":
            return None
    except Exception:
        return None
    return (symbol, "Equities")


def _parse_expiry(s: str) -> date | None:
    try:
        return datetime.strptime(s, "%d-%b-%Y").date()
    except (ValueError, TypeError):
        return None


def _num(v):
    """NSE sends 0 for unquoted strikes. Zero IV is not a measurement, it's a blank, and
    feeding it to black_scholes() would collapse the option to intrinsic value."""
    return None if v in (None, 0, 0.0, "-", "") else float(v)


def _fetch(symbol: str, expiry: date | None = None) -> tuple[list[dict], date, float]:
    """(rows, expiry, spot) straight from NSE. Raises on any failure — callers fall back."""
    target = nse_target(symbol)
    if not target:
        raise ValueError(f"{symbol} has no NSE option chain")
    nse_sym, kind = target

    with httpx.Client(headers=HEADERS, timeout=20, follow_redirects=True) as c:
        w = c.get(WARMUP)
        if w.status_code != 200 or not len(c.cookies):
            raise RuntimeError(f"NSE warm-up failed (HTTP {w.status_code})")

        ci = c.get(f"{BASE}/option-chain-contract-info?symbol={nse_sym}")
        raw = ci.json().get("expiryDates") or [] if ci.status_code == 200 else []
        available = [d for d in (_parse_expiry(s) for s in raw) if d]
        if not available:
            raise RuntimeError(f"no expiryDates for {nse_sym} (HTTP {ci.status_code})")
        chosen = expiry if expiry in available else available[0]

        r = c.get(f"{BASE}/option-chain-v3?type={kind}&symbol={nse_sym}"
                  f"&expiry={chosen:%d-%b-%Y}")
        if r.status_code != 200:
            raise RuntimeError(f"chain HTTP {r.status_code} for {nse_sym}")
        if len(r.content) < 100:
            # The failure mode this module exists to document.
            raise RuntimeError(f"chain empty for {nse_sym} — expiry param rejected?")
        rec = r.json().get("records") or {}

    return rec.get("data") or [], chosen, float(rec.get("underlyingValue") or 0.0)


def refresh_chain(symbol: str, expiry: date | None = None) -> int:
    """Fetch and upsert one expiry's chain. Returns rows written."""
    rows, chosen, spot = _fetch(symbol, expiry)
    out = []
    for row in rows:
        strike = row.get("strikePrice")
        if strike is None:
            continue
        for opt_type in ("CE", "PE"):
            leg = row.get(opt_type)
            if not leg:
                continue
            out.append((symbol, chosen, float(strike), opt_type,
                        _num(leg.get("impliedVolatility")), _num(leg.get("lastPrice")),
                        int(leg.get("openInterest") or 0), int(leg.get("totalTradedVolume") or 0),
                        spot, datetime.now(timezone.utc)))
    if not out:
        return 0
    with engine.begin() as cx:
        cx.exec_driver_sql(
            "INSERT INTO option_chain(symbol,expiry,strike,opt_type,iv,ltp,oi,volume,spot,fetched_at) VALUES "
            + ",".join(["(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)"] * len(out))
            + """ ON CONFLICT (symbol,expiry,strike,opt_type) DO UPDATE SET
                  iv=EXCLUDED.iv, ltp=EXCLUDED.ltp, oi=EXCLUDED.oi, volume=EXCLUDED.volume,
                  spot=EXCLUDED.spot, fetched_at=EXCLUDED.fetched_at""",
            tuple(p for row in out for p in row))
    log.info("option chain %s %s: %d rows", symbol, chosen, len(out))
    return len(out)


def _cache_fresh(symbol: str) -> bool:
    rows = q("SELECT max(fetched_at) f FROM option_chain WHERE symbol=:s", s=symbol)
    at = rows[0]["f"] if rows else None
    return at is not None and (datetime.now(timezone.utc) - at
                               < timedelta(minutes=NSE_CHAIN_STALE_MINUTES))


def expiries(symbol: str) -> list[date]:
    return [r["expiry"] for r in
            q("SELECT DISTINCT expiry FROM option_chain WHERE symbol=:s ORDER BY expiry", s=symbol)]


def get_chain(symbol: str, expiry: date | None = None, auto: bool = True) -> list[dict]:
    """Cached chain rows, refreshed when stale. Never raises — an empty list means
    'no IV available', which callers read as 'use realized vol'."""
    if auto and not _cache_fresh(symbol):
        try:
            refresh_chain(symbol, expiry)
        except Exception:
            log.warning("option chain refresh failed for %s, serving cache", symbol, exc_info=True)
    sql = "SELECT * FROM option_chain WHERE symbol=:s"
    params = {"s": symbol}
    if expiry is not None:
        sql += " AND expiry=:e"
        params["e"] = expiry
    return q(sql + " ORDER BY expiry, strike", **params)


def implied_vol(symbol: str, strike: float, kind: str, days: int = 30,
                auto: bool = True) -> dict | None:
    """IV for the nearest quoted strike, as a decimal (0.1276), or None.

    Per-leg by design: taking one at-the-money number and applying it across a spread
    would throw away exactly the skew this feed was added to capture.
    """
    opt_type = "CE" if kind == "call" else "PE"
    rows = [r for r in get_chain(symbol, auto=auto)
            if r["opt_type"] == opt_type and r["iv"] is not None]
    if not rows:
        return None

    # Expiry nearest the requested horizon; strike nearest the leg, within that expiry.
    today = date.today()
    wanted = today + timedelta(days=max(days, 0))
    chosen = min({r["expiry"] for r in rows}, key=lambda e: abs((e - wanted).days))
    same = [r for r in rows if r["expiry"] == chosen]
    best = min(same, key=lambda r: abs(float(r["strike"]) - strike))
    return {
        "vol": float(best["iv"]) / 100.0,
        "iv_pct": round(float(best["iv"]), 2),
        "strike_used": float(best["strike"]),
        "expiry": str(chosen),
        "expiry_days": (chosen - today).days,
        "ltp": None if best["ltp"] is None else float(best["ltp"]),
        "fetched_at": str(best["fetched_at"]),
    }
