import numpy as np
import pytest
from app.services import backtest

@pytest.fixture
def offline(monkeypatch, make_df):
    """Feed the backtester synthetic candles and swallow the DB write."""
    def _with(closes, vols=None, highs=None, lows=None):
        df = make_df(closes, vols=vols, highs=highs, lows=lows)
        monkeypatch.setattr(backtest, "get_candles", lambda s: df)
        monkeypatch.setattr(backtest, "q", lambda *a, **k: [])
        return df
    return _with

def test_not_enough_history(offline):
    offline([100] * 50)
    assert backtest.run("T", "emax", {})["error"] == "not enough history"

def test_unknown_strategy(offline):
    offline([100] * 300)
    assert "unknown strategy" in backtest.run("T", "nope", {})["error"]

def test_emax_trades_a_cycle(offline):
    up = list(100 * 1.01 ** np.arange(150))
    down = list(up[-1] * 0.99 ** np.arange(1, 151))
    df = offline(down + up + down)   # fall -> rally -> fall forces a round trip
    out = backtest.run("T", "emax", {})
    assert out["n_trades"] >= 1
    assert len(out["curve"]) == len(df) - 1
    assert len(out["dates"]) == len(out["curve"])
    assert out["final"] > 0

def test_buy_hold_benchmark_math(offline):
    closes = list(np.linspace(100, 150, 300))
    offline(closes)
    out = backtest.run("T", "rsi", {})
    assert abs(out["buy_hold"] - 50.0) < 0.01

def test_costs_reduce_returns(offline):
    closes = list(100 * 1.01 ** np.arange(150)) + list((100 * 1.01 ** 149) * 0.99 ** np.arange(1, 151))
    offline(closes * 1)
    cheap = backtest.run("T", "emax", {"fee_bps": 0, "slip_bps": 0})
    costly = backtest.run("T", "emax", {"fee_bps": 50, "slip_bps": 50})
    assert cheap["n_trades"] == costly["n_trades"]
    assert cheap["final"] > costly["final"]

def test_signal_strategy_runs_with_shared_thresholds(offline):
    rng = np.random.default_rng(7)
    closes = list(100 * np.cumprod(1 + rng.normal(0.0005, 0.015, 400)))
    offline(closes, vols=list(rng.uniform(0.5e6, 3e6, 400)))
    out = backtest.run("T", "signal", {})
    assert "error" not in out
    assert out["final"] > 0
    assert np.isfinite(out["sharpe"])

def test_max_drawdown_bounds(offline):
    closes = list(100 * 1.005 ** np.arange(200)) + list((100 * 1.005 ** 199) * 0.98 ** np.arange(1, 101))
    offline(closes)
    out = backtest.run("T", "macd", {})
    assert 0 <= out["max_drawdown"] <= 100

def test_rsi2_buys_dip_above_trend_and_exits_on_reversion(offline):
    # long, gentle uptrend so sma200 sits well below price, then a sharp one-day
    # drop tanks the 2-period RSI while price stays above the 200-day average,
    # then an immediate bounce should trip the 5-day-SMA exit soon after
    closes = list(100 * 1.002 ** np.arange(220))
    dip = closes[-1] * 0.90
    closes += [dip]
    closes += list(dip * 1.01 ** np.arange(1, 10))   # sharp bounce
    offline(closes)
    out = backtest.run("T", "rsi2", {"rsi2_buy": 5})
    assert "error" not in out
    assert out["n_trades"] >= 1
    assert out["trades"][0]["ret"] > 0    # bought the dip, sold into the bounce

def test_rsi2_no_trade_below_200sma(offline):
    # a straight, gentle downtrend keeps price under its 200-day average for the
    # whole series, so the trend filter should block every entry
    closes = list(100 * 0.999 ** np.arange(260))
    offline(closes)
    out = backtest.run("T", "rsi2", {"rsi2_buy": 50})   # a lax RSI threshold to isolate the trend filter
    assert out["n_trades"] == 0

def test_donchian_breakout_entry_and_breakdown_exit(offline):
    # flat range, then a clean breakout above the 20-day high, then a slide
    # through the 10-day low should open and close exactly one trade
    flat = [100.0] * 80
    breakout = [100 + i for i in range(1, 16)]      # steadily makes new 20d highs
    slide = [breakout[-1] - i for i in range(1, 15)]  # then gives it all back
    closes = flat + breakout + slide
    highs = [c * 1.001 for c in closes]
    lows = [c * 0.999 for c in closes]
    offline(closes, highs=highs, lows=lows)
    out = backtest.run("T", "donchian", {"entry_days": 20, "exit_days": 10})
    assert "error" not in out
    assert out["n_trades"] >= 1

def test_donchian_no_breakout_no_trade(offline):
    closes = [100 + 0.01 * i for i in range(300)]   # drifts up slowly, never a clean 20d high break
    offline(closes)
    out = backtest.run("T", "donchian", {"entry_days": 20, "exit_days": 10})
    assert out["n_trades"] == 0
