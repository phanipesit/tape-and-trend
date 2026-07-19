import numpy as np
import pandas as pd
from app.services.indicators import sma, ema, rsi, atr, bollinger, enrich

def test_sma_known_values():
    s = pd.Series([1.0, 2.0, 3.0, 4.0, 5.0])
    out = sma(s, 3)
    assert np.isnan(out.iloc[1])
    assert out.iloc[2] == 2.0
    assert out.iloc[4] == 4.0

def test_ema_converges_to_constant():
    out = ema(pd.Series([50.0] * 100), 20)
    assert abs(out.iloc[-1] - 50.0) < 1e-9

def test_rsi_bounds_and_direction():
    up = rsi(pd.Series(np.linspace(100, 200, 60)))
    dn = rsi(pd.Series(np.linspace(200, 100, 60)))
    assert 0 <= up.iloc[-1] <= 100 and 0 <= dn.iloc[-1] <= 100
    assert up.iloc[-1] > 70          # persistent gains -> overbought
    assert dn.iloc[-1] < 30          # persistent losses -> oversold

def test_atr_positive_and_scales_with_range(make_df):
    calm = atr(make_df([100] * 50, highs=[100.5] * 50, lows=[99.5] * 50))
    wild = atr(make_df([100] * 50, highs=[105] * 50, lows=[95] * 50))
    assert calm.iloc[-1] > 0
    assert wild.iloc[-1] > calm.iloc[-1] * 5

def test_bollinger_ordering():
    s = pd.Series(np.linspace(100, 120, 60) + np.sin(np.arange(60)))
    up, mid, lo = bollinger(s)
    assert up.iloc[-1] > mid.iloc[-1] > lo.iloc[-1]

def test_enrich_columns_present(make_df):
    e = enrich(make_df(np.linspace(100, 150, 250)))
    for col in ("ema20", "ema50", "sma200", "rsi14", "macd_h",
                "bb_up", "bb_lo", "atr14", "vol20", "hi20", "lo20"):
        assert col in e.columns, col
        assert not np.isnan(e[col].iloc[-1]), col

def test_hi20_lo20_exclude_current_bar(make_df):
    # a huge spike on the last bar must not raise its own breakout level
    closes = [100.0] * 60
    highs = [101.0] * 59 + [150.0]
    e = enrich(make_df(closes, highs=highs))
    assert e["hi20"].iloc[-1] == 101.0   # prior bars only — no lookahead
