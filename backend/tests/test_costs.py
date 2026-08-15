"""Indian transaction-cost schedule. Pure arithmetic — no DB, no network."""
import pytest

from app.services import costs


def test_delivery_round_trip_is_about_22bps():
    # The number that decides whether a near-zero strategy is positive or negative.
    c = costs.india_costs(100_000, "delivery")
    assert 0.20 < c["total_pct"] < 0.25


def test_delivery_stt_is_charged_on_both_sides():
    c = costs.india_costs(100_000, "delivery")
    assert c["stt"] == pytest.approx(200.0)      # 0.1% buy + 0.1% sell


def test_intraday_stt_is_sell_side_only():
    c = costs.india_costs(100_000, "intraday")
    assert c["stt"] == pytest.approx(25.0)       # 0.025% on sell alone


def test_intraday_is_cheaper_than_delivery():
    # Entirely because delivery STT is 8x intraday's and charged twice.
    assert (costs.india_costs(100_000, "intraday")["total_pct"]
            < costs.india_costs(100_000, "delivery")["total_pct"])


def test_gst_is_not_charged_on_stt_or_stamp_duty():
    """Taxing the tax is the classic error in a home-grown cost model."""
    c = costs.india_costs(100_000, "intraday")
    expected = (c["brokerage"] + c["exchange"]) * costs.GST_RATE
    assert c["gst"] == pytest.approx(expected, abs=0.01)   # both sides are paise-rounded
    assert c["gst"] < c["stt"]


def test_stamp_duty_is_buy_side_only():
    c = costs.india_costs(100_000, "delivery")
    assert c["stamp_duty"] == pytest.approx(15.0)   # 0.015% once, not twice


def test_flat_brokerage_hurts_small_trades_disproportionately():
    # Rs 20/order is invisible on a large trade and punitive on a small one.
    small = costs.india_costs(5_000, "intraday")["total_pct"]
    large = costs.india_costs(500_000, "intraday")["total_pct"]
    assert small > large * 3


def test_delivery_cost_is_scale_invariant():
    # Delivery brokerage is zero, so everything left is proportional to turnover.
    a = costs.india_costs(10_000, "delivery")["total_pct"]
    b = costs.india_costs(1_000_000, "delivery")["total_pct"]
    assert a == pytest.approx(b, rel=1e-9)


def test_us_costs_are_far_below_indian_ones():
    assert costs.round_trip_pct(100_000, "US") < costs.round_trip_pct(100_000, "IN") / 5


@pytest.mark.parametrize("tv", [10_000, 250_000, 1_000_000])
def test_components_sum_to_the_total_exactly(tv):
    """The displayed breakdown must add up — anyone checking by hand will notice a paisa."""
    c = costs.india_costs(tv, "delivery")
    parts = sum(c[k] for k in ("brokerage", "stt", "exchange", "gst", "stamp_duty", "sebi"))
    assert round(parts, 2) == c["total"]


@pytest.mark.parametrize("bad", ["equity", "swing", ""])
def test_unknown_trade_type_is_rejected(bad):
    with pytest.raises(ValueError):
        costs.india_costs(100_000, bad)


def test_non_positive_trade_value_is_rejected():
    with pytest.raises(ValueError):
        costs.india_costs(0)


def test_rates_carry_an_as_of_stamp():
    # Budgets and SEBI circulars move these; a stale schedule must be visible.
    assert costs.india_costs(100_000)["as_of"] == costs.RATES_AS_OF
