"""Playbook grading. Pure: a hand-built edge book stands in for signal_outcomes."""
from app.services import playbook as pb
from app.services.edge_stats import MIN_SAMPLE


def cell(verdict, n=100, avg=0.0, lo=None, hi=None):
    return {"verdict": verdict, "n": n, "avg_r": avg, "ci_low": lo, "ci_high": hi, "win_pct": 50.0}


def setup(*tags):
    types = {"breakout_20d": "BUY", "breakdown_20d": "SELL", "rsi_overbought": "SELL",
             "ema_cross_up": "BUY", "macd_flip_up": "WATCH"}
    return {"symbol": "X", "close": 100.0, "atr": 2.0, "direction": "LONG",
            "signals": [{"type": types[t], "tag": t, "why": t} for t in tags]}


BOOK = {
    ("breakout_20d", "RISK_ON"): cell("negative", avg=-0.29, lo=-0.47, hi=-0.11),
    ("breakout_20d", "RISK_OFF"): cell("positive", n=40, avg=0.47, lo=0.04, hi=0.90),
    ("breakout_20d", None): cell("inconclusive", avg=-0.14, lo=-0.31, hi=0.03),
    ("rsi_overbought", None): cell("positive", avg=0.30, lo=0.04, hi=0.55),
    ("rsi_overbought", "RISK_OFF"): cell("positive", n=MIN_SAMPLE - 1, avg=2.0, lo=1.0, hi=3.0),
    ("ema_cross_up", None): cell("inconclusive", avg=0.001, lo=-0.29, hi=0.29),
    ("breakdown_20d", None): cell("negative", avg=-0.2, lo=-0.32, hi=-0.08),
}


def test_same_rule_grades_by_the_regime_it_fired_in():
    """breakout_20d earned money risk-off and lost it risk-on; one grade for both hides that."""
    assert pb.grade(setup("breakout_20d"), BOOK, "RISK_OFF")["playbook"]["grade"] == "TRADE"
    assert pb.grade(setup("breakout_20d"), BOOK, "RISK_ON")["playbook"]["grade"] == "SKIP"


def test_thin_regime_cell_falls_back_to_the_pooled_record():
    rec = pb.rule_record("rsi_overbought", "RISK_OFF", BOOK)
    assert rec["avg_r"] == 0.30 and "all regimes" in rec["basis"]


def test_zero_expectancy_is_skipped_not_paper_traded():
    assert pb.grade(setup("ema_cross_up"), BOOK, None)["playbook"]["grade"] == "SKIP"


def test_plan_follows_the_best_rule_not_the_engines_net_direction():
    """The engine nets a BUY against a SELL; the record describes the rule's own plan."""
    a = pb.grade(setup("breakout_20d", "rsi_overbought"), BOOK, "RISK_ON")
    p = a["playbook"]
    assert p["rule"] == "rsi_overbought" and p["direction"] == "SHORT"
    assert p["stop"] > 100 > p["target"]


def test_watch_only_setup_is_unproven_because_watch_rules_are_never_scored():
    assert pb.grade(setup("macd_flip_up"), BOOK, "RISK_ON")["playbook"]["grade"] == "UNPROVEN"


def test_unknown_rule_is_unproven():
    a = pb.grade({"close": 1, "atr": 1, "signals": [{"type": "BUY", "tag": "new_rule"}]}, BOOK, "RISK_ON")
    assert a["playbook"]["grade"] == "UNPROVEN"


def test_sort_puts_measured_edges_first_and_losers_last():
    rows = [pb.grade(setup(t), BOOK, "RISK_ON") for t in ("breakdown_20d", "rsi_overbought", "macd_flip_up")]
    assert [r["playbook"]["grade"] for r in sorted(rows, key=pb.sort_key)] == ["TRADE", "UNPROVEN", "SKIP"]


def test_a_lean_smaller_than_costs_is_skipped():
    rec = {"verdict": "inconclusive", "avg_r": pb.PAPER_MIN_R - 0.01}
    assert pb.rule_grade(rec) == "SKIP"
    assert pb.rule_grade({**rec, "avg_r": pb.PAPER_MIN_R}) == "PAPER"


def test_indian_short_carries_the_overnight_short_warning():
    a = pb.grade({**setup("rsi_overbought"), "market": "IN"}, BOOK, None)
    assert "futures" in a["playbook"]["note"]
    assert pb.grade({**setup("rsi_overbought"), "market": "US"}, BOOK, None)["playbook"]["note"] is None


def test_desk_lists_each_rule_once_per_regime_not_per_market():
    d = pb.desk(BOOK, {"IN": "RISK_ON", "US": "RISK_ON"}, {})
    tags = [r["rule"] for r in d["rules"]]
    assert len(tags) == len(set(tags)) and d["rules"][0]["markets"] == ["IN", "US"]
