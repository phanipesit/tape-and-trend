#!/usr/bin/env python3
"""Walk-forward the swing engine's stop/target parameters.

The 40-cell sweep on 2026-08-15 reported +0.189 R for its best long-only cell. Split by
year that was +0.344 in 2025 and +0.040 in 2026 — it failed out-of-sample, and only a
manual year-split revealed it. This asks the question the sweep could not: if you had
re-optimised on a rolling basis, as anyone actually would, what would you have earned?

Signals come from the live analyse_df over cached candles, so entries are the engine's
real ones. Only the exit parameters are searched.
"""
import os
import sys
from itertools import product

BACKEND = r"C:\users\phani\tape-and-trend\backend"
os.chdir(BACKEND)
sys.path.insert(0, BACKEND)

from app.services.data import all_symbols, get_candles
from app.services.signals import analyse_df, STOP_ATR, TARGET_ATR
from app.services import walkforward as wf

WARMUP, HORIZON = 210, 20
STOPS = [1.0, 1.5, 2.0, 2.5, 3.0]
TARGETS = [2.0, 3.0, 4.0, 6.0]
GRID = [(s, t) for s, t in product(STOPS, TARGETS) if t > s]
BASELINE = (STOP_ATR, TARGET_ATR)


def collect():
    out = []
    for meta in all_symbols():
        sym = meta["symbol"]
        df = get_candles(sym, limit=600, auto=False)
        if len(df) < WARMUP + HORIZON:
            continue
        for i in range(WARMUP, len(df) - HORIZON):
            a = analyse_df(df.iloc[:i + 1], sym)
            if a.get("error") or not a["signals"] or not a["atr"]:
                continue
            for s in a["signals"]:
                if s["type"] not in ("BUY", "SELL"):
                    continue
                fut = df.iloc[i + 1:i + 1 + HORIZON]
                out.append({
                    "date": df["d"].iloc[i], "dir": "LONG" if s["type"] == "BUY" else "SHORT",
                    "entry": float(a["close"]), "atr": float(a["atr"]),
                    "highs": fut["h"].astype(float).tolist(),
                    "lows": fut["l"].astype(float).tolist(),
                    "close": float(fut["c"].iloc[-1]) if len(fut) else None,
                })
    return out


def score(sig, params):
    """First touch wins, stop assumed first when a bar spans both — the same rule as
    services/signal_eval.score_signal, so results stay comparable to /edge."""
    stop_m, tgt_m = params
    e, a, lng = sig["entry"], sig["atr"], sig["dir"] == "LONG"
    stop = e - stop_m * a if lng else e + stop_m * a
    tgt = e + tgt_m * a if lng else e - tgt_m * a
    risk = abs(e - stop)
    if not risk or sig["close"] is None:
        return None
    for h, l in zip(sig["highs"], sig["lows"]):
        if (l <= stop) if lng else (h >= stop):
            return -1.0
        if (h >= tgt) if lng else (l <= tgt):
            return tgt_m / stop_m
    return ((sig["close"] - e) if lng else (e - sig["close"])) / risk


def main():
    print("collecting signals from the live engine...", flush=True)
    sigs = collect()
    print(f"{len(sigs):,} signals, {sigs[0]['date']} -> {sigs[-1]['date']}", flush=True)
    print(f"grid: {len(GRID)} stop/target pairs, baseline {BASELINE}\n", flush=True)

    r = wf.run(sigs, GRID, score, train_days=180, test_days=60, baseline=BASELINE)
    print(f"folds: {r['n_folds']} used, {r['skipped_folds']} skipped (too thin)\n")
    for label in ("in_sample", "out_of_sample", "baseline"):
        s = r[label]
        ci = "" if s["ci_low"] is None else f"  CI [{s['ci_low']:+.3f}, {s['ci_high']:+.3f}]"
        print(f"  {label:<15} {str(s['mean']):>8} R over {s['n']} folds{ci}")
    print(f"\n  decay (in-sample minus out-of-sample): {r['decay']:+.4f} R")
    print(f"  optimising vs fixed parameters:        {r['beats_baseline']:+.4f} R")
    st = r["stability"]
    print(f"  stability: {st['distinct_choices']} distinct winners, "
          f"most common {st['most_common']}, consistency {st['consistency']}")

    print("\n  fold detail:")
    print(f"    {'test window':<24}{'chosen':<12}{'in-samp':>9}{'out-samp':>10}{'baseline':>10}")
    for f in r["folds"]:
        print(f"    {f['test_start']} -> {f['test_end']}  {str(f['chosen']):<12}"
              f"{f['in_sample']:>9}{str(f['out_of_sample']):>10}{str(f.get('baseline')):>10}")


if __name__ == "__main__":
    main()
