"""Day-trading signal engine over enriched intraday bars — the intraday counterpart
to services/signals.py, same conviction-score shape, different rule set (VWAP,
opening range, fast EMA) tuned for moves measured in minutes to hours instead of days.

Note: index symbols (^NSEI, ^NSEBANK, ^GSPC) report zero intraday volume from Yahoo,
so VWAP is undefined (NaN) and volume-gated rules never fire for them — expected, not
a bug, and handled naturally by the same NaN-safe comparisons signals.py already relies on.
"""
from datetime import datetime, timezone

import pandas as pd

from .data import get_intraday, get_symbol
from .indicators import enrich_intraday
from .market_hours import venue_for, venue_state
from .signals import BREAKOUT_RVOL

INTRADAY_RSI_OVERSOLD = 20    # rsi7 is far more volatile than daily rsi14, hence the wider extremes
INTRADAY_RSI_OVERBOUGHT = 80
INTRADAY_STOP_ATR = 1.0       # tighter than daily's 1.5x/3x — intraday moves are smaller in absolute terms
INTRADAY_TARGET_ATR = 2.0

_INTERVAL_MINUTES = {"1m": 1, "5m": 5, "15m": 15}
# A live feed should produce a bar every `interval`. Three missed in a row, during an
# open session, means the feed is dead rather than quiet.
STALE_BAR_MULTIPLE = 3


def _bar_age_minutes(ts, now: datetime) -> float | None:
    """Minutes between the last bar and `now`. None if the timestamp is unusable."""
    t = pd.Timestamp(ts)
    if pd.isna(t):
        return None
    t = t.tz_localize(timezone.utc) if t.tzinfo is None else t.tz_convert(timezone.utc)
    return (now - t.to_pydatetime()).total_seconds() / 60.0


def analyse(symbol: str, interval: str = "5m") -> dict:
    """Rule evaluation plus a staleness verdict, which needs the venue's session."""
    open_now = None
    try:
        venue = venue_for(symbol) or venue_for_market(symbol)
        open_now = venue_state(venue)["state"] == "OPEN" if venue else None
    except Exception:
        pass   # a missing venue must never stop the analysis; it just leaves stale unknown
    return analyse_df(get_intraday(symbol, interval), symbol, interval, venue_open=open_now)


def venue_for_market(symbol: str) -> str | None:
    """Fallback when venue_for() has no mapping for a plain equity ticker."""
    try:
        return {"IN": "NSE", "US": "NYSE"}.get(get_symbol(symbol)["market"])
    except Exception:
        return None


def analyse_df(df, symbol: str = "", interval: str = "5m", now: datetime | None = None,
               venue_open: bool | None = None) -> dict:
    """Pure rule evaluation over raw intraday candles (ts,o,h,l,c,v) — no I/O, testable."""
    if len(df) < 30:
        return {"symbol": symbol, "signals": [], "error": "not enough intraday history"}
    e = enrich_intraday(df, interval=interval)
    i, p = e.iloc[-1], e.iloc[-2]
    sig = []
    if p.c <= p.vwap and i.c > i.vwap:
        sig.append({"type": "BUY", "tag": "vwap_reclaim", "why": "Price reclaimed VWAP from below"})
    if p.c >= p.vwap and i.c < i.vwap:
        sig.append({"type": "SELL", "tag": "vwap_reject", "why": "Price lost VWAP from above"})
    if i.c > i.or_hi and i.v > BREAKOUT_RVOL * i.vol20:
        sig.append({"type": "BUY", "tag": "or_breakout", "why": "Opening-range breakout on high volume"})
    if i.c < i.or_lo:
        sig.append({"type": "SELL", "tag": "or_breakdown", "why": "Opening-range breakdown"})
    if p.ema9 <= p.ema20 and i.ema9 > i.ema20:
        sig.append({"type": "BUY", "tag": "ema_cross_up", "why": "EMA9 crossed above EMA20"})
    if p.ema9 >= p.ema20 and i.ema9 < i.ema20:
        sig.append({"type": "SELL", "tag": "ema_cross_down", "why": "EMA9 crossed below EMA20"})
    if i.rsi7 < INTRADAY_RSI_OVERSOLD:
        sig.append({"type": "WATCH", "tag": "rsi_oversold", "why": f"RSI(7) {i.rsi7:.0f} — stretched, watch for a bounce"})
    if i.rsi7 > INTRADAY_RSI_OVERBOUGHT:
        sig.append({"type": "WATCH", "tag": "rsi_overbought", "why": f"RSI(7) {i.rsi7:.0f} — stretched, watch for a fade"})

    a = float(i.atr14)
    rvol = float(i.v / i.vol20) if i.vol20 else 1.0
    buy_pts = sum(2 for s in sig if s["type"] == "BUY")
    sell_pts = sum(2 for s in sig if s["type"] == "SELL")
    watch_pts = sum(1 for s in sig if s["type"] == "WATCH")
    score = abs(buy_pts - sell_pts) + watch_pts + (min(rvol, 3.0) if sig else 0.0)
    direction = "SHORT" if sell_pts > buy_pts else "LONG"
    stop = i.c + INTRADAY_STOP_ATR * a if direction == "SHORT" else i.c - INTRADAY_STOP_ATR * a
    target = i.c - INTRADAY_TARGET_ATR * a if direction == "SHORT" else i.c + INTRADAY_TARGET_ATR * a
    # Staleness is only meaningful while the venue is open — a Friday bar on a Sunday
    # is the weekend, not a dead feed, the same distinction the daily quote path makes.
    # Reported even when we can't judge it, so callers can apply their own rule.
    age = _bar_age_minutes(i.ts, now or datetime.now(timezone.utc))
    limit = STALE_BAR_MULTIPLE * _INTERVAL_MINUTES.get(interval, 5)
    stale = bool(venue_open and age is not None and age > limit)

    return {
        "symbol": symbol, "interval": interval, "close": float(i.c), "ts": str(i.ts),
        "bar_age_minutes": None if age is None else round(age, 1),
        "stale": stale, "venue_open": venue_open,
        "vwap": round(float(i.vwap), 4) if i.vwap == i.vwap else None,   # NaN check
        "or_hi": float(i.or_hi), "or_lo": float(i.or_lo),
        "ema9": float(i.ema9), "ema20": float(i.ema20), "rsi7": round(float(i.rsi7), 1),
        "rvol": round(rvol, 2), "score": round(score, 2),
        "atr": a, "direction": direction, "entry": float(i.c),
        "stop": float(stop), "target": float(target),
        "signals": sig,
    }
