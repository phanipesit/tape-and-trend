import math

import numpy as np
import pandas as pd
import pytest

from app.services import options as opt


# ---- Black-Scholes ----------------------------------------------------------

def test_atm_call_matches_published_value():
    """S=K=100, t=1, vol=20%, r=5% is the textbook case: call ~= 10.45."""
    g = opt.black_scholes(100, 100, 1.0, 0.20, "call", 0.05)
    assert g["premium"] == pytest.approx(10.45, abs=0.01)


def test_put_call_parity():
    """C - P == S - K*exp(-rt). Catches sign and discounting errors that
    eyeballing individual premiums never would."""
    S, K, t, vol, r = 1290.0, 1300.0, 45 / 365, 0.28, 0.065
    c = opt.black_scholes(S, K, t, vol, "call", r)["premium"]
    p = opt.black_scholes(S, K, t, vol, "put", r)["premium"]
    assert c - p == pytest.approx(S - K * math.exp(-r * t), abs=0.02)


def test_premium_rises_with_volatility_and_time():
    lo = opt.black_scholes(100, 100, 0.25, 0.15, "call", 0.05)["premium"]
    hi = opt.black_scholes(100, 100, 0.25, 0.45, "call", 0.05)["premium"]
    long_dated = opt.black_scholes(100, 100, 1.0, 0.15, "call", 0.05)["premium"]
    assert hi > lo and long_dated > lo


def test_deep_otm_call_is_near_worthless_and_deep_itm_tracks_intrinsic():
    otm = opt.black_scholes(100, 200, 0.08, 0.20, "call", 0.05)
    itm = opt.black_scholes(200, 100, 0.08, 0.20, "call", 0.05)
    assert otm["premium"] < 0.05
    assert itm["premium"] == pytest.approx(200 - 100 * math.exp(-0.05 * 0.08), abs=0.5)


def test_premium_is_monotonic_in_strike():
    """Calls get cheaper as the strike rises; puts get dearer. A premium model that
    fails this would produce nonsensical spread break-evens."""
    calls = [opt.black_scholes(100, k, 0.25, 0.3, "call", 0.05)["premium"]
             for k in range(80, 125, 5)]
    puts = [opt.black_scholes(100, k, 0.25, 0.3, "put", 0.05)["premium"]
            for k in range(80, 125, 5)]
    assert all(a > b for a, b in zip(calls, calls[1:]))
    assert all(a < b for a, b in zip(puts, puts[1:]))


def test_expiry_and_zero_vol_degenerate_to_intrinsic():
    for t, vol in ((0.0, 0.3), (0.25, 0.0)):
        assert opt.black_scholes(120, 100, t, vol, "call", 0.05)["premium"] == 20.0
        assert opt.black_scholes(80, 100, t, vol, "put", 0.05)["premium"] == 20.0
        assert opt.black_scholes(80, 100, t, vol, "call", 0.05)["premium"] == 0.0
    # Greeks are undefined there — must be zeroed, not NaN or a division error
    g = opt.black_scholes(120, 100, 0.0, 0.3, "call", 0.05)
    assert g["gamma"] == 0.0 and g["theta"] == 0.0 and g["delta"] == 1.0


# ---- Greeks -----------------------------------------------------------------

def test_delta_bounds_and_sign():
    call = opt.black_scholes(100, 100, 0.25, 0.3, "call", 0.05)
    put = opt.black_scholes(100, 100, 0.25, 0.3, "put", 0.05)
    assert 0.0 < call["delta"] < 1.0
    assert -1.0 < put["delta"] < 0.0


def test_long_options_lose_value_over_time():
    """Theta is negative for long calls and long puts alike."""
    assert opt.black_scholes(100, 100, 0.25, 0.3, "call", 0.05)["theta"] < 0
    assert opt.black_scholes(100, 100, 0.25, 0.3, "put", 0.05)["theta"] < 0


def test_gamma_and_vega_are_positive_and_peak_atm():
    atm = opt.black_scholes(100, 100, 0.25, 0.3, "call", 0.05)
    otm = opt.black_scholes(100, 140, 0.25, 0.3, "call", 0.05)
    assert atm["gamma"] > 0 and atm["vega"] > 0
    assert atm["gamma"] > otm["gamma"] and atm["vega"] > otm["vega"]


