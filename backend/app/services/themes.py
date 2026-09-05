"""Theme tracker: which parts of the market are inflecting, per the accounts.

The question this answers is "what is actually happening in these businesses", not
"what will their shares do". NVIDIA's revenue inflected in the statements before the
stock finished repricing, and that inflection was visible to anyone reading the filings.
Being on time is worth something; it is not the same as being early, and this is not
privileged information -- every institution sees the same revenue line the same day.

**Acceleration, not growth.** A company compounding 20% a year for a decade is a good
business but not news. A company whose latest year jumped to 33% against a 20% trend is
a change in the world showing up in accounting. Each company is measured against its own
three-year trend, so a fast-growing sector does not automatically outrank a slow one.

**Margin direction rides alongside on purpose.** Revenue accelerating while margins
collapse is a company buying growth, which is a different story from one earning it, and
a headline growth number alone cannot tell them apart.

Medians rather than means throughout: one company tripling its revenue would otherwise
carry an entire theme.

Cannot be validated here, and is not presented as if it could be. Scoring whether these
inflections predict returns needs years of price history against a database holding two
-- the same limit as services/quality.py.
"""
from __future__ import annotations

from collections import defaultdict
from statistics import median

from ..db import q
from .heatmap import is_ai
from .sectors import sector_group

MIN_MEMBERS = 3          # below this a median is one opinion wearing a crowd's clothes
TREND_YEARS = 3
AI_LABEL = "AI theme"


def _cagr(series: dict[int, float], years: int) -> float | None:
    ys = sorted(series)
    if len(ys) < years + 1:
        return None
    first, last = series[ys[-years - 1]], series[ys[-1]]
    if first is None or last is None or first <= 0:
        return None
    return (last / first) ** (1 / years) - 1


def _company(rev: dict[int, float], ni: dict[int, float]) -> dict | None:
    """Per-company growth, acceleration and margin direction, or None if too thin."""
    g1, g3 = _cagr(rev, 1), _cagr(rev, TREND_YEARS)
    if g1 is None or g3 is None:
        return None
    ys = sorted(rev)
    m_now = (ni.get(ys[-1]) / rev[ys[-1]]) if ni.get(ys[-1]) is not None and rev[ys[-1]] else None
    older = ys[-TREND_YEARS - 1]
    m_then = (ni.get(older) / rev[older]) if ni.get(older) is not None and rev[older] else None
    return {"growth_1y": g1, "cagr_3y": g3, "accel": g1 - g3,
            "margin_now": m_now,
            "margin_change": None if m_now is None or m_then is None else m_now - m_then,
            "latest_year": ys[-1]}


def _aggregate(label: str, members: list[dict]) -> dict:
    accel = [m["accel"] for m in members]
    margins = [m["margin_change"] for m in members if m["margin_change"] is not None]
    return {
        "theme": label, "n": len(members),
        "cagr_3y": round(median(m["cagr_3y"] for m in members), 4),
        "growth_1y": round(median(m["growth_1y"] for m in members), 4),
        "accel": round(median(accel), 4),
        # Breadth matters: a median lifted by two names is a different claim from one
        # where most of the theme is moving together.
        "breadth": round(sum(1 for a in accel if a > 0) / len(accel), 3),
        "margin_change": round(median(margins), 4) if margins else None,
        "members": sorted(members, key=lambda m: -m["accel"]),
    }


def board(market: str | None = None) -> dict:
    """Themes ranked by revenue acceleration. Reads cached statements only."""
    rows = q(f"""SELECT f.symbol, f.fiscal_year, f.revenue, f.net_income,
                        s.sector, s.name, s.market
                 FROM fundamentals_history f JOIN symbols s USING(symbol)
                 WHERE f.revenue IS NOT NULL {'AND s.market=:m' if market else ''}""",
             **({"m": market} if market else {}))

    rev: dict[str, dict] = defaultdict(dict)
    ni: dict[str, dict] = defaultdict(dict)
    meta: dict[str, dict] = {}
    for r in rows:
        rev[r["symbol"]][r["fiscal_year"]] = float(r["revenue"])
        if r["net_income"] is not None:
            ni[r["symbol"]][r["fiscal_year"]] = float(r["net_income"])
        meta[r["symbol"]] = r

    groups: dict[str, list] = defaultdict(list)
    for sym, series in rev.items():
        c = _company(series, ni.get(sym, {}))
        if not c:
            continue
        m = meta[sym]
        c |= {"symbol": sym, "name": m["name"], "market": m["market"],
              "sector": m["sector"]}
        groups[sector_group(m["sector"])].append(c)
        # Orthogonal to sector, exactly as on the heatmap: a semiconductor company is
        # both a semiconductor company and part of the AI trade.
        if is_ai(m["sector"]):
            groups[AI_LABEL].append(c)

    themes = [_aggregate(g, ms) for g, ms in groups.items() if len(ms) >= MIN_MEMBERS]
    themes.sort(key=lambda t: -t["accel"])
    return {
        "market": market, "themes": themes,
        "min_members": MIN_MEMBERS, "trend_years": TREND_YEARS,
        "companies": sum(len(g) for k, g in groups.items() if k != AI_LABEL),
    }
