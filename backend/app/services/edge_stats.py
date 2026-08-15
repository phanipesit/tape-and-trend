"""Per-rule edge statistics with error bars.

Existed as an ad-hoc script before this. It shouldn't have: the question "which of my
rules actually makes money" is the one the whole tracker exists to answer, and it needs
to be checkable at any time rather than recomputed by hand.

Two decisions worth stating, because both change the numbers:

**A win is r_multiple > 0, not outcome = 'target_hit'.** The old router counted only
target hits, so an `expired` trade that closed up was recorded as a loss. That
understates every win rate on the page.

**Every average carries a 95% confidence interval.** A rule with n=33 and a +0.57 R mean
looks like the best thing on the board; the same rule at n=626 measured -0.223. That
specific reversal happened here on 2026-08-15, and the interval is what would have shown
it up front. `verdict` refuses to call an edge either way unless the interval clears
zero.
"""
from ..db import q

MIN_SAMPLE = 20        # below this, report the row but never call it an edge
Z = 1.96               # 95%

_STATS = """
    COUNT(*) FILTER (WHERE outcome IS NOT NULL)                        AS n,
    COUNT(*) FILTER (WHERE outcome IS NULL)                            AS still_open,
    COUNT(*) FILTER (WHERE r_multiple > 0)                             AS wins,
    ROUND(AVG(r_multiple)::numeric, 3)                                 AS avg_r,
    ROUND(STDDEV_SAMP(r_multiple)::numeric, 3)                         AS sd_r,
    ROUND(SUM(r_multiple)::numeric, 2)                                 AS total_r,
    ROUND(MIN(r_multiple)::numeric, 2)                                 AS worst_r,
    ROUND(MAX(r_multiple)::numeric, 2)                                 AS best_r
"""


def _finish(rows: list[dict]) -> list[dict]:
    """Attach win %, the confidence interval, and a verdict that respects it."""
    for r in rows:
        n, avg, sd = r["n"], r["avg_r"], r["sd_r"]
        r["win_pct"] = round(r["wins"] / n * 100, 1) if n else None
        if not n or avg is None or sd is None or n < 2:
            r.update(ci=None, ci_low=None, ci_high=None, verdict="no data")
            continue
        half = Z * float(sd) / (n ** 0.5)
        low, high = float(avg) - half, float(avg) + half
        r["ci"] = round(half, 3)
        r["ci_low"], r["ci_high"] = round(low, 3), round(high, 3)
        if n < MIN_SAMPLE:
            r["verdict"] = "too few"
        elif low > 0:
            r["verdict"] = "positive"
        elif high < 0:
            r["verdict"] = "negative"
        else:
            r["verdict"] = "inconclusive"
    return rows


def _group(expr: str, days: int, extra: str = "") -> list[dict]:
    return _finish(q(f"""SELECT {expr} AS grp, {_STATS}
                         FROM signal_outcomes
                         WHERE signal_date >= CURRENT_DATE - :days {extra}
                         GROUP BY 1 HAVING COUNT(*) FILTER (WHERE outcome IS NOT NULL) > 0
                         ORDER BY avg_r DESC NULLS LAST""", days=days))


def rule_stats(days: int = 3650) -> dict:
    """Everything the /edge page needs to judge each rule on its own merits."""
    by_rule_regime = _finish(q("""
        SELECT setup_tag || ' · ' || COALESCE(regime, 'unknown') AS grp,
               setup_tag, regime, """ + _STATS + """
        FROM signal_outcomes
        WHERE signal_date >= CURRENT_DATE - :days AND regime IS NOT NULL
        GROUP BY 1, 2, 3
        HAVING COUNT(*) FILTER (WHERE outcome IS NOT NULL) >= :min
        ORDER BY setup_tag, regime""", days=days, min=MIN_SAMPLE))

    overall = _finish(q(f"SELECT 'ALL' AS grp, {_STATS} FROM signal_outcomes "
                        f"WHERE signal_date >= CURRENT_DATE - :days", days=days))[0]

    return {
        "days": days, "min_sample": MIN_SAMPLE, "overall": overall,
        "by_rule": _group("setup_tag", days),
        "by_regime": _group("regime", days, "AND regime IS NOT NULL"),
        "by_direction": _group("direction", days),
        "by_market": _group("market", days),
        "by_rule_regime": by_rule_regime,
    }
