from datetime import datetime, timedelta, timezone
import numpy as np
import pandas as pd
from app.services.indicators import enrich_intraday
from app.services.intraday_signals import analyse_df, INTRADAY_STOP_ATR, INTRADAY_TARGET_ATR

def make_intraday(closes, vols=None, bars_per_session=30, interval_minutes=5, vol=0.001):
    """Multiple sessions of 5-min bars. Symmetric h/l around c makes the typical price
    (h+l+c)/3 exactly equal to c, which keeps VWAP arithmetic easy to reason about in tests."""
    n = len(closes)
    ts = []
    day = 0
    while len(ts) < n:
        session_start = datetime(2026, 1, 2, 3, 45, tzinfo=timezone.utc) + timedelta(days=day)
        for b in range(bars_per_session):
            if len(ts) >= n:
                break
            ts.append(session_start + timedelta(minutes=interval_minutes * b))
        day += 1
    c = np.array(closes, dtype=float)
    h, l = c * (1 + vol), c * (1 - vol)
    v = np.array(vols, dtype=float) if vols is not None else np.full(n, 1e5)
    return pd.DataFrame({"ts": pd.to_datetime(ts, utc=True), "o": c, "h": h, "l": l, "c": c, "v": v})

def tags(res):
    return [s["tag"] for s in res["signals"]]

def test_not_enough_history():
    df = make_intraday([100.0] * 20)
    res = analyse_df(df, "X")
    assert res["error"] == "not enough intraday history"

def test_vwap_resets_each_session():
    closes = [100.0] * 15 + [200.0] * 15   # two 15-bar sessions at very different levels
    df = make_intraday(closes, bars_per_session=15)
    e = enrich_intraday(df, interval="5m")
    assert abs(e["vwap"].iloc[14] - 100.0) < 1e-6     # last bar of session 1
    assert abs(e["vwap"].iloc[15] - 200.0) < 1e-6     # first bar of session 2 -> reset, not blended

def test_opening_range_does_not_leak_later_bars():
    # first 3 bars (15min at 5min/bar) make the highs 101,102,103; a much bigger
    # high shows up later in the same session and must not affect or_hi
    closes = [100.0] * 25
    highs = [101.0, 102.0, 103.0] + [104.0] * 4 + [150.0] + [104.0] * 17
    df = make_intraday(closes, bars_per_session=25)
    df["h"] = highs
    e = enrich_intraday(df, interval="5m", or_minutes=15)
    assert (e["or_hi"] == 103.0).all()

def test_vwap_reclaim_fires(): # noqa
    closes = [95.0] * 29 + [105.0]
    df = make_intraday(closes, bars_per_session=30)
    res = analyse_df(df, "X")
    assert "vwap_reclaim" in tags(res)

def test_or_breakout_fires_on_volume():
    closes = [100.0] * 29 + [110.0]
    vols = [1e5] * 29 + [3e5]   # well above 1.4x the trailing 20-bar average
    df = make_intraday(closes, vols=vols, bars_per_session=30)
    res = analyse_df(df, "X")
    assert "or_breakout" in tags(res)
    assert res["direction"] == "LONG"

def test_or_breakout_needs_volume():
    closes = [100.0] * 29 + [110.0]
    df = make_intraday(closes, bars_per_session=30)   # flat volume -> no breakout signal
    res = analyse_df(df, "X")
    assert "or_breakout" not in tags(res)

def test_ema_cross_up_fires_on_cross_bar():
    closes = list(200 * 0.99 ** np.arange(40)) + list(np.array(200 * 0.99 ** 39) * 1.02 ** np.arange(1, 21))
    df = make_intraday(closes, bars_per_session=60)
    e = enrich_intraday(df, interval="5m")
    ema9, ema20 = e["ema9"].to_numpy(), e["ema20"].to_numpy()
    cross = [k for k in range(21, len(e)) if ema9[k - 1] <= ema20[k - 1] and ema9[k] > ema20[k]]
    assert cross, "test construction should produce a cross"
    res = analyse_df(df.iloc[:cross[0] + 1], "X")
    assert "ema_cross_up" in tags(res)

def test_stop_target_use_intraday_atr_multiples():
    closes = list(100 + 0.05 * np.sin(np.arange(40)))
    df = make_intraday(closes, bars_per_session=40)
    res = analyse_df(df, "X")
    a = res["atr"]
    if res["direction"] == "LONG":
        assert abs(res["stop"] - (res["entry"] - INTRADAY_STOP_ATR * a)) < 1e-6
        assert abs(res["target"] - (res["entry"] + INTRADAY_TARGET_ATR * a)) < 1e-6
    else:
        assert abs(res["stop"] - (res["entry"] + INTRADAY_STOP_ATR * a)) < 1e-6
        assert abs(res["target"] - (res["entry"] - INTRADAY_TARGET_ATR * a)) < 1e-6

def test_index_like_zero_volume_gives_no_vwap_and_no_volume_signals():
    closes = [100.0] * 29 + [105.0]   # would fire vwap_reclaim if vwap were defined
    df = make_intraday(closes, vols=[0.0] * 30, bars_per_session=30)
    res = analyse_df(df, "X")
    assert res["vwap"] is None
    assert "vwap_reclaim" not in tags(res)
    assert res["rvol"] == 1.0   # falls back cleanly instead of dividing by zero


# ---------------------------------------------------------------- staleness

def last_ts(df):
    return df["ts"].iloc[-1].to_pydatetime()


def test_fresh_bar_during_an_open_session_is_not_stale():
    df = make_intraday([100.0 + i * 0.1 for i in range(40)])
    res = analyse_df(df, "X", now=last_ts(df) + timedelta(minutes=4), venue_open=True)
    assert res["stale"] is False
    assert res["bar_age_minutes"] == 4.0


def test_old_bar_during_an_open_session_is_stale():
    # Three missed 5m bars while the venue is open means the feed is dead, which is
    # exactly how HDFCBANK served Friday's bars as if they were live.
    df = make_intraday([100.0 + i * 0.1 for i in range(40)])
    res = analyse_df(df, "X", now=last_ts(df) + timedelta(minutes=20), venue_open=True)
    assert res["stale"] is True


def test_old_bar_while_the_venue_is_shut_is_not_stale():
    # The weekend guard: Friday's close on a Sunday is not a dead feed.
    df = make_intraday([100.0 + i * 0.1 for i in range(40)])
    res = analyse_df(df, "X", now=last_ts(df) + timedelta(days=2), venue_open=False)
    assert res["stale"] is False
    assert res["bar_age_minutes"] > 2000


def test_unknown_venue_state_never_claims_stale_but_still_reports_age():
    df = make_intraday([100.0 + i * 0.1 for i in range(40)])
    res = analyse_df(df, "X", now=last_ts(df) + timedelta(minutes=99), venue_open=None)
    assert res["stale"] is False
    assert res["bar_age_minutes"] == 99.0


def test_stale_threshold_scales_with_the_interval():
    df = make_intraday([100.0 + i * 0.1 for i in range(40)], interval_minutes=15)
    fresh = analyse_df(df, "X", interval="15m", now=last_ts(df) + timedelta(minutes=40),
                       venue_open=True)
    dead = analyse_df(df, "X", interval="15m", now=last_ts(df) + timedelta(minutes=50),
                      venue_open=True)
    assert fresh["stale"] is False and dead["stale"] is True
