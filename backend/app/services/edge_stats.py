"""Per-rule edge statistics with error bars.

Existed as an ad-hoc script before this. It shouldn't have: the question "which of my
rules actually makes money" is the one the whole tracker exists to answer, and it needs
to be checkable at any time rather than recomputed by hand.

Four decisions worth stating, because each changes the numbers:

**A win is R > 0, not outcome = 'target_hit'.** The old router counted only target hits,
so an `expired` trade that closed up was recorded as a loss. That understates every win
rate on the page.

**Every average carries a 95% confidence interval.** A rule with n=33 and a +0.57 R mean
looks like the best thing on the board; the same rule at n=626 measured -0.223. That
specific reversal happened here on 2026-08-15, and the interval is what would have shown
it up front. `verdict` refuses to call an edge either way unless the interval clears
zero.

**R is net: `r_net`, executable fills after costs** (see signal_eval.score_executable).
Round-trip costs average ~0.11R a trade on these stops, which is the whole size of most
apparent edges. `avg_gross_r` and `avg_cost_r` are reported alongside so the gap is
visible rather than hidden.

**The interval is clustered by signal date.** Signals that fire on the same day are one
market move seen through several tickers, not independent trials — rsi_overbought's 90
signals came from 38 distinct days. Treating them as 90 draws made its interval
[+0.10, +0.63]; clustered, the same data (net) is [-0.04, +0.48]. `days` is the number of
independent observations, and a group needs MIN_DAYS of them before any call is made.
"""
from collections import defaultdict
from math import sqrt

from ..db import q

MIN_SAMPLE = 20        # below this, report the row but never call it an edge
MIN_DAYS = 10          # distinct signal dates; a clustered SE on fewer is not trustworthy
Z = 1.96               # 95%


def _finish(rows: list[dict]) -> list[dict]:
    """Attach win %, the confidence interval, and a verdict that respects it.

    Uses a row's clustered `se` when it has one, else the iid sd/sqrt(n)."""
    for r in rows:
        n, avg, sd = r["n"], r["avg_r"], r.get("sd_r")
        r["win_pct"] = round(r["wins"] / n * 100, 1) if n else None
        se = r.get("se")
        # A clustered row (it carries `days`) must never fall back to the iid formula:
        # one day of five signals would get a tight interval it has not earned.
        if se is None and "days" not in r and sd is not None and n and n >= 2:
            se = float(sd) / sqrt(n)
        if not n or avg is None or se is None or n < 2:
            thin = "days" in r and n and n >= 2 and avg is not None
            r.update(ci=None, ci_low=None, ci_high=None, verdict="too few" if thin else "no data")
            continue
        half = Z * float(se)
        low, high = float(avg) - half, float(avg) + half
        r["ci"] = round(half, 3)
        r["ci_low"], r["ci_high"] = round(low, 3), round(high, 3)
        if n < MIN_SAMPLE or r.get("days", MIN_DAYS) < MIN_DAYS:
            r["verdict"] = "too few"
        elif low > 0:
            r["verdict"] = "positive"
        elif high < 0:
            r["verdict"] = "negative"
        else:
            r["verdict"] = "inconclusive"
    return rows


def summarise(rows: list[dict], grp) -> dict:
    """One group's record from raw signal_outcomes rows. Pure.

    Only rows scored under the current method (r_net present) count; an unscored or
    not-yet-rescored row is open, not a zero."""
    done = [r for r in rows if r.get("r_net") is not None]
    x = [float(r["r_net"]) for r in done]
    n = len(x)
    out = {"grp": grp, "n": n, "still_open": sum(1 for r in rows if r.get("outcome") is None),
           "wins": sum(1 for v in x if v > 0)}
    if not n:
        return {**out, "avg_r": None, "sd_r": None, "total_r": None, "worst_r": None,
                "best_r": None, "avg_gross_r": None, "avg_cost_r": None, "days": 0, "se": None}
    m = sum(x) / n
    sd = sqrt(sum((v - m) ** 2 for v in x) / (n - 1)) if n > 1 else None

    by_day: dict = defaultdict(list)
    for r, v in zip(done, x):
        by_day[r["signal_date"]].append(v)
    k = len(by_day)
    se = None
    if k >= 2:
        # Cluster-robust SE of the mean: residuals summed within a day, squared across days.
        resid = sum((sum(vs) - len(vs) * m) ** 2 for vs in by_day.values())
        se = sqrt(resid) / n * sqrt(k / (k - 1))

    gross = [float(r["r_multiple"]) for r in done if r.get("r_multiple") is not None]
    cost = [float(r["cost_r"]) for r in done if r.get("cost_r") is not None]
    return {**out, "avg_r": round(m, 3), "sd_r": round(sd, 3) if sd is not None else None,
            "total_r": round(sum(x), 2), "worst_r": round(min(x), 2), "best_r": round(max(x), 2),
            "avg_gross_r": round(sum(gross) / len(gross), 3) if gross else None,
            "avg_cost_r": round(sum(cost) / len(cost), 3) if cost else None,
            "days": k, "se": se}


def _grouped(rows: list[dict], key, *, min_n: int = 1) -> list[dict]:
    groups: dict = defaultdict(list)
    for r in rows:
        g = key(r)
        if g is not None:
            groups[g].append(r)
    out = [summarise(v, g) for g, v in groups.items()]
    out = [r for r in out if r["n"] >= min_n]
    out = _finish(out)
    out.sort(key=lambda r: -r["avg_r"] if r["avg_r"] is not None else float("inf"))
    for r in out:
        r.pop("se", None)
    return out


def _rows(days: int) -> list[dict]:
    return q("""SELECT setup_tag, regime, direction, market, signal_date, outcome,
                       r_net, r_multiple, cost_r
                FROM signal_outcomes WHERE signal_date >= CURRENT_DATE - :days""", days=days)


def rule_stats(days: int = 3650) -> dict:
    """Everything the /edge page needs to judge each rule on its own merits."""
    rows = _rows(days)
    by_rule_regime = _grouped(rows, lambda r: (r["setup_tag"], r["regime"]) if r["regime"] else None,
                              min_n=MIN_SAMPLE)
    for r in by_rule_regime:
        r["setup_tag"], r["regime"] = r["grp"]
        r["grp"] = f"{r['setup_tag']} · {r['regime']}"
    by_rule_regime.sort(key=lambda r: (r["setup_tag"], r["regime"]))

    overall = _finish([summarise(rows, "ALL")])[0]
    overall.pop("se", None)
    return {
        "days": days, "min_sample": MIN_SAMPLE, "min_days": MIN_DAYS, "overall": overall,
        "by_rule": _grouped(rows, lambda r: r["setup_tag"]),
        "by_regime": _grouped(rows, lambda r: r["regime"]),
        "by_direction": _grouped(rows, lambda r: r["direction"]),
        "by_market": _grouped(rows, lambda r: r["market"]),
        "by_rule_regime": by_rule_regime,
    }


def edge_book(days: int = 3650) -> dict:
    """Every rule's record, keyed (setup_tag, regime) and (setup_tag, None) for the
    all-regime pool. Unlike rule_stats() nothing is filtered by sample size here: the
    caller decides which cell is deep enough to trust, and needs the thin ones to say
    *why* it fell back."""
    rows = _rows(days)
    book = {}
    for r in _grouped(rows, lambda r: (r["setup_tag"], r["regime"]) if r["regime"] else None):
        book[r["grp"]] = {**r, "grp": r["grp"][0], "regime": r["grp"][1]}
    for r in _grouped(rows, lambda r: r["setup_tag"]):
        book[(r["grp"], None)] = r
    return book
