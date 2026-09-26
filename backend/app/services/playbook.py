"""Grade fired setups by what their rules have actually earned.

The swing engine's conviction `score` counts how many rules fired and how loud the
volume was. On 863 scored signals (2026-06-18 → 09-25) it did not predict outcomes —
setups scoring 4-6 averaged -0.20R and 6-8 averaged -0.56R, worse than the 2-4 bucket's
-0.02R — while the system as a whole ran -0.094R with a 95% interval entirely below
zero. Ranking "Today's focus" by score was therefore promoting noise, and some of it
was rules that lose money outright (breakdown_20d, rsi_pullback).

So a setup's rank comes from the *measured* record of the rule that fired, in the
market regime it fired in, because the same rule can flip sign across regimes
(breakout_20d: +0.47R risk-off, -0.29R risk-on). The engine itself is untouched: every
rule keeps firing and keeps being logged, which is the only way a benched rule can
earn its way back or a live one can be caught decaying.

`grade()` is pure — analysis + book + regime in, verdict out — so it is unit-testable
without a database.
"""
from datetime import date

from .edge_stats import MIN_SAMPLE
from .signals import STOP_ATR, TARGET_ATR

# Best first. The frontend sorts by this order, so it is part of the API.
GRADES = ("TRADE", "PAPER", "UNPROVEN", "SKIP")
_RANK = {g: i for i, g in enumerate(GRADES)}

# The record is net R (edge_stats judges r_net), so costs are already paid. This was
# 0.10 while R was gross — roughly one round trip on these stops — and keeping it now
# would charge costs twice. What remains is a small margin: a net lean of a few
# hundredths of an R is inside the noise of the cost estimate itself.
PAPER_MIN_R = 0.05

_WHY = {
    "TRADE": "measured edge — 95% interval clears zero",
    "PAPER": "leaning positive but the interval still spans zero — paper-trade it",
    "UNPROVEN": "too few scored outcomes to judge",
    "SKIP": "this rule has lost money or shown no edge",
}


def _num(v):
    return None if v is None else float(v)


def rule_record(tag: str, regime: str | None, book: dict) -> dict:
    """The record to judge `tag` by: its record in this regime when that cell is deep
    enough, else its all-regime record, else nothing."""
    cell = book.get((tag, regime)) if regime else None
    basis = f"{tag} in {regime}"
    # Thin by either measure: too few signals, or too few distinct days for the
    # clustered interval to mean anything (edge_stats marks that "too few").
    if not cell or cell["n"] < MIN_SAMPLE or cell.get("verdict") == "too few":
        cell, basis = book.get((tag, None)), f"{tag}, all regimes"
    if not cell:
        return {"verdict": "no data", "n": 0, "avg_r": None, "ci_low": None,
                "ci_high": None, "win_pct": None, "basis": basis}
    return {"verdict": cell["verdict"], "n": cell["n"], "avg_r": _num(cell["avg_r"]),
            "ci_low": _num(cell["ci_low"]), "ci_high": _num(cell["ci_high"]),
            "win_pct": cell["win_pct"], "basis": basis}


def rule_grade(rec: dict) -> str:
    v = rec["verdict"]
    if v == "positive":
        return "TRADE"
    if v == "negative":
        return "SKIP"
    if v == "inconclusive":
        # a lean inside the cost estimate's own noise is zero expectancy, not an edge
        return "PAPER" if (rec["avg_r"] or 0) >= PAPER_MIN_R else "SKIP"
    return "UNPROVEN"


def grade(a: dict, book: dict, regime: str | None) -> dict:
    """Attach `edge` to each tradeable signal and a setup-level `playbook`.

    The plan is rebuilt from the *best-graded* rule in that rule's own direction —
    that is the plan signal_eval scored, so it is the one the record describes. The
    engine's net plan can point the other way when rules conflict."""
    best = None
    for s in a.get("signals", []):
        if s["type"] not in ("BUY", "SELL"):
            continue
        rec = rule_record(s["tag"], regime, book)
        rec["grade"] = rule_grade(rec)
        s["edge"] = rec
        key = (_RANK[rec["grade"]], -(rec["ci_low"] if rec["ci_low"] is not None else -9))
        if best is None or key < best[0]:
            best = (key, s)

    if best is None:
        a["playbook"] = {"grade": "UNPROVEN", "why": "watch-only rules fired — none are scored",
                         "regime": regime, "rule": None}
        return a

    s = best[1]
    g = s["edge"]["grade"]
    c, atr = a["close"], a["atr"]
    long_ = s["type"] == "BUY"
    a["playbook"] = {
        "grade": g, "why": _WHY[g], "regime": regime, "rule": s["tag"],
        "edge": s["edge"], "direction": "LONG" if long_ else "SHORT",
        "entry": c,
        "stop": c - STOP_ATR * atr if long_ else c + STOP_ATR * atr,
        "target": c + TARGET_ATR * atr if long_ else c - TARGET_ATR * atr,
        # NSE cash shorts must be squared off intraday; a multi-day short needs stock
        # futures or a put, and only F&O-listed names have those.
        "note": ("Short swing in India: cash shorts can't be held overnight — "
                 "use stock futures or puts (F&O names only)")
                if not long_ and a.get("market") == "IN" else None,
    }
    return a


def sort_key(a: dict):
    p = a.get("playbook") or {}
    e = p.get("edge") or {}
    lo = e.get("ci_low")
    return (_RANK.get(p.get("grade"), 99), -(lo if lo is not None else -9))


def regimes(markets=("IN", "US")) -> dict:
    from .signal_eval import market_regime
    return {m: market_regime(m, date.today()) for m in markets}


def desk(book: dict, regime_by_market: dict, overall: dict) -> dict:
    """What a trader needs before looking at a single chart: is the system making money,
    what tape is each market in, and which rules are live in that tape."""
    # The record is pooled across markets and split by regime, so rules are listed once
    # per regime in force — two markets in the same tape would otherwise repeat rows.
    tags = sorted({t for (t, _r) in book})
    rules = []
    for reg in sorted({r for r in regime_by_market.values()}, key=str):
        for t in tags:
            rec = rule_record(t, reg, book)
            rules.append({"regime": reg, "markets": [m for m, r in regime_by_market.items() if r == reg],
                          "rule": t, **rec, "grade": rule_grade(rec)})
    rules.sort(key=lambda r: (str(r["regime"]), _RANK[r["grade"]], -(r["avg_r"] or -9)))
    return {"regimes": regime_by_market, "overall": overall, "rules": rules,
            "min_sample": MIN_SAMPLE}
