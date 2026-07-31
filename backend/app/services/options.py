"""Black-Scholes pricing and Greeks for the options lab.

Premiums used to be fixed percentages of spot on the frontend (a long call was always
3% of spot), so strike distance, time to expiry, and volatility never entered the
numbers — the payoff *shape* was right but every break-even, max-profit and max-loss
level was arbitrary. Those levels are what the AI analysis reasons over, so they have
to be model-derived rather than invented.

Volatility comes from the underlying's own cached daily candles (realized vol), not a
live option chain — we have no IV feed. That makes these *theoretical* prices: right
order of magnitude and correctly shaped across strikes, but not broker quotes.
"""
import math

import numpy as np

from .data import get_candles, get_symbol

RISK_FREE = {"IN": 0.065, "US": 0.043}   # ~10y sovereign yields; a payoff lab needs no term structure
TRADING_DAYS = 252
VOL_LOOKBACK = 60          # ~3 months of sessions: recent enough to reflect the current regime
MIN_VOL, MAX_VOL = 0.05, 2.0   # a degenerate history must not produce absurd premiums


def _cdf(x: float) -> float:
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


def _pdf(x: float) -> float:
    return math.exp(-0.5 * x * x) / math.sqrt(2.0 * math.pi)


def realized_vol(symbol: str, lookback: int = VOL_LOOKBACK) -> float:
    """Annualised stdev of daily log returns — our stand-in for implied vol."""
    c = get_candles(symbol)["c"].tail(lookback + 1)
    if len(c) < 20:
        raise ValueError(f"{symbol}: not enough history to estimate volatility")
    lr = np.diff(np.log(c.to_numpy(dtype=float)))
    return float(np.clip(lr.std(ddof=1) * math.sqrt(TRADING_DAYS), MIN_VOL, MAX_VOL))


def black_scholes(S: float, K: float, t: float, vol: float, kind: str, r: float) -> dict:
    """Price + Greeks for one European option. `t` is in years.

    At expiry (or zero vol) the model degenerates to intrinsic value, where the Greeks
    are undefined — return intrinsic with delta stepped 0/1 and the rest zeroed rather
    than dividing by zero.
    """
    call = kind == "call"
    if t <= 0 or vol <= 0:
        intrinsic = max(S - K, 0.0) if call else max(K - S, 0.0)
        itm = (S > K) if call else (S < K)
        return {"premium": round(intrinsic, 2),
                "delta": round((1.0 if call else -1.0) if itm else 0.0, 4),
                "gamma": 0.0, "theta": 0.0, "vega": 0.0, "rho": 0.0}

    sqrt_t = math.sqrt(t)
    d1 = (math.log(S / K) + (r + 0.5 * vol * vol) * t) / (vol * sqrt_t)
    d2 = d1 - vol * sqrt_t
    disc = math.exp(-r * t)

    if call:
        premium = S * _cdf(d1) - K * disc * _cdf(d2)
        delta = _cdf(d1)
        theta = -S * _pdf(d1) * vol / (2 * sqrt_t) - r * K * disc * _cdf(d2)
        rho = K * t * disc * _cdf(d2)
    else:
        premium = K * disc * _cdf(-d2) - S * _cdf(-d1)
        delta = _cdf(d1) - 1.0
        theta = -S * _pdf(d1) * vol / (2 * sqrt_t) + r * K * disc * _cdf(-d2)
        rho = -K * t * disc * _cdf(-d2)

    return {
        "premium": round(premium, 2),
        "delta": round(delta, 4),
        "gamma": round(_pdf(d1) / (S * vol * sqrt_t), 6),
        "theta": round(theta / 365.0, 4),          # per calendar day, as traders quote it
        "vega": round(S * _pdf(d1) * sqrt_t / 100.0, 4),   # per 1 percentage point of vol
        "rho": round(rho / 100.0, 4),
    }


def price_strategy(symbol: str, legs: list[dict], days: int = 30) -> dict:
    """Theoretical premium + Greeks per leg, plus position totals.

    `legs` are {type, strike, qty} — qty>0 long, qty<0 short. Position Greeks are
    qty-weighted so a spread nets out the way the actual position would.
    """
    if not legs:
        raise ValueError("no legs supplied")
    meta = get_symbol(symbol)
    spot = float(get_candles(symbol)["c"].iloc[-1])
    vol = realized_vol(symbol)
    r = RISK_FREE.get(meta["market"], RISK_FREE["US"])
    t = max(days, 0) / 365.0

    priced, totals = [], {k: 0.0 for k in ("delta", "gamma", "theta", "vega", "rho")}
    net_premium = 0.0
    for leg in legs:
        g = black_scholes(spot, float(leg["strike"]), t, vol, leg["type"], r)
        qty = float(leg["qty"])
        priced.append({**leg, **g})
        net_premium += qty * g["premium"]        # >0 paid out (debit), <0 received (credit)
        for k in totals:
            totals[k] += qty * g[k]

    return {
        "symbol": symbol, "spot": round(spot, 2), "days": days,
        "vol": round(vol, 4), "vol_pct": round(vol * 100, 1), "rate": r,
        "legs": priced,
        "net_premium": round(net_premium, 2),
        "position": {k: round(v, 4) for k, v in totals.items()},
    }
