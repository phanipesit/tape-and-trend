"""Portfolio-level momentum rotation backtest (Clenow's "Stocks on the Move").

Ranks a whole market universe by risk-adjusted momentum, holds a rotating basket of
the top N, sized by ATR risk-parity and gated by a broad index's own 200-day trend —
architecturally different from backtest.py's single-symbol engine, so it lives here
with its own portfolio bookkeeping.

Runs entirely off cached candles (same precondition as services/sectors.py) — never
triggers a live yfinance refresh per symbol, since looping that across a ~100-symbol
universe inside one request is exactly what routers/screener.py's "multi-minute run"
comment warns about. Refresh the universe first (screener's "Refresh all") if the
cache is stale.
"""
import json
import numpy as np
import pandas as pd
from .data import all_symbols, get_candles, get_index_symbol
from .indicators import enrich, atr
from .perf import perf_stats, INITIAL_CAPITAL
from ..db import q

def _momentum_and_gap(close: pd.Series, window: int) -> tuple[pd.Series, pd.Series]:
    """Closed-form rolling OLS (no slow rolling().apply()): regression slope of
    log(close) vs a bar index, annualised and weighted by fit quality, per Clenow's
    published formula ((1+slope)**252 * r_squared). The regression's bar index can be
    global (0..n-1) rather than re-based to 0 at each window start — slope/R² only
    depend on covariance/variance of t, which are unaffected by shifting t by a
    constant, so rolling sums of a single global t series give the correct per-window
    OLS result without recomputing t per window.

    Also returns the trailing max absolute daily return over the same window, the
    direct daily-bar proxy for "no gap >= 15% in the last N days".
    """
    n = len(close)
    t = pd.Series(np.arange(n, dtype=float), index=close.index)
    y = np.log(close)
    w = window
    sum_t, sum_t2 = t.rolling(w).sum(), (t * t).rolling(w).sum()
    sum_y, sum_ty, sum_y2 = y.rolling(w).sum(), (t * y).rolling(w).sum(), (y * y).rolling(w).sum()
    denom = w * sum_t2 - sum_t ** 2
    slope = (w * sum_ty - sum_t * sum_y) / denom.replace(0, np.nan)
    intercept = (sum_y - slope * sum_t) / w
    ss_tot = sum_y2 - (sum_y ** 2) / w
    ss_res = sum_y2 - intercept * sum_y - slope * sum_ty
    r2 = (1 - ss_res / ss_tot.replace(0, np.nan)).clip(lower=0, upper=1).fillna(0)
    momentum = ((1 + slope) ** 252) * r2
    max_abs_ret = close.pct_change().abs().rolling(w).max()
    return momentum, max_abs_ret