def test_delta_matches_numeric_derivative():
    # h must stay well above the 0.01 rounding applied to `premium`, or the central
    # difference measures rounding noise instead of the derivative.
    S, K, t, vol, r, h = 100.0, 105.0, 0.5, 0.25, 0.05, 1.0
    up = opt.black_scholes(S + h, K, t, vol, "call", r)["premium"]
    dn = opt.black_scholes(S - h, K, t, vol, "call", r)["premium"]
    assert opt.black_scholes(S, K, t, vol, "call", r)["delta"] == pytest.approx(
        (up - dn) / (2 * h), abs=0.01)


# ---- Volatility + strategy pricing ------------------------------------------

def test_realized_vol_recovers_a_known_sigma(monkeypatch, make_df):
    """Generate returns with a known daily sigma; the annualised estimate should
    land near sigma*sqrt(252)."""
    rng = np.random.default_rng(0)
    daily = 0.02
    closes = 100 * np.exp(np.cumsum(rng.normal(0, daily, 400)))
    monkeypatch.setattr(opt, "get_candles", lambda s: make_df(closes))
    assert opt.realized_vol("X") == pytest.approx(daily * math.sqrt(252), rel=0.25)


def test_realized_vol_is_clamped(monkeypatch, make_df):
    monkeypatch.setattr(opt, "get_candles", lambda s: make_df([100.0] * 200))
    assert opt.realized_vol("FLAT") == opt.MIN_VOL   # flat history, not zero vol


def test_realized_vol_rejects_short_history(monkeypatch, make_df):
    monkeypatch.setattr(opt, "get_candles", lambda s: make_df([100.0] * 5))
    with pytest.raises(ValueError):
        opt.realized_vol("SHORT")


def _patch_market(monkeypatch, make_df, closes):
    monkeypatch.setattr(opt, "get_candles", lambda s: make_df(closes))
    monkeypatch.setattr(opt, "get_symbol", lambda s: {"symbol": s, "market": "IN"})


def test_price_strategy_nets_a_debit_spread(monkeypatch, make_df):
    rng = np.random.default_rng(1)
    closes = 100 * np.exp(np.cumsum(rng.normal(0, 0.015, 300)))
    _patch_market(monkeypatch, make_df, closes)
    spot = round(float(closes[-1]), 2)

    out = opt.price_strategy("X", [
        {"type": "call", "strike": spot, "qty": 1},
        {"type": "call", "strike": spot * 1.06, "qty": -1},
    ], days=30)

    assert out["spot"] == spot and out["days"] == 30
    assert out["legs"][0]["premium"] > out["legs"][1]["premium"]   # lower strike costs more
    assert out["net_premium"] > 0                                  # bull call spread is a debit
    assert 0 < out["position"]["delta"] < 1                        # capped long exposure
    assert out["rate"] == opt.RISK_FREE["IN"]


def test_short_leg_flips_greek_signs(monkeypatch, make_df):
    rng = np.random.default_rng(2)
    closes = 100 * np.exp(np.cumsum(rng.normal(0, 0.015, 300)))
    _patch_market(monkeypatch, make_df, closes)
    spot = float(closes[-1])
    short = opt.price_strategy("X", [{"type": "call", "strike": spot, "qty": -1}], days=30)
    assert short["net_premium"] < 0            # credit received
    assert short["position"]["delta"] < 0      # short call is short delta
    assert short["position"]["theta"] > 0      # and collects time decay


def test_straddle_is_delta_neutral_ish(monkeypatch, make_df):
    rng = np.random.default_rng(3)
    closes = 100 * np.exp(np.cumsum(rng.normal(0, 0.015, 300)))
    _patch_market(monkeypatch, make_df, closes)
    spot = float(closes[-1])
    out = opt.price_strategy("X", [{"type": "call", "strike": spot, "qty": 1},
                                   {"type": "put", "strike": spot, "qty": 1}], days=30)
    assert abs(out["position"]["delta"]) < 0.25
    assert out["position"]["vega"] > 0          # long vol


def test_price_strategy_rejects_empty_legs(monkeypatch, make_df):
    _patch_market(monkeypatch, make_df, [100.0] * 200)
    with pytest.raises(ValueError):
        opt.price_strategy("X", [], days=30)


# ---------------------------------------------------------------- implied vol wiring

