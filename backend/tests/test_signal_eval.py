import pandas as pd
from app.services.signal_eval import score_signal, EXPIRE_BARS

def bars(rows):
    """rows = list of (h, l, c) -> forward-walk DataFrame with business dates."""
    d = pd.bdate_range("2026-06-01", periods=len(rows)).date
    return pd.DataFrame([{"d": d[i], "h": h, "l": l, "c": c}
                         for i, (h, l, c) in enumerate(rows)])

def test_long_stop_hit_is_exactly_minus_one_r():
    res = score_signal("LONG", 100, 95, 115, bars([(101, 96, 100), (99, 94, 95)]))
    assert res["outcome"] == "stop_hit"
    assert res["r_multiple"] == -1.0
    assert res["bars_held"] == 2

def test_long_target_hit_r_matches_plan():
    res = score_signal("LONG", 100, 95, 115, bars([(101, 98, 100), (116, 99, 114)]))
    assert res["outcome"] == "target_hit"
    assert res["r_multiple"] == 3.0          # 15 gained / 5 risked
    assert res["exit_price"] == 115

def test_short_stop_hit_is_exactly_minus_one_r():
    res = score_signal("SHORT", 100, 105, 85, bars([(106, 99, 104)]))
    assert res["outcome"] == "stop_hit"
    assert res["r_multiple"] == -1.0         # shorts must lose on a rise

def test_short_target_hit_is_positive():
    res = score_signal("SHORT", 100, 105, 85, bars([(101, 84, 86)]))
    assert res["outcome"] == "target_hit"
    assert res["r_multiple"] == 3.0          # 15 gained / 5 risked, signed for shorts

def test_stop_and_target_same_bar_assumes_stop_first():
    res = score_signal("LONG", 100, 95, 105, bars([(110, 90, 100)]))
    assert res["outcome"] == "stop_hit"
    assert res["r_multiple"] == -1.0

def test_still_open_before_expiry_window():
    quiet = [(101, 99, 100)] * (EXPIRE_BARS - 1)
    assert score_signal("LONG", 100, 90, 120, bars(quiet)) is None

def test_expires_at_window_close_with_signed_r():
    quiet = [(101, 99, 100)] * (EXPIRE_BARS - 1) + [(99, 97, 98)]
    res = score_signal("LONG", 100, 90, 120, bars(quiet))
    assert res["outcome"] == "expired"
    assert res["bars_held"] == EXPIRE_BARS
    assert res["r_multiple"] == -0.2         # drifted 2 against, risk was 10

def test_no_bars_or_zero_risk_stays_open():
    assert score_signal("LONG", 100, 90, 120, bars([])) is None
    assert score_signal("LONG", 100, 100, 120, bars([(101, 99, 100)])) is None
