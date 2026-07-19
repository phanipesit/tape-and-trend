"""Forward-tracking of fired swing signals.

snapshot_today(): logs every BUY/SELL rule that fired on the latest bar, one row
per (symbol, bar date, rule) — idempotent via the table's UNIQUE constraint, so
weekend/restart re-runs don't duplicate. Each rule gets its own ATR plan in the
rule's direction (a SELL rule is scored as a short even when the engine's net
plan is long) so /edge measures each rule on its own merits.

evaluate_open(): walks open rows forward bar by bar — stop or target hit first
wins (stop assumed first when both fall in one bar), else expired at the close
after EXPIRE_BARS bars. R is signed: -1.0 = full stop, +2.0 = twice the risk.
"""
import logging
from ..db import q
from .data import all_symbols, get_candles
from .signals import analyse

log = logging.getLogger(__name__)

EXPIRE_BARS = 20

def snapshot_today() -> int:
    logged = 0
    for meta in all_symbols():
        sym = meta["symbol"]
        try:
            a = analyse(sym)
        except Exception:
            log.warning("signal snapshot: analyse failed for %s", sym, exc_info=True)
            continue
        if a.get("error") or not a["signals"]:
            continue
        close, atr = a["close"], a["atr"]
        for s in a["signals"]:
            if s["type"] not in ("BUY", "SELL") or not atr:
                continue
            if s["type"] == "BUY":
                direction, stop, target = "LONG", close - 1.5 * atr, close + 3 * atr
            else:
                direction, stop, target = "SHORT", close + 1.5 * atr, close - 3 * atr
            rows = q("""INSERT INTO signal_outcomes
                          (symbol, signal_date, setup_tag, sig_type, direction,
                           entry, stop, target, atr, score, market)
                        VALUES (:s, :d, :tag, :ty, :dir, :e, :st, :tg, :atr, :sc, :m)
                        ON CONFLICT (symbol, signal_date, setup_tag) DO NOTHING
                        RETURNING id""",
                     s=sym, d=a["date"], tag=s["tag"], ty=s["type"], dir=direction,
                     e=round(close, 4), st=round(stop, 4), tg=round(target, 4),
                     atr=round(atr, 4), sc=a["score"], m=meta["market"])
            logged += len(rows)
    return logged

def evaluate_open() -> int:
    rows = q("""SELECT * FROM signal_outcomes
                WHERE outcome IS NULL AND signal_date < CURRENT_DATE
                ORDER BY signal_date""")
    scored = 0
    for sig in rows:
        try:
            df = get_candles(sig["symbol"], limit=EXPIRE_BARS + 60, auto=False)
            if df.empty:
                continue
            after = df[df["d"] > sig["signal_date"]].head(EXPIRE_BARS)
            if after.empty:
                continue
            entry, stop, target = float(sig["entry"]), float(sig["stop"]), float(sig["target"])
            is_long = sig["direction"] == "LONG"
            risk = abs(entry - stop)
            if not risk:
                continue
            outcome = exit_price = exit_date = None
            bars = 0
            for _, row in after.iterrows():
                bars += 1
                h, l = float(row.h), float(row.l)
                if (l <= stop if is_long else h >= stop):
                    outcome, exit_price, exit_date = "stop_hit", stop, row.d
                    break
                if (h >= target if is_long else l <= target):
                    outcome, exit_price, exit_date = "target_hit", target, row.d
                    break
            if outcome is None:
                if len(after) < EXPIRE_BARS:
                    continue   # still open — not enough bars yet, check again tomorrow
                last = after.iloc[-1]
                outcome, exit_price, exit_date = "expired", float(last.c), last.d
            r = (exit_price - entry) / risk if is_long else (entry - exit_price) / risk
            q("""UPDATE signal_outcomes
                 SET outcome=:o, exit_price=:e, exit_date=:d, bars_held=:b, r_multiple=:r
                 WHERE id=:i""",
              o=outcome, e=round(exit_price, 4), d=exit_date, b=bars, r=round(r, 2), i=sig["id"])
            scored += 1
        except Exception:
            log.warning("signal eval failed for id=%s (%s)", sig["id"], sig["symbol"], exc_info=True)
    return scored
