"""Dashboard global market board: world indices, metals, macro, and a synthesised
trend read.

Reads only the cached `ohlcv` table via get_candles — same precondition as sectors.py
and rotation.py. The board covers ~18 symbols; refreshing each live on page load would
turn the dashboard into the multi-minute wait routers/screener.py warns about, so a
stale row is served with its own as-of date rather than blocking.

The point of the trend block is to answer "what is the market doing" in one line
instead of leaving the user to eyeball eighteen percentages. Every number in it is
derived here so the frontend renders rather than computes.
"""
import logging

from .data import get_candles, market_context
from .indicators import sma
from .market_hours import venue_for, venue_state

log = logging.getLogger(__name__)

LOOKBACKS = {"1w": 5, "1m": 21, "3m": 63}
REGION_ORDER = ["INDIA", "AMERICAS", "EUROPE", "APAC", "METALS", "MACRO"]


def _pct(cur: float, past: float) -> float | None:
    return round((cur / past - 1) * 100, 2) if past else None


def _row(meta: dict) -> dict | None:
    """One board row from cached candles. Returns None if we have no history at all."""
    df = get_candles(meta["symbol"], limit=260, auto=False)
    if df.empty:
        return None
    c = df["c"]
    last = float(c.iloc[-1])
    prev = float(c.iloc[-2]) if len(c) > 1 else last
    s200 = sma(c, 200).iloc[-1] if len(c) >= 200 else None
    s50 = sma(c, 50).iloc[-1] if len(c) >= 50 else None

    venue = venue_for(meta["symbol"])
    return {
        "symbol": meta["symbol"], "name": meta["name"], "region": meta["region"],
        "asset_class": meta["asset_class"],
        "last": round(last, 2),
        "change": round(last - prev, 2),
        "pct": round((last / prev - 1) * 100, 2) if prev else 0.0,
        "as_of": str(df["d"].iloc[-1]),
        "performance_pct": {k: _pct(last, float(c.iloc[-n - 1]))
                            for k, n in LOOKBACKS.items() if len(c) > n},
        "above_sma200": None if s200 is None or s200 != s200 else bool(last > float(s200)),
        "above_sma50": None if s50 is None or s50 != s50 else bool(last > float(s50)),
        "hi_52w": round(float(df["h"].tail(252).max()), 2),
        "lo_52w": round(float(df["l"].tail(252).min()), 2),
        "venue": venue,
        "venue_state": venue_state(venue)["state"] if venue else None,
    }


def _trend(indices: list[dict], metals: list[dict], macro: list[dict]) -> dict:
    """One-line read of the global tape, computed rather than left to the frontend.

    Note the rows may not share an as-of date — the board reads cache only, so an
    unrefreshed symbol sits on an older close. The regime is a breadth count over
    200-day averages, which barely moves in a day, so a mixed board still reads
    correctly; `as_of_mixed` on the response is what tells the UI to caveat it.
    """
    scored = [r for r in indices if r["above_sma200"] is not None]
    above = sum(r["above_sma200"] for r in scored)
    up = sum(1 for r in indices if r["pct"] > 0)
    down = sum(1 for r in indices if r["pct"] < 0)

    # Regime from participation, not from any single index. Thresholds are deliberately
    # wide: this is a weather report, not a signal, and it should not flip on one bad day.
    regime, verdict = "MIXED", "no clear global direction"
    if scored:
        share = above / len(scored)
        if share >= 0.7:
            regime, verdict = "RISK-ON", "most world indices are above their 200-day average"
        elif share <= 0.3:
            regime, verdict = "RISK-OFF", "most world indices are below their 200-day average"
        else:
            verdict = "world indices are split around their 200-day averages"

    # Conventional VIX reading: under 20 is a calm tape, 20-30 elevated, above 30 is
    # genuine stress. An earlier 15/25 split called a 16 handle "elevated", which is
    # simply wrong and would have coloured the whole dashboard's tone.
    vix = next((r for r in macro if r["symbol"] == "^VIX"), None)
    vol_note = None
    if vix:
        v = vix["last"]
        vol_note = ("calm" if v < 20 else "elevated" if v < 30 else "stressed")

    gold = next((r for r in metals if r["symbol"] == "GC=F"), None)
    silver = next((r for r in metals if r["symbol"] == "SI=F"), None)
    gs_ratio = round(gold["last"] / silver["last"], 1) if gold and silver and silver["last"] else None

    best = max(indices, key=lambda r: r["pct"], default=None)
    worst = min(indices, key=lambda r: r["pct"], default=None)

    return {
        "regime": regime,
        "verdict": verdict,
        "indices_up": up, "indices_down": down, "indices_total": len(indices),
        "above_sma200": above, "scored": len(scored),
        "vix": vix["last"] if vix else None,
        "volatility": vol_note,
        "gold_silver_ratio": gs_ratio,
        "best": {"symbol": best["symbol"], "name": best["name"], "pct": best["pct"]} if best else None,
        "worst": {"symbol": worst["symbol"], "name": worst["name"], "pct": worst["pct"]} if worst else None,
    }


def board() -> dict:
    """Everything the dashboard's global section needs, in one call."""
    rows, missing = [], []
    for meta in market_context():
        r = _row(meta)
        if r is None:
            missing.append(meta["symbol"])
        else:
            rows.append(r)
    if missing:
        log.info("global board: no cached candles yet for %s", ", ".join(missing))

    indices = [r for r in rows if r["asset_class"] in ("index", "global")]
    metals = [r for r in rows if r["asset_class"] == "metal"]
    macro = [r for r in rows if r["asset_class"] == "macro"]

    by_region: dict[str, list[dict]] = {}
    for r in indices:
        by_region.setdefault(r["region"], []).append(r)
    regions = [{"region": g, "rows": sorted(by_region[g], key=lambda r: r["symbol"])}
               for g in REGION_ORDER if g in by_region]

    # Rows do not share an as-of date. The board never fetches (auto=False), so a symbol
    # only advances when the ↻ button runs or some other page happens to refresh it with
    # auto=True — the signals and day-trading pages do that for ^NSEI/^NSEBANK. Reporting
    # max() as *the* board date therefore claimed "close of <today>" while most of the
    # board was days behind. Report the spread and let the UI say so.
    dates = sorted({r["as_of"] for r in rows})
    newest = dates[-1] if dates else None
    for r in rows:
        r["is_behind"] = r["as_of"] != newest
    behind = sum(r["is_behind"] for r in rows)

    return {
        "regions": regions,
        "metals": sorted(metals, key=lambda r: r["symbol"]),
        "macro": sorted(macro, key=lambda r: r["symbol"]),
        "trend": _trend(indices, metals, macro),
        # Only a single shared date can honestly be called "the" board date.
        "as_of": newest if len(dates) == 1 else None,
        "as_of_oldest": dates[0] if dates else None,
        "as_of_newest": newest,
        "as_of_mixed": len(dates) > 1,
        "rows_behind": behind, "rows_total": len(rows),
        "missing": missing,
    }


def refresh_board(force: bool = False) -> dict:
    """Pull fresh candles for every board symbol. Called explicitly (a button / the
    background loop), never from the read path — 18 sequential yfinance fetches is
    far too slow to sit in a dashboard render."""
    ok, failed = [], []
    for meta in market_context():
        try:
            get_candles(meta["symbol"], limit=1, auto=True)
            ok.append(meta["symbol"])
        except Exception:
            failed.append(meta["symbol"])
            log.warning("global board refresh failed for %s", meta["symbol"], exc_info=True)
    return {"refreshed": len(ok), "failed": failed}
