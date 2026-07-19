import numpy as np
from app.services.indicators import enrich
from app.services.signals import analyse_df, STOP_ATR, TARGET_ATR

def tags(res):
    return [s["tag"] for s in res["signals"]]

def test_not_enough_history(make_df):
    res = analyse_df(make_df([100] * 30), "X")
    assert res["error"] == "not enough history"

def test_quiet_market_no_signals_default_long_plan(make_df):
    # gentle drift, no extremes: no rules fire, score 0, but a plan still exists
    closes = 100 + 0.1 * np.sin(np.arange(120) / 3)
    res = analyse_df(make_df(closes), "X")
    assert res["signals"] == []
    assert res["score"] == 0.0
    assert res["direction"] == "LONG"          # documented default so risk calc always loads
    assert res["stop"] < res["entry"] < res["target"]
    assert res["entry"] == res["close"]

def test_breakout_20d_fires_on_volume(make_df):
    closes = list(100 + 0.1 * np.sin(np.arange(99))) + [112.0]
    vols = [1e6] * 99 + [2.5e6]
    res = analyse_df(make_df(closes, vols=vols), "X")
    assert "breakout_20d" in tags(res)
    assert res["direction"] == "LONG"

def test_breakout_needs_volume(make_df):
    closes = list(100 + 0.1 * np.sin(np.arange(99))) + [112.0]
    res = analyse_df(make_df(closes), "X")   # flat volume -> no breakout signal
    assert "breakout_20d" not in tags(res)

def test_breakdown_20d_fires_and_plan_is_short(make_df):
    closes = list(100 + 0.1 * np.sin(np.arange(95))) + [100, 97, 94, 91, 85]
    res = analyse_df(make_df(closes), "X")
    assert "breakdown_20d" in tags(res)
    assert res["direction"] == "SHORT"
    assert res["stop"] > res["entry"] > res["target"]
    a = res["atr"]
    assert abs(res["stop"] - (res["close"] + STOP_ATR * a)) < 1e-9
    assert abs(res["target"] - (res["close"] - TARGET_ATR * a)) < 1e-9

def test_rsi_pullback_in_uptrend(make_df):
    # long uptrend keeps price above sma200, then a sharp multi-day drop tanks RSI
    closes = list(100 * 1.004 ** np.arange(250))
    for _ in range(8):
        closes.append(closes[-1] * 0.97)
    res = analyse_df(make_df(closes), "X")
    assert res["rsi"] < 32
    assert res["trend"] == "UP"
    assert "rsi_pullback" in tags(res)

def test_ema_cross_up_fires_on_cross_bar(make_df):
    # downtrend then recovery; find the exact bar where ema20 crosses ema50
    closes = list(200 * 0.995 ** np.arange(120)) + list(np.array(200 * 0.995 ** 119) * 1.01 ** np.arange(1, 61))
    df = make_df(closes)
    e = enrich(df)
    e20, e50 = e["ema20"].to_numpy(), e["ema50"].to_numpy()
    cross = [i for i in range(61, len(e)) if e20[i - 1] <= e50[i - 1] and e20[i] > e50[i]]
    assert cross, "test construction should produce a cross"
    res = analyse_df(df.iloc[:cross[0] + 1], "X")
    assert "ema_cross_up" in tags(res)

def test_score_positive_when_rules_fire(make_df):
    # sharp breakdown: SELL (2pts each) + possibly WATCH (1pt) signals, never BUYs;
    # score = |buy-sell| + watch + rvol bonus (capped 3), so it must exceed 2
    closes = list(100 + 0.1 * np.sin(np.arange(95))) + [100, 97, 94, 91, 85]
    res = analyse_df(make_df(closes), "X")
    assert res["signals"] and not any(s["type"] == "BUY" for s in res["signals"])
    sells = sum(1 for s in res["signals"] if s["type"] == "SELL")
    watches = sum(1 for s in res["signals"] if s["type"] == "WATCH")
    assert 2 < res["score"] <= 2 * sells + watches + 3 + 1e-9
