"""Vectorised long-only backtester with costs + slippage, results stored in psql."""
import json
import numpy as np
from .data import get_candles
from .indicators import enrich, rsi, sma
from .signals import RSI_OVERSOLD, RSI_OVERBOUGHT, BREAKOUT_RVOL
from .perf import perf_stats, INITIAL_CAPITAL
from ..db import q

def run(symbol: str, strategy: str, params: dict) -> dict:
    df = enrich(get_candles(symbol))
    if len(df) < 100:
        return {"error": "not enough history"}
    c = df["c"].to_numpy()
    fee = params.get("fee_bps", 5) / 1e4        # per side
    slip = params.get("slip_bps", 5) / 1e4

    if strategy == "emax":
        f = df["c"].ewm(span=params.get("fast", 20), adjust=False).mean().to_numpy()
        s = df["c"].ewm(span=params.get("slow", 50), adjust=False).mean().to_numpy()
        entry_sig = (f > s) & (np.roll(f <= s, 1))
        exit_sig = (f < s) & (np.roll(f >= s, 1))
    elif strategy == "rsi":
        r = df["rsi14"].to_numpy()
        entry_sig = r < params.get("buy", 30)
        exit_sig = r > params.get("sell", 60)
    elif strategy == "macd":
        h = df["macd_h"].to_numpy()
        entry_sig = (h > 0) & (np.roll(h, 1) <= 0)
        exit_sig = (h < 0) & (np.roll(h, 1) >= 0)
    elif strategy == "signal":
        # the live swing engine's rules (services/signals.py), long side only:
        # BUY rules open a position, SELL rules close it — thresholds imported
        # from signals.py so the two engines cannot drift apart
        e20, e50 = df["ema20"].to_numpy(), df["ema50"].to_numpy()
        r, s200 = df["rsi14"].to_numpy(), df["sma200"].to_numpy()
        h, hi, lo = df["macd_h"].to_numpy(), df["hi20"].to_numpy(), df["lo20"].to_numpy()
        v, v20 = df["v"].to_numpy(), df["vol20"].to_numpy()
        cross_up = (e20 > e50) & np.roll(e20 <= e50, 1)
        cross_dn = (e20 < e50) & np.roll(e20 >= e50, 1)
        entry_sig = cross_up | ((r < RSI_OVERSOLD) & (c > s200)) | ((c > hi) & (v > BREAKOUT_RVOL * v20))
        exit_sig = cross_dn | ((r > RSI_OVERBOUGHT) & (h < np.roll(h, 1))) | (c < lo)
    elif strategy == "rsi2":
        # Larry Connors' RSI(2) mean reversion: only long while above the 200-day
        # trend filter, buy a sharp 2-period RSI dip, exit on reversion above the
        # 5-day average — a fast, high-turnover system (holds days, not weeks)
        r2 = rsi(df["c"], 2).to_numpy()
        s200 = df["sma200"].to_numpy()
        s5 = sma(df["c"], 5).to_numpy()
        entry_sig = (c > s200) & (r2 < params.get("rsi2_buy", 5))
        exit_sig = c > s5
    elif strategy == "donchian":
        # Turtle-style trend following: buy an N-day high breakout, exit on an
        # M-day low breakdown. Wins less often than it loses; the edge is letting
        # the rare big trend run rather than a high hit rate.
        entry_days = params.get("entry_days", 20)
        exit_days = params.get("exit_days", 10)
        hi_n = df["h"].shift(1).rolling(entry_days).max().to_numpy()
        lo_n = df["l"].shift(1).rolling(exit_days).min().to_numpy()
        entry_sig = c > hi_n
        exit_sig = c < lo_n
    else:
        return {"error": f"unknown strategy {strategy}"}

    cash, qty, entry_px = INITIAL_CAPITAL, 0.0, 0.0
    trades, curve = [], []
    for i in range(1, len(c)):
        px = c[i]
        if qty == 0 and entry_sig[i]:
            fill = px * (1 + slip)
            qty = cash * (1 - fee) / fill
            entry_px, cash = fill, 0.0
        elif qty > 0 and exit_sig[i]:
            fill = px * (1 - slip)
            cash = qty * fill * (1 - fee)
            trades.append({"in": round(entry_px, 2), "out": round(fill, 2),
                           "ret": round((fill / entry_px - 1) * 100, 2)})
            qty = 0.0
        curve.append(cash + qty * px)
    if qty > 0:
        cash = qty * c[-1] * (1 - fee)
        trades.append({"in": round(entry_px, 2), "out": round(c[-1], 2),
                       "ret": round((c[-1] / entry_px - 1) * 100, 2)})
        curve[-1] = cash

    curve = np.array(curve)
    wins = [t for t in trades if t["ret"] > 0]
    out = {
        "symbol": symbol, "strategy": strategy, "params": params,
        **perf_stats(curve),
        "win_rate": round(len(wins) / len(trades) * 100, 1) if trades else 0,
        "buy_hold": round(float(c[-1] / c[0] - 1) * 100, 2),
        "n_trades": len(trades), "trades": trades,
        "curve": [round(float(x), 2) for x in curve],
        "dates": [str(d) for d in df["d"].iloc[1:]],
    }
    q("""INSERT INTO backtest_runs (symbol,strategy,params,total_return,cagr,win_rate,
         max_drawdown,sharpe,trades,buy_hold)
         VALUES (:s,:st,:p,:tr,:cg,:wr,:dd,:sh,:n,:bh)""",
      s=symbol, st=strategy, p=json.dumps(params), tr=out["total_return"],
      cg=out["cagr"], wr=out["win_rate"], dd=out["max_drawdown"],
      sh=out["sharpe"], n=out["n_trades"], bh=out["buy_hold"])
    return out
