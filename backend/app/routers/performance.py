from fastapi import APIRouter
from ..db import q
from ..services.edge_stats import rule_stats

router = APIRouter(prefix="/api", tags=["performance"])


@router.get("/performance/rules")
def performance_rules(days: int = 3650):
    """Per-rule expectancy with 95% confidence intervals, split by market regime."""
    return rule_stats(days)

# A win is a positive R, not specifically a target hit: an `expired` trade that closed
# up made money and was previously counted as a loss, understating every win rate here.
_COLS = """COUNT(*) FILTER (WHERE outcome IS NOT NULL)      AS n,
           COUNT(*) FILTER (WHERE outcome IS NULL)          AS open,
           COUNT(*) FILTER (WHERE r_multiple > 0)           AS wins,
           ROUND(AVG(r_multiple), 2)                        AS avg_r,
           ROUND(MAX(r_multiple), 2)                        AS best_r,
           ROUND(MIN(r_multiple), 2)                        AS worst_r,
           ROUND(SUM(r_multiple), 2)                        AS total_r"""

def _agg(group_expr: str, days: int) -> list[dict]:
    rows = q(f"""SELECT {group_expr} AS grp, {_COLS}
                 FROM signal_outcomes
                 WHERE signal_date >= CURRENT_DATE - :days
                 GROUP BY 1
                 ORDER BY avg_r DESC NULLS LAST""", days=days)
    for r in rows:
        r["win_pct"] = round(r["wins"] / r["n"] * 100, 1) if r["n"] else None
    return rows

@router.get("/performance")
def performance(days: int = 90):
    return {
        "days": days,
        "by_setup": _agg("setup_tag", days),
        "by_market": _agg("market", days),
        "by_direction": _agg("direction", days),
        "by_score": _agg("""CASE WHEN score >= 4 THEN 'score ≥ 4'
                                 WHEN score >= 2 THEN 'score 2–4'
                                 ELSE 'score < 2' END""", days),
        "recent": q("""SELECT * FROM signal_outcomes
                       WHERE signal_date >= CURRENT_DATE - :days
                       ORDER BY signal_date DESC, id DESC LIMIT 50""", days=days),
    }
