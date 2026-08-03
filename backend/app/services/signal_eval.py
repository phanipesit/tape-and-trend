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
from .signals import analyse, analyse_df, STOP_ATR, TARGET_ATR

log = logging.getLogger(__name__)

EXPIRE_BARS = 20

def _log_signals(sym: str, market: str, a: dict) -> int:
    """Persist every BUY/SELL rule in one analysis. Idempotent via the table's UNIQUE
    constraint, so re-running a day is free. Shared by snapshot_today and backfill so
    the two can't drift in how a signal is recorded."""
    if a.get("error") or not a.get("signals"):
        return 0
    close, atr = a["close"], a["atr"]
    logged = 0
    for s in a["signals"]:
        if s["type"] not in ("BUY", "SELL") or not atr:
            continue
        if s["type"] == "BUY":
            direction = "LONG"
            stop, target = close - STOP_ATR * atr, close + TARGET_ATR * atr
        else:
            direction = "SHORT"
            stop, target = close + STOP_ATR * atr, close - TARGET_ATR * atr
        rows = q("""INSERT INTO signal_outcomes
                      (symbol, signal_date, setup_tag, sig_type, direction,
                       entry, stop, target, atr, score, market)
                    VALUES (:s, :d, :tag, :ty, :dir, :e, :st, :tg, :atr, :sc, :m)
                    ON CONFLICT (symbol, signal_date, setup_tag) DO NOTHING
                    RETURNING id""",
                 s=sym, d=a["date"], tag=s["tag"], ty=s["type"], dir=direction,
                 e=round(close, 4), st=round(stop, 4), tg=round(target, 4),
                 atr=round(atr, 4), sc=a["score"], m=market)
        logged += len(rows)
    return logged


def snapshot_today() -> int:
    logged = 0
    for meta in all_symbols():
        sym = meta["symbol"]
        try:
            logged += _log_signals(sym, meta["market"], analyse(sym))
        except Exception:
            log.warning("signal snapshot: analyse failed for %s", sym, exc_info=True)
    return logged


def backfill(sessions: int = 30) -> dict:
    """Reconstruct snapshots for the last `sessions` cached trading days.

    The tracker only ever recorded on days the backend happened to be running, so
    /edge was measuring a sampled subset rather than a series — five days across
    three weeks, which is far too sparse to say anything about an edge.

    Reconstruction is exact rather than approximate: every indicator in enrich() is
    backward-looking, so running analyse_df over candles truncated at date D returns
    precisely what the engine returned on D. It goes through the same analyse_df the
    live path uses, deliberately — re-implementing the rules here is how backtest.py
    and the live engine are already able to drift, and that hazard is not worth
    repeating for a one-off.

    Only the entry side is reconstructed. Outcomes are then scored forward by
    evaluate_open() from the same cached bars, so nothing is invented.

    Caveat worth knowing: cached candles are auto-adjusted, so a split or dividend
    since the signal date shifts historical prices relative to what was on screen at
    the time. Levels stay internally consistent (entry, stop and target all move
    together, and R is risk-normalised), so outcome and R survive it; the absolute
    prices are the adjusted ones.
    """
    logged = skipped = 0
    for meta in all_symbols():
        sym = meta["symbol"]
        try:
            df = get_candles(sym, limit=sessions + 300, auto=False)
            if len(df) < 60:
                skipped += 1
                continue
            for d in df["d"].tail(sessions):
                logged += _log_signals(sym, meta["market"], analyse_df(df[df["d"] <= d], sym))
        except Exception:
            skipped += 1
            log.warning("backfill failed for %s", sym, exc_info=True)
    return {"logged": logged, "skipped": skipped, "sessions": sessions}

def score_signal(direction: str, entry: float, stop: float, target: float, after) -> dict | None:
    """Pure forward-walk over the bars after the signal (max EXPIRE_BARS rows used).

    Returns {outcome, exit_price, exit_date, bars_held, r_multiple} once resolved,
    or None while the signal is still open (or unscorable). Stop wins when stop and
    target both fall inside one bar; r_multiple is signed and risk-normalised.
    """
    after = after.head(EXPIRE_BARS)
    if after.empty:
        return None
    is_long = direction == "LONG"
    risk = abs(entry - stop)
    if not risk:
        return None
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
            return None   # still open — not enough bars yet
        last = after.iloc[-1]
        outcome, exit_price, exit_date = "expired", float(last.c), last.d
    r = (exit_price - entry) / risk if is_long else (entry - exit_price) / risk
    return {"outcome": outcome, "exit_price": exit_price, "exit_date": exit_date,
            "bars_held": bars, "r_multiple": round(r, 2)}

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
            res = score_signal(sig["direction"], float(sig["entry"]), float(sig["stop"]),
                               float(sig["target"]), df[df["d"] > sig["signal_date"]])
            if res is None:
                continue
            q("""UPDATE signal_outcomes
                 SET outcome=:o, exit_price=:e, exit_date=:d, bars_held=:b, r_multiple=:r
                 WHERE id=:i""",
              o=res["outcome"], e=round(res["exit_price"], 4), d=res["exit_date"],
              b=res["bars_held"], r=res["r_multiple"], i=sig["id"])
            scored += 1
        except Exception:
            log.warning("signal eval failed for id=%s (%s)", sig["id"], sig["symbol"], exc_info=True)
    return scored