def test_each_leg_prices_on_its_own_implied_vol(monkeypatch):
    """The reason IV was added: one realized number priced both wings at zero."""
    monkeypatch.setattr(opt, "get_symbol", lambda s: {"market": "IN"})
    monkeypatch.setattr(opt, "get_candles",
                        lambda s, **k: pd.DataFrame({"c": [24550.0] * 80}))
    monkeypatch.setattr(opt, "realized_vol", lambda s, lookback=60: 0.1228)

    ivs = {(23000.0, "put"): 0.4999, (24550.0, "call"): 0.1259, (25500.0, "call"): 0.2927}
    monkeypatch.setattr(opt, "implied_vol",
                        lambda sym, strike, kind, days: (
                            {"vol": ivs[(strike, kind)], "iv_pct": ivs[(strike, kind)] * 100,
                             "strike_used": strike, "expiry": "2026-08-04", "expiry_days": 1,
                             "ltp": 1.2, "fetched_at": "x"}
                            if (strike, kind) in ivs else None))

    r = opt.price_strategy("^NSEI", [
        {"type": "put", "strike": 23000, "qty": 1},
        {"type": "call", "strike": 24550, "qty": 1},
        {"type": "call", "strike": 25500, "qty": -1}], days=1)

    assert r["vol_source"] == "implied" and r["legs_implied"] == 3
    assert [L["vol_source"] for L in r["legs"]] == ["implied"] * 3
    # Wings must carry their own vol, not the at-the-money one.
    assert r["legs"][0]["vol_pct"] == 49.99
    assert r["legs"][2]["vol_pct"] == 29.27
    # And therefore must not price at zero, which realized vol did.
    assert r["legs"][0]["premium"] > 0 and r["legs"][2]["premium"] > 0


def test_falls_back_to_realized_per_leg(monkeypatch):
    monkeypatch.setattr(opt, "get_symbol", lambda s: {"market": "IN"})
    monkeypatch.setattr(opt, "get_candles",
                        lambda s, **k: pd.DataFrame({"c": [100.0] * 80}))
    monkeypatch.setattr(opt, "realized_vol", lambda s, lookback=60: 0.20)
    # Only the 100 strike is quoted; the 120 wing is not.
    monkeypatch.setattr(opt, "implied_vol",
                        lambda sym, strike, kind, days: (
                            {"vol": 0.3, "iv_pct": 30.0, "strike_used": 100.0,
                             "expiry": "2026-08-04", "expiry_days": 1, "ltp": 5.0,
                             "fetched_at": "x"} if strike == 100 else None))

    r = opt.price_strategy("^NSEI", [{"type": "call", "strike": 100, "qty": 1},
                                          {"type": "call", "strike": 120, "qty": 1}], days=30)
    assert r["vol_source"] == "mixed" and r["legs_implied"] == 1
    assert r["legs"][0]["vol_pct"] == 30.0 and r["legs"][0]["vol_source"] == "implied"
    assert r["legs"][1]["vol_pct"] == 20.0 and r["legs"][1]["vol_source"] == "realized"


def test_use_implied_false_prices_everything_on_realized(monkeypatch):
    monkeypatch.setattr(opt, "get_symbol", lambda s: {"market": "IN"})
    monkeypatch.setattr(opt, "get_candles",
                        lambda s, **k: pd.DataFrame({"c": [100.0] * 80}))
    monkeypatch.setattr(opt, "realized_vol", lambda s, lookback=60: 0.20)
    def should_not_run(*a, **k):
        raise AssertionError("implied_vol must not be consulted when use_implied=False")
    monkeypatch.setattr(opt, "implied_vol", should_not_run)

    r = opt.price_strategy("^NSEI", [{"type": "call", "strike": 100, "qty": 1}],
                                days=30, use_implied=False)
    assert r["vol_source"] == "realized" and r["chain"] is None


def test_expiry_mismatch_is_flagged(monkeypatch):
    """IV from a 1-day contract applied to a 30-day model describes a different thing."""
    monkeypatch.setattr(opt, "get_symbol", lambda s: {"market": "IN"})
    monkeypatch.setattr(opt, "get_candles",
                        lambda s, **k: pd.DataFrame({"c": [100.0] * 80}))
    monkeypatch.setattr(opt, "realized_vol", lambda s, lookback=60: 0.20)
    monkeypatch.setattr(opt, "implied_vol",
                        lambda sym, strike, kind, days: {
                            "vol": 0.3, "iv_pct": 30.0, "strike_used": 100.0,
                            "expiry": "2026-08-04", "expiry_days": 1, "ltp": 5.0,
                            "fetched_at": "x"})
    near = opt.price_strategy("^NSEI", [{"type": "call", "strike": 100, "qty": 1}], days=1)
    far = opt.price_strategy("^NSEI", [{"type": "call", "strike": 100, "qty": 1}], days=30)
    assert near["expiry_mismatch"] is False
    assert far["expiry_mismatch"] is True
