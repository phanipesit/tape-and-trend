"""FII/DII regime classification. Pure — classify() takes rows and touches nothing."""
import pytest

from app.services import flows


def day(d, fii, dii):
    return {"date": d, "fii": {"net": fii, "buy": 0, "sell": 0},
            "dii": {"net": dii, "buy": 0, "sell": 0}}


def series(pairs, start=1):
    return [day(f"2026-08-{start + i:02d}", f, d) for i, (f, d) in enumerate(pairs)]


# ---------------------------------------------------------------- honesty about history

def test_no_data_says_so():
    r = flows.classify([])
    assert r["days"] == 0 and r["regime"] is None


def test_thin_history_refuses_to_name_a_regime():
    """There is no historical feed to backfill from, so early days really are thin —
    inventing a regime from two points would be the wrong kind of confident."""
    r = flows.classify(series([(500, 300), (400, 200)]))
    assert r["regime"] is None
    assert r["needs"] == flows.STREAK_DAYS
    assert "2 day" in r["verdict"]


def test_daily_numbers_are_reported_even_without_a_regime():
    # The day's flows are still useful on their own.
    r = flows.classify(series([(508.12, 356.4)]))
    assert r["fii"]["net"] == 508.12 and r["dii"]["net"] == 356.4
    assert r["as_of"] == "2026-08-01"


# ---------------------------------------------------------------- regimes

def test_dual_buying():
    r = flows.classify(series([(3000, 2000)] * 6))
    assert r["regime"] == "DUAL BUYING"


def test_dual_selling():
    r = flows.classify(series([(-3000, -2000)] * 6))
    assert r["regime"] == "DUAL SELLING"


def test_dii_absorption_beats_a_bare_fii_seller_label():
    """The distinction that matters: FII selling into DII buying is a floor, not a rout."""
    r = flows.classify(series([(-3000, 2500)] * 6))
    assert r["regime"] == "DII ABSORPTION"
    assert r["absorption_pct"] == pytest.approx(83.3, abs=0.1)


def test_weak_absorption_is_not_a_floor():
    # DII covering only a fifth of the outflow does not cushion anything.
    r = flows.classify(series([(-3000, 600)] * 6))
    assert r["regime"] != "DII ABSORPTION"


def test_sustained_fii_selling():
    # DII drifting -100cr a day is immaterial, so this is an FII story, not a dual one.
    r = flows.classify(series([(-3000, -100)] * 6))
    assert r["regime"] == "FII NET SELLER"


def test_a_trivial_shared_drift_is_not_dual_selling():
    """Six days of -100cr on both sides is a rounding error. Labelling that
    'liquidity withdrawing' is how a warning stops meaning anything."""
    r = flows.classify(series([(-100, -100)] * 6))
    assert r["regime"] != "DUAL SELLING"


def test_mtd_can_trigger_a_regime_without_a_streak():
    # Big month, choppy days: alternating signs means no streak, but MTD still speaks.
    r = flows.classify(series([(6000, 10), (-100, 10), (5000, 10), (-100, 10),
                               (4000, 10), (-100, 10)]))
    assert r["regime"] == "FII NET BUYER"
    assert r["fii"]["mtd"] > flows.MTD_STRONG


def test_choppy_small_flows_are_mixed():
    r = flows.classify(series([(100, -50), (-80, 60), (120, -40), (-90, 30),
                               (60, -20), (-70, 40)]))
    assert r["regime"] == "MIXED"


# ---------------------------------------------------------------- components

def test_streak_is_signed_and_counts_only_the_current_run():
    assert flows._streak([1, 2, -3, -4]) == -2
    assert flows._streak([-1, -2, 3, 4, 5]) == 3
    assert flows._streak([]) == 0
    assert flows._streak([1, 2, 0]) == 0        # a flat day breaks the run


@pytest.mark.parametrize("net,expected", [
    (2500, "significant buy"), (-2500, "significant sell"),
    (1999, "neutral"), (-1999, "neutral"), (0, "neutral"),
])
def test_day_labels_use_the_2000cr_threshold(net, expected):
    assert flows._label(net) == expected


def test_mtd_only_counts_the_current_month():
    rows = [day("2026-07-30", 9999, 0), day("2026-08-03", 100, 0), day("2026-08-04", 200, 0)]
    assert flows.classify(rows)["fii"]["mtd"] == 300


def test_rows_missing_a_side_are_ignored_rather_than_half_counted():
    rows = series([(100, 50)]) + [{"date": "2026-08-02", "fii": None, "dii": None}]
    assert flows.classify(rows)["days"] == 1
