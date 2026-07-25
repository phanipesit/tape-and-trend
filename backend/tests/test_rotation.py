import numpy as np
import pandas as pd
import pytest
from app.services import rotation

N = 320   # comfortably past the 201-day warmup (max(200,100,momentum_days)+1)

def series(kind, n=N, gap_at=None, vol=0.01):
    """Build a (h,l,c) triple of numpy arrays for one synthetic symbol."""
    if kind == "up":
        c = 100 * 1.01 ** np.arange(n)
    elif kind == "flat":
        c = 100 + 0.01 * np.sin(np.arange(n) / 5)   # goes nowhere -> fails close>sma100 eventually
    elif kind == "down":
        c = 100 * 0.999 ** np.arange(n)   # steady decline -> reliably below its own trailing 200-day SMA
    else:
        raise ValueError(kind)
    c = c.astype(float)
    if gap_at is not None:
        c[gap_at:] *= 1.25   # a single day's 25% jump, carried forward
    h, l = c * (1 + vol), c * (1 - vol)
    return h, l, c

def fillers(n=N, count=4):
    """Flat, unremarkable symbols padding the universe past the >=5 minimum
    without threatening to outrank whatever the test is actually checking."""
    return {f"FILL{i}": series("flat", n=n) for i in range(count)}

@pytest.fixture
def env(monkeypatch):
    """Wire rotation.py's data-layer calls to synthetic universes/index."""
    state = {}

    def _setup(symbols: dict, index_kind="up", n=N):
        dates = pd.bdate_range("2024-01-02", periods=n).date
        state["dates"] = dates
        meta = [{"symbol": s, "market": "IN"} for s in symbols]
        monkeypatch.setattr(rotation, "all_symbols", lambda market: meta)
        monkeypatch.setattr(rotation, "get_index_symbol", lambda market: "IDX")

        idx_h, idx_l, idx_c = series(index_kind, n=n)
        idx_df = pd.DataFrame({"d": dates, "o": idx_c, "h": idx_h, "l": idx_l,
                               "c": idx_c, "v": [1e6] * n})
        real_get_candles = rotation.get_candles
        def fake_get_candles(sym, auto=True):
            assert sym == "IDX"
            return idx_df
        monkeypatch.setattr(rotation, "get_candles", fake_get_candles)

        rows = []
        for sym, (h, l, c) in symbols.items():
            for i, d in enumerate(dates):
                rows.append({"symbol": sym, "d": d, "h": h[i], "l": l[i], "c": c[i]})
        def fake_q(sql, **kw):
            if sql.strip().upper().startswith("SELECT"):
                return rows
            return []   # swallow the INSERT INTO rotation_runs
        monkeypatch.setattr(rotation, "q", fake_q)
        return real_get_candles
    return _setup

def test_strong_uptrend_beats_flat_laggard(env):
    env({"LEADER": series("up"), "LAGGARD": series("flat"), **fillers()})
    out = rotation.run("IN", {"top_n": 1, "momentum_days": 30, "rebalance_days": 5})
    assert "error" not in out
    picked = {t["symbol"] for t in out["trades"]}
    assert "LEADER" in picked
    assert "LAGGARD" not in picked

def test_gap_filter_blocks_the_only_candidate(env):
    # a short window (warmup 201 through day 229, 6 rebalances) with a single
    # candidate whose one big jump at day 170 sits inside every rebalance's
    # trailing 90-day momentum window ([112,201] through [137,226]) - so gap_ok
    # is False at every rebalance in range and nothing should ever get bought
    n = 230
    env({"GAPPY": series("up", n=n, gap_at=170), **fillers(n=n)}, n=n)
    out = rotation.run("IN", {"top_n": 1, "momentum_days": 90, "rebalance_days": 5})
    assert "error" not in out
    assert "GAPPY" not in {t["symbol"] for t in out["trades"]}

def test_regime_off_blocks_all_new_entries(env):
    # index in a persistent downtrend, always below its own 200-day SMA
    env({"LEADER": series("up"), **fillers()}, index_kind="down")
    out = rotation.run("IN", {"top_n": 1, "momentum_days": 30, "rebalance_days": 5})
    assert "error" not in out
    assert out["n_trades"] == 0

def test_atr_sizing_scales_inversely_with_volatility(env):
    lo_h, lo_l, lo_c = series("up", vol=0.003)
    hi_h, hi_l, hi_c = series("up", vol=0.05)
    env({"LOWVOL": (lo_h, lo_l, lo_c), "HIGHVOL": (hi_h, hi_l, hi_c), **fillers()})
    out = rotation.run("IN", {"top_n": 2, "momentum_days": 30, "rebalance_days": 5})
    assert "error" not in out
    lo_qty = next(t["qty"] for t in out["trades"] if t["symbol"] == "LOWVOL")
    hi_qty = next(t["qty"] for t in out["trades"] if t["symbol"] == "HIGHVOL")
    assert lo_qty > hi_qty   # smaller ATR -> larger risk-parity position

def test_not_enough_symbols_errors(env):
    env({"ONLYONE": series("up")})
    out = rotation.run("IN", {})
    assert "not enough symbols" in out["error"]

def test_unknown_market_errors(env):
    env({"A": series("up")})
    assert "unknown market" in rotation.run("XX", {})["error"]
