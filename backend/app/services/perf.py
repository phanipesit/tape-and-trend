"""Shared equity-curve performance math, used by both backtest.py (single-symbol)
and rotation.py (portfolio-level) so the two engines report numbers the same way."""
import numpy as np

INITIAL_CAPITAL = 100_000.0

def perf_stats(curve: np.ndarray, initial: float = INITIAL_CAPITAL) -> dict:
    """CAGR/Sharpe/max-drawdown/total-return from a daily equity curve."""
    final = float(curve[-1])
    rets = np.diff(curve) / curve[:-1]
    peak = np.maximum.accumulate(curve)
    mdd = float(((peak - curve) / peak).max() * 100)
    yrs = len(curve) / 252
    sharpe = float(rets.mean() / (rets.std() + 1e-12) * np.sqrt(252))
    return {
        "final": round(final, 2),
        "total_return": round((final / initial - 1) * 100, 2),
        "cagr": round(((final / initial) ** (1 / yrs) - 1) * 100, 2),
        "max_drawdown": round(mdd, 2),
        "sharpe": round(sharpe, 2),
    }