def run(market: str, params: dict) -> dict:
    if market not in ("IN", "US"):
        return {"error": f"unknown market {market}"}
    top_n = int(params.get("top_n", 20))
    momentum_days = int(params.get("momentum_days", 90))
    rebalance_days = int(params.get("rebalance_days", 5))
    risk_pct = params.get("risk_pct", 0.1) / 100
    fee = params.get("fee_bps", 5) / 1e4
    slip = params.get("slip_bps", 5) / 1e4
    max_gap = 0.15

    universe = [s["symbol"] for s in all_symbols(market)]
    if len(universe) < 5:
        return {"error": f"not enough symbols in {market} universe"}
    index_sym = get_index_symbol(market)
    idx = enrich(get_candles(index_sym, auto=False))
    if len(idx) < 220:
        return {"error": f"not enough index history for {index_sym} — refresh candles first"}

    rows = q("""SELECT symbol, d, h, l, c FROM ohlcv WHERE symbol = ANY(:syms)
                AND d >= :start ORDER BY symbol, d""",
             syms=universe, start=idx["d"].iloc[0])
    if not rows:
        return {"error": f"no cached candles for {market} universe — refresh first"}
    by_symbol: dict[str, list] = {}
    for r in rows:
        by_symbol.setdefault(r["symbol"], []).append(r)

    master_dates = idx["d"].reset_index(drop=True)
    n_days = len(master_dates)
    date_pos = {d: i for i, d in enumerate(master_dates)}

    close_arr = np.full((n_days, len(by_symbol)), np.nan)
    sma100_arr = np.full_like(close_arr, np.nan)
    atr20_arr = np.full_like(close_arr, np.nan)
    mom_arr = np.full_like(close_arr, np.nan)
    gap_ok_arr = np.full((n_days, len(by_symbol)), False)
    symbols_list = list(by_symbol)

    for j, sym in enumerate(symbols_list):
        recs = by_symbol[sym]
        d = [r["d"] for r in recs]
        sdf = pd.DataFrame({"h": [float(r["h"]) for r in recs], "l": [float(r["l"]) for r in recs],
                            "c": [float(r["c"]) for r in recs]}, index=d)
        # align to the index's own calendar; forward-fill the rare stock-specific
        # non-trading day so every symbol has a value on every master date
        sdf = sdf.reindex(master_dates).ffill()
        pos = [date_pos[dd] for dd in sdf.index]
        close_arr[pos, j] = sdf["c"].to_numpy()
        sma100_arr[pos, j] = sdf["c"].rolling(100).mean().to_numpy()
        atr20_arr[pos, j] = atr(sdf, 20).to_numpy()
        momentum, max_abs_ret = _momentum_and_gap(sdf["c"], momentum_days)
        mom_arr[pos, j] = momentum.to_numpy()
        gap_ok_arr[pos, j] = (max_abs_ret < max_gap).to_numpy()

    idx_sma200 = idx["sma200"].to_numpy()
    idx_close = idx["c"].to_numpy()
    warmup = max(200, 100, momentum_days) + 1
    if n_days <= warmup:
        return {"error": "not enough history across the warmup window"}

    cash = INITIAL_CAPITAL
    qty = np.zeros(len(symbols_list))
    entry_px = np.full(len(symbols_list), np.nan)
    trades = []
    curve = np.empty(n_days)

    for i in range(n_days):
        px_today = close_arr[i]
        if i >= warmup and (i - warmup) % rebalance_days == 0:
            regime_on = idx_close[i] > idx_sma200[i]
            held = qty > 0
            eligible = (
                (px_today > sma100_arr[i]) & gap_ok_arr[i] &
                ~np.isnan(mom_arr[i]) & (atr20_arr[i] > 0)
            )
            # rank eligible names by momentum, desired = top_n — computed regardless
            # of regime; the regime only gates new buys below, not existing holdings
            cand = np.where(eligible)[0]
            desired = set(cand[np.argsort(-mom_arr[i][cand])][:top_n])

            # sell anything no longer desired, or that broke its own trend filter
            trend_broken = held & (px_today <= sma100_arr[i])
            to_sell = [j for j in np.where(held)[0] if j not in desired or trend_broken[j]]
            for j in to_sell:
                fill = px_today[j] * (1 - slip)
                sold_qty = qty[j]
                cash += sold_qty * fill * (1 - fee)
                trades.append({"symbol": symbols_list[j], "qty": round(float(sold_qty), 4),
                               "in": round(float(entry_px[j]), 2), "out": round(float(fill), 2),
                               "ret": round(float(fill / entry_px[j] - 1) * 100, 2)})
                qty[j], entry_px[j] = 0.0, np.nan

            # buy newly-desired names, scaling down if cash-constrained
            to_buy = [j for j in desired if qty[j] == 0]
            if to_buy and regime_on:
                equity_now = cash + float(np.nansum(qty * px_today))
                raw_qty = {j: (equity_now * risk_pct) / atr20_arr[i, j] for j in to_buy}
                fills = {j: px_today[j] * (1 + slip) for j in to_buy}
                total_cost = sum(raw_qty[j] * fills[j] * (1 + fee) for j in to_buy)
                scale = min(1.0, cash / total_cost) if total_cost > cash and total_cost > 0 else 1.0
                for j in to_buy:
                    q_j = raw_qty[j] * scale
                    cost = q_j * fills[j] * (1 + fee)
                    if cost <= 0 or cost > cash + 1e-6:
                        continue
                    cash -= cost
                    qty[j], entry_px[j] = q_j, fills[j]

        curve[i] = cash + float(np.nansum(qty * np.nan_to_num(px_today, nan=0.0)))

    # close anything still open at the final available price
    last_px = close_arr[-1]
    for j in np.where(qty > 0)[0]:
        fill = last_px[j] * (1 - slip)
        cash += qty[j] * fill * (1 - fee)
        trades.append({"symbol": symbols_list[j], "qty": round(float(qty[j]), 4),
                       "in": round(float(entry_px[j]), 2), "out": round(float(fill), 2),
                       "ret": round(float(fill / entry_px[j] - 1) * 100, 2)})
        qty[j] = 0.0
    curve[-1] = cash

    wins = [t for t in trades if t["ret"] > 0]
    out = {
        "market": market, "index": index_sym, "params": params,
        **perf_stats(curve),
        "win_rate": round(len(wins) / len(trades) * 100, 1) if trades else 0,
        "buy_hold": round(float(idx_close[-1] / idx_close[warmup] - 1) * 100, 2),
        "n_trades": len(trades), "trades": trades,
        "curve": [round(float(x), 2) for x in curve[warmup:]],
        "dates": [str(dd) for dd in master_dates.iloc[warmup:]],
    }
    q("""INSERT INTO rotation_runs (market,params,total_return,cagr,win_rate,
         max_drawdown,sharpe,n_trades,buy_hold)
         VALUES (:m,:p,:tr,:cg,:wr,:dd,:sh,:n,:bh)""",
      m=market, p=json.dumps(params), tr=out["total_return"], cg=out["cagr"],
      wr=out["win_rate"], dd=out["max_drawdown"], sh=out["sharpe"],
      n=out["n_trades"], bh=out["buy_hold"])
    return out

def history(market: str | None = None, limit: int = 20) -> list[dict]:
    if market in ("IN", "US"):
        return q("""SELECT * FROM rotation_runs WHERE market=:m
                    ORDER BY ran_at DESC LIMIT :n""", m=market, n=limit)
    return q("SELECT * FROM rotation_runs ORDER BY ran_at DESC LIMIT :n", n=limit)
