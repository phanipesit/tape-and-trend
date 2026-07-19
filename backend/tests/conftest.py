import pandas as pd
import pytest

@pytest.fixture
def make_df():
    """Synthetic daily candles in get_candles() shape: d,o,h,l,c,v."""
    def _make(closes, highs=None, lows=None, vols=None, start="2024-01-02"):
        c = pd.Series([float(x) for x in closes])
        n = len(c)
        return pd.DataFrame({
            "d": pd.bdate_range(start, periods=n).date,
            "o": c,
            "h": pd.Series(highs, dtype=float) if highs is not None else c * 1.01,
            "l": pd.Series(lows, dtype=float) if lows is not None else c * 0.99,
            "c": c,
            "v": pd.Series(vols, dtype=float) if vols is not None else pd.Series([1e6] * n),
        })
    return _make
