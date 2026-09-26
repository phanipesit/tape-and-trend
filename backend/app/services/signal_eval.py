"""Forward-tracking of fired swing signals.

snapshot_today(): logs every BUY/SELL rule that fired on the latest bar, one row
per (symbol, bar date, rule) — idempotent via the table's UNIQUE constraint, so
weekend/restart re-runs don't duplicate. Each rule gets its own ATR plan in the
rule's direction (a SELL rule is scored as a short even when the engine's net
plan is long) so /edge measures each rule on its own merits.

evaluate_open(): scores each row the way it could actually have been traded
(score_executable): entered at the next session's open, the first price a signal
can be acted on; stop or target hit first wins (stop assumed first when both fall
in one bar), and a gap through either fills at the open rather than at the level;
else expired at the close after EXPIRE_BARS bars. R is signed: -1.0 = full stop.
`r_net` is R after round-trip costs and slippage, and it is what /edge and the
playbook judge a rule by.

Why executable and net: scored from the signal bar's own close with gap-free stops
and no costs, the system read -0.10R a trade; scored executably it is -0.20R, and
the one rule graded TRADE (rsi_overbought, +0.36R) fell to +0.22R with an interval
spanning zero (measured 2026-09-26). An edge that only exists at a price nobody can
be filled at, before costs, is not an edge.
"""
import logging
from datetime import date
from functools import lru_cache

from ..db import q
from .costs import round_trip_pct
from .data import all_symbols, get_candles, get_index_symbol, session_open
from .indicators import sma
from .signals import analyse, analyse_df, STOP_ATR, TARGET_ATR

log = logging.getLogger(__name__)

EXPIRE_BARS = 20
REGIME_SMA = 200

# Bump when the scoring method changes: evaluate_open() re-scores every row whose
# `scoring` differs, so history is never left mixing two definitions of R.
SCORING_VERSION = "exec-v1"
# Per side, on top of statutory costs. A market order at the open is where spreads are
# widest, so this is deliberately not zero.
SLIPPAGE_BPS = 10


@lru_cache(maxsize=8)
def _regime_series(market: str) -> dict:
    """date -> 'RISK_ON'/'RISK_OFF' for a market's index, close vs its own 200-day SMA.

    Same test rotation.py uses for its market filter, so the two cannot disagree.
    Cached because backfilling thousands of signals would otherwise re-read and
    re-average the index for every row. Cleared by regime_cache_clear() when the
    index gets new bars.
    """
    try:
        idx = get_index_symbol(market)
        df = get_candles(idx, limit=2000, auto=False)
    except Exception:
        log.warning("no index for market %s; regime will be null", market)
        return {}
    if len(df) < REGIME_SMA:
        return {}
    s = sma(df["c"], REGIME_SMA)
    return {d: ("RISK_ON" if c > m else "RISK_OFF")
            for d, c, m in zip(df["d"], df["c"], s) if m == m}   # skip NaN warmup


def regime_cache_clear() -> None:
    _regime_series.cache_clear()


def market_regime(market: str, on: date) -> str | None:
    """Regime on `on`, or the most recent prior session. None when unknowable."""
    series = _regime_series(market)
    if not series:
        return None
    if on in series:
        return series[on]
    earlier = [d for d in series if d <= on]
    return series[max(earlier)] if earlier else None

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
                       entry, stop, target, atr, score, market, regime)
                    VALUES (:s, :d, :tag, :ty, :dir, :e, :st, :tg, :atr, :sc, :m, :rg)
                    ON CONFLICT (symbol, signal_date, setup_tag) DO NOTHING
                    RETURNING id""",
                 s=sym, d=a["date"], tag=s["tag"], ty=s["type"], dir=direction,
                 e=round(close, 4), st=round(stop, 4), tg=round(target, 4),
                 atr=round(atr, 4), sc=a["score"], m=market,
                 rg=market_regime(market, date.fromisoformat(a["date"])))
        logged += len(rows)
    return logged


def snapshot_today() -> int:
    """Record every rule that fired on the latest *final* bar.

    Symbols whose venue is currently trading are skipped. Their newest bar is still
    forming, and the entry/stop/target derived from a mid-session close would be
    recorded as if it were the day's outcome — permanently, since the insert is
    ON CONFLICT DO NOTHING and the first write wins. This never mattered while the
    only trigger was 18:10 IST, safely after every close we track; it started
    mattering the moment the task also began firing at logon, which can be any hour.
    Nothing is lost by skipping: backfill() picks the day up once the bar is final.
    """
    logged = skipped = 0
    for meta in all_symbols():
        sym = meta["symbol"]
        try:
            if session_open(sym):
                skipped += 1
                continue
            logged += _log_signals(sym, meta["market"], analyse(sym))
        except Exception:
            log.warning("signal snapshot: analyse failed for %s", sym, exc_info=True)
    if skipped:
        log.info("signal snapshot: skipped %d symbol(s) mid-session", skipped)
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

def backfill_regime() -> int:
    """Stamp regime on rows written before migration_012. Idempotent."""
    rows = q("SELECT id, market, signal_date FROM signal_outcomes WHERE regime IS NULL")
    n = 0
    for r in rows:
        rg = market_regime(r["market"], r["signal_date"])
        if rg:
            q("UPDATE signal_outcomes SET regime=:g WHERE id=:i", g=rg, i=r["id"])
            n += 1
    return n


def score_signal(direction: str, entry: float, stop: float, target: float, after) -> dict | None:
    """Pure forward-walk over the bars after the signal (max EXPIRE_BARS rows used).

    Returns {outcome, exit_price, exit_date, bars_held, r_multiple} once resolved,
    or None while the signal is still open (or unscorable). Stop wins when stop and
    target both fall inside one bar; r_multiple is signed and risk-normalised.

    When bars carry an open (`o`), a bar that *opens* beyond a level fills at the open:
    a stock that gaps 4% through its stop overnight loses more than 1R, and one that
    gaps through its target earns the gap. Without this every stop read exactly -1.00R.
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
    has_open = "o" in after.columns
    for _, row in after.iterrows():
        bars += 1
        h, l = float(row.h), float(row.l)
        if has_open:
            o = float(row.o)
            if (o <= stop if is_long else o >= stop):
                outcome, exit_price, exit_date = "stop_hit", o, row.d
                break
            if (o >= target if is_long else o <= target):
                outcome, exit_price, exit_date = "target_hit", o, row.d
                break
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

