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
