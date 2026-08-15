"""FII/DII institutional cash flows, and what they say about positioning.

Foreign and domestic institutions between them move Indian cash equity, and their daily
net is information nothing else in this app has — services/sectors.py's docstring notes
that actual flows aren't in yfinance, which is why sector momentum stands in as a proxy.

**There is no history to backfill.** NSE's /api/fiidiiTradeReact returns the latest
trading day only; `from`/`to` are accepted and ignored, and the historical path 503s
(probed 2026-08-15). Whatever isn't captured on the day is lost, so capture runs from the
daily scheduled task rather than lazily on read. Everything here therefore reports
`days` and degrades honestly: the multi-day regimes simply say they need more history
rather than guessing from two rows.

Regime taxonomy and thresholds follow the methodology in
ajeeshworkspace/indian-trading-skills (MIT), with the data layer replaced — that skill
reads the numbers out of web search results, which is not a defensible source for figures
quoted to four significant figures.
"""
from __future__ import annotations

import logging
from datetime import date, datetime

import httpx

from ..db import q, engine

log = logging.getLogger(__name__)

URL = "https://www.nseindia.com/api/fiidiiTradeReact"
WARMUP = "https://www.nseindia.com/reports/fii-dii"
HEADERS = {
    "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                   "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"),
    "Accept": "application/json, text/plain, */*",
    "Referer": WARMUP,
}

# Rupee crores. From the source methodology; deliberately wide, since these are meant to
# separate "worth noticing" from "ordinary", not to trigger trades.
SIGNIFICANT_DAY = 2_000
MTD_STRONG = 5_000
STREAK_DAYS = 5             # consecutive same-sign days that define a regime
ABSORPTION_FULL = 0.7       # DII offsetting this share of FII selling = a floor
TREND_WINDOW = 10


def _fetch() -> list[dict]:
    """Latest trading day's flows, straight from NSE. Raises — callers serve cache."""
    with httpx.Client(headers=HEADERS, timeout=20, follow_redirects=True) as c:
        w = c.get(WARMUP)
        if w.status_code != 200:
            raise RuntimeError(f"NSE warm-up failed (HTTP {w.status_code})")
        r = c.get(URL)
        if r.status_code != 200:
            raise RuntimeError(f"flows HTTP {r.status_code}")
        payload = r.json()
    if not isinstance(payload, list) or not payload:
        raise RuntimeError("flows payload empty")

    out = []
    for row in payload:
        # NSE labels the foreign side "FII/FPI"; normalise so the CHECK constraint and
        # every query downstream can rely on two fixed values.
        cat = "FII" if str(row.get("category", "")).upper().startswith("FII") else "DII"
        try:
            d = datetime.strptime(row["date"], "%d-%b-%Y").date()
        except (KeyError, ValueError) as e:
            raise RuntimeError(f"unparseable flow date {row.get('date')!r}") from e
        out.append({"flow_date": d, "category": cat,
                    "buy_cr": float(row["buyValue"]), "sell_cr": float(row["sellValue"]),
                    "net_cr": float(row["netValue"])})
    return out


def refresh() -> dict:
    """Capture today's flows. Idempotent — re-running a day overwrites identically."""
    rows = _fetch()
    with engine.begin() as cx:
        for r in rows:
            cx.exec_driver_sql(
                """INSERT INTO institutional_flows
                     (flow_date, category, buy_cr, sell_cr, net_cr, fetched_at)
                   VALUES (%s,%s,%s,%s,%s, now())
                   ON CONFLICT (flow_date, category) DO UPDATE SET
                     buy_cr=EXCLUDED.buy_cr, sell_cr=EXCLUDED.sell_cr,
                     net_cr=EXCLUDED.net_cr, fetched_at=now()""",
                (r["flow_date"], r["category"], r["buy_cr"], r["sell_cr"], r["net_cr"]))
    return {"captured": len(rows), "date": str(rows[0]["flow_date"])}


def history(days: int = 30) -> list[dict]:
    """One row per date: {date, fii, dii}. Newest last, so streaks read naturally."""
    rows = q("""SELECT flow_date, category, net_cr, buy_cr, sell_cr
                FROM institutional_flows
                WHERE flow_date >= CURRENT_DATE - :d
                ORDER BY flow_date""", d=days)
    by_date: dict[date, dict] = {}
    for r in rows:
        e = by_date.setdefault(r["flow_date"], {"date": str(r["flow_date"]),
                                                "fii": None, "dii": None})
        e[r["category"].lower()] = {"net": float(r["net_cr"]), "buy": float(r["buy_cr"]),
                                    "sell": float(r["sell_cr"])}
    return [by_date[d] for d in sorted(by_date)]


