"""Market heatmap: one tile per stock, area = activity, colour = direction.

A table of quotes makes you read every row to find what moved; a treemap puts size
and direction in the same glance. This computes the tile weights and buckets so the
frontend only lays them out.

Reads cached candles only — same precondition as sectors.py, rotation.py and
markets.py. The universe is ~124 symbols, so a live fetch per tile is exactly the
multi-minute stall routers/screener.py warns about.

**Weights are shares, never raw values.** `symbols.mcap` and turnover are in each
listing's own currency: Reliance's market cap reads 17.3T (₹) against NVIDIA's 5.0T
($), which would draw Reliance three times NVIDIA's tile when it is roughly a
twenty-fifth of it. Every weight here is therefore normalised against its own
market's total, so a tile means "share of India's / America's traded value" and the
two universes can sit side by side honestly.
"""
import re
from collections import defaultdict

from ..db import q
from .sectors import sector_group

# "AI" as a standalone token. A substring match is the obvious implementation and
# the wrong one — it also tags Ret*ai*l, *Ai*rlines and P*ai*nts, three of which are
# in the seeded Indian universe.
_AI_TOKEN = re.compile(r"(?:^|[^a-z])ai(?:$|[^a-z])")

# The one sector that is the AI trade even though its label never says "AI": the
# chipmakers selling into it. Deliberately *not* "technology" — that bucket is the
# hyperscalers (AAPL, MSFT, GOOGL, META), and folding four of the largest listings
# on earth into the AI filter makes it a megacap-tech filter wearing an AI label.
_AI_SECTORS = {"semiconductors"}


def is_ai(raw_sector: str | None) -> bool:
    s = (raw_sector or "").strip().lower()
    return bool(_AI_TOKEN.search(s)) or s in _AI_SECTORS


def _shares(rows: list[dict], key: str) -> None:
    """Attach `<key>_share`: this row's value as a fraction of its own market's
    total. In-place, because every caller wants it on the row it came from."""
    totals: dict[str, float] = defaultdict(float)
    for r in rows:
        totals[r["market"]] += r[key] or 0
    for r in rows:
        total = totals[r["market"]]
        r[f"{key}_share"] = round((r[key] or 0) / total, 6) if total else 0.0


def board(market: str | None = None) -> dict:
    """Every equity tile, its bucket, and both sizing weights."""
    syms = q(f"""SELECT symbol, name, market, sector, mcap FROM symbols
                 WHERE asset_class='equity' {'AND market=:m' if market else ''}
                 ORDER BY symbol""", **({"m": market} if market else {}))
    if not syms:
        return {"rows": [], "groups": [], "as_of": None, "market": market, "missing": []}
    meta = {r["symbol"]: r for r in syms}

    # Last two bars per symbol in one query — the whole point of the cached table is
    # that this stays a single round trip regardless of universe size.
    bars = q("""SELECT symbol, d, c, v FROM (
                  SELECT symbol, d, c, v,
                         row_number() OVER (PARTITION BY symbol ORDER BY d DESC) rn
                  FROM ohlcv WHERE symbol = ANY(:syms)) t
                WHERE rn <= 2 ORDER BY symbol, d""", syms=list(meta))
    series = defaultdict(list)
    for b in bars:
        series[b["symbol"]].append(b)

    rows, missing = [], []
    for sym, m in meta.items():
        s = series.get(sym)
        if not s:
            missing.append(sym)
            continue
        last = s[-1]
        prev = s[-2] if len(s) > 1 else last
        close, pclose = float(last["c"]), float(prev["c"])
        volume = int(last["v"] or 0)
        rows.append({
            "symbol": sym,
            "name": m["name"],
            "market": m["market"],
            "sector": m["sector"],
            "group": sector_group(m["sector"]),
            "ai": is_ai(m["sector"]),
            "last": round(close, 2),
            "change": round(close - pclose, 2),
            "pct": round((close / pclose - 1) * 100, 2) if pclose else 0.0,
            "volume": volume,
            "turnover": round(close * volume, 2),
            "mcap": float(m["mcap"]) if m["mcap"] is not None else None,
            "as_of": str(last["d"]),
        })

    _shares(rows, "turnover")
    _shares(rows, "mcap")

    agg = defaultdict(lambda: {"n": 0, "turnover_share": 0.0, "pcts": []})
    for r in rows:
        a = agg[r["group"]]
        a["n"] += 1
        a["turnover_share"] += r["turnover_share"]
        a["pcts"].append(r["pct"])
    groups = sorted(
        ({"group": g, "n": a["n"],
          "turnover_share": round(a["turnover_share"], 6),
          "avg_pct": round(sum(a["pcts"]) / len(a["pcts"]), 2)}
         for g, a in agg.items()),
        key=lambda g: -g["turnover_share"])

    return {
        "rows": sorted(rows, key=lambda r: -r["turnover_share"]),
        "groups": groups,
        "ai_count": sum(r["ai"] for r in rows),
        "as_of": max((r["as_of"] for r in rows), default=None),
        "market": market,
        "missing": missing,
    }