def cost_fraction(market: str | None) -> float:
    """Round trip as a fraction of turnover: statutory costs plus slippage both sides.
    Indian shorts are costed as delivery, which overstates them slightly (a stock-futures
    short pays less STT) — conservative, and a rule has to survive it either way."""
    return round_trip_pct(100_000, market or "IN") / 100 + 2 * SLIPPAGE_BPS / 10_000


def score_executable(direction: str, atr: float, after, cost_frac: float) -> dict | None:
    """Score a signal as it could have been traded. Pure.

    Entry is the open of the first bar after the signal, and stop/target are re-based on
    that fill with the same ATR multiples — the plan a trader would actually place. The
    walk starts on that same bar, since the stop is live from the fill onward."""
    if after is None or after.empty or not atr:
        return None
    entry = float(after.iloc[0].o)
    is_long = direction == "LONG"
    risk = STOP_ATR * atr
    stop = entry - risk if is_long else entry + risk
    target = entry + TARGET_ATR * atr if is_long else entry - TARGET_ATR * atr
    res = score_signal(direction, entry, stop, target, after)
    if res is None:
        return None
    cost_r = cost_frac * entry / risk
    res.update(fill_entry=entry, cost_r=round(cost_r, 3),
               r_net=round(res["r_multiple"] - cost_r, 3))
    return res


def evaluate_open() -> int:
    """Score open rows, and re-score any row scored under an older method."""
    rows = q("""SELECT * FROM signal_outcomes
                WHERE (outcome IS NULL OR scoring IS DISTINCT FROM :v)
                  AND signal_date < CURRENT_DATE
                ORDER BY signal_date""", v=SCORING_VERSION)
    scored = 0
    # Deep enough for any row being re-scored, cached per symbol: a re-score walks
    # hundreds of rows per name. A fixed recent window (it was the last 80 bars) is
    # only safe for open rows — an older signal would silently be walked from whatever
    # bar the window happened to start at.
    candles: dict[str, object] = {}
    for sig in rows:
        try:
            if sig["symbol"] not in candles:
                candles[sig["symbol"]] = get_candles(sig["symbol"], limit=2000, auto=False)
            df = candles[sig["symbol"]]
            if df.empty or sig["signal_date"] not in set(df["d"]):
                continue
            res = score_executable(sig["direction"], float(sig["atr"] or 0),
                                   df[df["d"] > sig["signal_date"]], cost_fraction(sig["market"]))
            if res is None:
                # Not resolvable yet. A row scored under an older method goes back to
                # open rather than keeping a result the current method wouldn't give.
                if sig["outcome"] is not None:
                    q("""UPDATE signal_outcomes SET outcome=NULL, exit_price=NULL,
                           exit_date=NULL, bars_held=NULL, r_multiple=NULL, fill_entry=NULL,
                           cost_r=NULL, r_net=NULL, scoring=NULL WHERE id=:i""", i=sig["id"])
                continue
            q("""UPDATE signal_outcomes
                 SET outcome=:o, exit_price=:e, exit_date=:d, bars_held=:b, r_multiple=:r,
                     fill_entry=:f, cost_r=:c, r_net=:n, scoring=:v
                 WHERE id=:i""",
              o=res["outcome"], e=round(res["exit_price"], 4), d=res["exit_date"],
              b=res["bars_held"], r=res["r_multiple"], f=round(res["fill_entry"], 4),
              c=res["cost_r"], n=res["r_net"], v=SCORING_VERSION, i=sig["id"])
            scored += 1
        except Exception:
            log.warning("signal eval failed for id=%s (%s)", sig["id"], sig["symbol"], exc_info=True)
    return scored
