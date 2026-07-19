"""Sector rotation analysis: equal-weight sector momentum over multiple windows.

Price/volume momentum by sector is a proxy for institutional rotation —
actual FII/DII sector-wise flows are only published in NSDL/NSE monthly
reports and aren't available from yfinance. Runs entirely off cached
candles (no live fetching), so figures are as of the last candle refresh.
"""
from collections import defaultdict
from ..db import q

# Windows in trading days: label -> lookback
WINDOWS = {"r_1m": 21, "r_3m": 63, "r_6m": 126, "r_1y": 252}

# Keyword rules applied in order to the raw sector label (lowercased).
# The seeded labels are fragmented (51 distinct for IN alone) — this folds
# them into ~16 stable groups. First match wins; fallback is the raw label.
_RULES = [
    ("defense", "Defense"),
    ("bank", "Banks"),
    (("nbfc", "financial", "insurance", "asset management", "fintech"), "Financial Services"),
    (("semiconductor",), "Semiconductors"),
    (("it ", "it/", "software", "digital", "engineering r&d", "technology", "cloud", "ai infra", "ai/design"), "IT & Software"),
    (("pharma", "healthcare"), "Pharma & Healthcare"),
    (("auto",), "Automobiles"),
    (("metals",), "Metals & Mining"),
    (("fmcg", "beverages"), "FMCG"),
    (("consumer", "retail", "hospitality", "airlines", "jewellery", "paints"), "Consumer & Retail"),
    (("oil & gas", "mining/energy", "energy"), "Energy"),
    (("power", "renewable"), "Power & Utilities"),
    (("cement", "chemicals"), "Cement & Chemicals"),
    (("capital goods", "electricals", "industrial", "infrastructure", "ports", "logistics"), "Capital Goods & Infra"),
    (("telecom",), "Telecom"),
    (("conglomerate", "diversified"), "Diversified"),
]

def sector_group(raw: str) -> str:
    s = (raw or "").lower()
    for keys, group in _RULES:
        if isinstance(keys, str):
            keys = (keys,)
        if any(k in s for k in keys):
            return group
    return raw or "Other"

def _pct(c_now: float, c_then: float) -> float | None:
    return (c_now / c_then - 1) * 100 if c_then else None

def analyse(market: str = "IN") -> dict:
    syms = q("SELECT symbol, sector FROM symbols WHERE market=:m", m=market)
    if not syms:
        return {"sectors": [], "as_of": None}
    sector_of = {r["symbol"]: sector_group(r["sector"]) for r in syms}

    rows = q("""SELECT symbol, d, c, v FROM ohlcv WHERE symbol = ANY(:syms)
                ORDER BY symbol, d""", syms=list(sector_of))
    candles = defaultdict(list)
    for r in rows:
        candles[r["symbol"]].append((r["d"], float(r["c"]), int(r["v"] or 0)))

    per_symbol, as_of = [], None
    for sym, series in candles.items():
        if len(series) < 60:
            continue
        closes = [c for _, c, _ in series]
        vols = [v for _, _, v in series]
        last_d, last_c = series[-1][0], closes[-1]
        as_of = max(as_of, last_d) if as_of else last_d
        rets = {k: _pct(last_c, closes[-n - 1]) if len(closes) > n else None
                for k, n in WINDOWS.items()}
        sma200 = sum(closes[-200:]) / min(len(closes), 200)
        # volume trend: last month's avg daily volume vs the prior 3 months'
        v_recent = sum(vols[-21:]) / 21
        v_base = sum(vols[-84:-21]) / 63 if len(vols) >= 84 else None
        per_symbol.append({"sector": sector_of[sym], "rets": rets,
                           "above_sma200": last_c > sma200,
                           "vol_ratio": v_recent / v_base if v_base else None})

    groups = defaultdict(list)
    for p in per_symbol:
        groups[p["sector"]].append(p)

    sectors = []
    for name, members in groups.items():
        agg = {}
        for k in WINDOWS:
            vals = [m["rets"][k] for m in members if m["rets"][k] is not None]
            agg[k] = round(sum(vals) / len(vals), 2) if vals else None
        vratios = [m["vol_ratio"] for m in members if m["vol_ratio"]]
        sectors.append({
            "sector": name, "n": len(members), **agg,
            "breadth": round(100 * sum(m["above_sma200"] for m in members) / len(members)),
            "vol_ratio": round(sum(vratios) / len(vratios), 2) if vratios else None,
        })

    # Rotation quadrant: long-term (6m) vs short-term (1m) momentum, each
    # relative to the median sector — Improving is where rotation money
    # is typically arriving.
    def med(key):
        vals = sorted(s[key] for s in sectors if s[key] is not None)
        return vals[len(vals) // 2] if vals else 0
    m_lt, m_st = med("r_6m"), med("r_1m")
    for s in sectors:
        lt = (s["r_6m"] or 0) >= m_lt
        st = (s["r_1m"] or 0) >= m_st
        s["quadrant"] = ("Leading" if lt and st else "Weakening" if lt else
                         "Improving" if st else "Lagging")

    sectors.sort(key=lambda s: -(s["r_1m"] or -999))
    return {"sectors": sectors, "as_of": str(as_of), "market": market}