def _streak(nets: list[float]) -> int:
    """Length of the current same-sign run, signed. [+1,+2,-3,-4] -> -2."""
    if not nets:
        return 0
    sign = 1 if nets[-1] > 0 else -1 if nets[-1] < 0 else 0
    if sign == 0:
        return 0
    n = 0
    for v in reversed(nets):
        if (v > 0) == (sign > 0) and v != 0:
            n += 1
        else:
            break
    return n * sign


def _label(net: float) -> str:
    if net > SIGNIFICANT_DAY:
        return "significant buy"
    if net < -SIGNIFICANT_DAY:
        return "significant sell"
    return "neutral"


def classify(rows: list[dict]) -> dict:
    """Regime read over whatever history exists. Pure — no DB, no network.

    Every multi-day conclusion states the history it needed. With two days cached the
    honest answer is "not enough data", not a regime derived from two points.
    """
    dated = [r for r in rows if r.get("fii") and r.get("dii")]
    if not dated:
        return {"days": 0, "regime": None,
                "verdict": "No flow data captured yet.", "needs": STREAK_DAYS}

    fii = [r["fii"]["net"] for r in dated]
    dii = [r["dii"]["net"] for r in dated]
    last = dated[-1]
    f, d = fii[-1], dii[-1]
    f_streak, d_streak = _streak(fii), _streak(dii)
    mtd_month = last["date"][:7]
    f_mtd = sum(r["fii"]["net"] for r in dated if r["date"][:7] == mtd_month)
    d_mtd = sum(r["dii"]["net"] for r in dated if r["date"][:7] == mtd_month)
    absorption = (d / abs(f)) if f < 0 and d > 0 else None

    # A streak alone is not enough for the dual regimes. Six consecutive days of -100cr
    # is a rounding error, and calling that "liquidity withdrawing" would cry wolf; the
    # run has to add up to something material on both sides.
    recent_f = sum(fii[-STREAK_DAYS:])
    recent_d = sum(dii[-STREAK_DAYS:])
    material = abs(recent_f) > SIGNIFICANT_DAY and abs(recent_d) > SIGNIFICANT_DAY

    regime, verdict = None, None
    enough = len(dated) >= STREAK_DAYS
    if not enough:
        verdict = (f"Only {len(dated)} day(s) captured — regimes need {STREAK_DAYS}. "
                   "There is no historical feed to backfill from, so this fills in daily.")
    elif f_streak >= STREAK_DAYS and d_streak >= STREAK_DAYS and material:
        regime, verdict = "DUAL BUYING", "Both FII and DII accumulating — broad-based bid."
    elif f_streak <= -STREAK_DAYS and d_streak <= -STREAK_DAYS and material:
        regime, verdict = "DUAL SELLING", "Both sides distributing — liquidity withdrawing."
    elif absorption is not None and absorption >= ABSORPTION_FULL:
        regime, verdict = "DII ABSORPTION", (
            f"DII absorbing {absorption * 100:.0f}% of FII selling — downside cushioned.")
    elif f_streak >= STREAK_DAYS or f_mtd > MTD_STRONG:
        regime, verdict = "FII NET BUYER", "Foreign money flowing in."
    elif f_streak <= -STREAK_DAYS or f_mtd < -MTD_STRONG:
        regime, verdict = "FII NET SELLER", "Sustained foreign outflow."
    else:
        regime, verdict = "MIXED", "No sustained institutional direction."

    return {
        "days": len(dated), "as_of": last["date"], "regime": regime, "verdict": verdict,
        "needs": STREAK_DAYS if not enough else None,
        "fii": {"net": round(f, 2), "label": _label(f), "streak": f_streak,
                "mtd": round(f_mtd, 2)},
        "dii": {"net": round(d, 2), "label": _label(d), "streak": d_streak,
                "mtd": round(d_mtd, 2)},
        "absorption_pct": None if absorption is None else round(absorption * 100, 1),
        "net_10d": {"fii": round(sum(fii[-TREND_WINDOW:]), 2),
                    "dii": round(sum(dii[-TREND_WINDOW:]), 2)},
    }


def board(days: int = 30) -> dict:
    rows = history(days)
    return {"history": rows, "summary": classify(rows)}
