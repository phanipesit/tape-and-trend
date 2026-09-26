"""Verdict logic and win definition. No DB: only _finish's pure arithmetic is exercised."""
import pytest

from app.services import edge_stats as es


def row(n, avg, sd, wins=None, grp="x", still_open=0):
    return {"grp": grp, "n": n, "avg_r": avg, "sd_r": sd,
            "wins": n // 2 if wins is None else wins, "still_open": still_open}


def one(**kw):
    return es._finish([row(**kw)])[0]


def test_interval_clearing_zero_upward_is_an_edge():
    r = one(n=400, avg=0.30, sd=1.0)
    assert r["ci_low"] > 0 and r["verdict"] == "positive"


def test_interval_clearing_zero_downward_is_losing():
    r = one(n=400, avg=-0.30, sd=1.0)
    assert r["ci_high"] < 0 and r["verdict"] == "negative"


def test_interval_spanning_zero_refuses_to_call_it():
    """The failure this panel exists to prevent: a positive mean on a thin sample."""
    r = one(n=33, avg=0.566, sd=2.0)
    assert r["ci_low"] < 0 < r["ci_high"]
    assert r["verdict"] == "inconclusive"


def test_small_samples_are_never_called_an_edge_even_when_the_interval_clears():
    # A tiny sample with an implausibly tight sd could otherwise sneak a verdict through.
    r = one(n=5, avg=1.0, sd=0.01)
    assert r["ci_low"] > 0
    assert r["verdict"] == "too few"


def test_the_interval_narrows_as_the_sample_grows():
    small = one(n=25, avg=0.2, sd=1.5)["ci"]
    large = one(n=2500, avg=0.2, sd=1.5)["ci"]
    assert large < small / 5


def test_win_pct_counts_any_positive_r_not_just_target_hits():
    # The old router counted only outcome='target_hit', so an expired trade that closed
    # up was recorded as a loss and every win rate on the page read low.
    assert one(n=100, avg=0.1, sd=1.0, wins=42)["win_pct"] == 42.0


def test_zero_sample_is_handled_rather_than_dividing_by_zero():
    r = one(n=0, avg=None, sd=None)
    assert r["verdict"] == "no data" and r["ci"] is None and r["win_pct"] is None


def test_single_observation_has_no_usable_interval():
    # stddev of one sample is undefined; it must not become a verdict.
    r = one(n=1, avg=2.0, sd=None)
    assert r["verdict"] == "no data"


@pytest.mark.parametrize("n,avg,sd,expected", [
    (405, -0.184, 1.24, "negative"),      # the real overall figure
    (170, -0.455, 1.01, "negative"),      # breakdown_20d
    (110, -0.040, 1.35, "inconclusive"),  # breakout_20d
])
def test_matches_the_live_numbers(n, avg, sd, expected):
    assert one(n=n, avg=avg, sd=sd)["verdict"] == expected


# ---------------------------------------------------------------- net R, clustered by day

from datetime import date, timedelta


def sig(day, r, gross=None, cost=0.1):
    return {"signal_date": date(2026, 7, 1) + timedelta(days=day), "r_net": r,
            "r_multiple": r + cost if gross is None else gross, "cost_r": cost, "outcome": "x"}


def test_same_day_signals_are_one_observation_not_several():
    """rsi_overbought's 90 signals came from 38 days; the iid interval was far too tight."""
    spread = [sig(d, v) for d, v in enumerate([1.0, -0.6] * 15)]           # 30 separate days
    clumped = [sig(d // 5, v) for d, v in enumerate(                        # 6 days of 5 alike
        [1.0] * 5 + [-0.6] * 5 + [1.0] * 5 + [-0.6] * 5 + [1.0] * 5 + [-0.6] * 5)]
    a = es._finish([es.summarise(spread, "a")])[0]
    b = es._finish([es.summarise(clumped, "b")])[0]
    assert a["avg_r"] == b["avg_r"] and b["days"] == 6
    assert b["ci"] > 2 * a["ci"]


def test_too_few_distinct_days_is_never_a_verdict():
    rows = [sig(d // 4, 0.5 + 0.01 * d) for d in range(4 * (es.MIN_DAYS - 1))]
    r = es._finish([es.summarise(rows, "x")])[0]
    assert r["n"] >= es.MIN_SAMPLE and r["days"] == es.MIN_DAYS - 1
    assert r["verdict"] == "too few"


def test_net_is_judged_and_gross_and_costs_are_reported():
    rows = [sig(d, 0.05) for d in range(30)]
    r = es._finish([es.summarise(rows, "x")])[0]
    assert r["avg_r"] == 0.05 and r["avg_gross_r"] == 0.15 and r["avg_cost_r"] == 0.1


def test_unscored_rows_are_open_not_zero():
    rows = [sig(d, 0.2) for d in range(3)] + [{"signal_date": date(2026, 7, 9), "r_net": None,
                                               "r_multiple": None, "cost_r": None, "outcome": None}]
    s = es.summarise(rows, "x")
    assert s["n"] == 3 and s["still_open"] == 1 and s["avg_r"] == 0.2


def test_one_day_of_signals_has_no_interval():
    s = es._finish([es.summarise([sig(0, 0.5), sig(0, 0.7)], "x")])[0]
    assert s["ci"] is None and s["verdict"] == "too few"
