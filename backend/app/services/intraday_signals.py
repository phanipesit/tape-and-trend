"""Day-trading signal engine over enriched intraday bars — the intraday counterpart
to services/signals.py, same conviction-score shape, different rule set (VWAP,
opening range, fast EMA) tuned for moves measured in minutes to hours instead of days.

Note: index symbols (^NSEI, ^NSEBANK, ^GSPC) report zero intraday volume from Yahoo,
so VWAP is undefined (NaN) and volume-gated rules never fire for them — expected, not
a bug, and handled naturally by the same NaN-safe comparisons signals.py already relies on.
"""
from .data import get_intraday
from .indicators import enrich_intraday
from .signals import BREAKOUT_RVOL

INTRADAY_RSI_OVERSOLD = 20    # rsi7 is far more volatile than daily rsi14, hence the wider extremes
INTRADAY_RSI_OVERBOUGHT = 80
INTRADAY_STOP_ATR = 1.0       # tighter than daily's 1.5x/3x — intraday moves are smaller in absolute terms
INTRADAY_TARGET_ATR = 2.0

def analyse(symbol: str, interval: str = "5m") -> dict:
    return analyse_df(get_intraday(symbol, interval), symbol, interval)

def analyse_df(df, symbol: str = "", interval: str = "5m") -> dict:
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
    return {
        "symbol": symbol, "interval": interval, "close": float(i.c), "ts": str(i.ts),
        "vwap": round(float(i.vwap), 4) if i.vwap == i.vwap else None,   # NaN check
        "or_hi": float(i.or_hi), "or_lo": float(i.or_lo),
        "ema9": float(i.ema9), "ema20": float(i.ema20), "rsi7": round(float(i.rsi7), 1),
        "rvol": round(rvol, 2), "score": round(score, 2),
        "atr": a, "direction": direction, "entry": float(i.c),
        "stop": float(stop), "target": float(target),
        "signals": sig,
    }
