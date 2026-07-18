"""Swing-signal rule engine over enriched daily bars."""
from .data import get_candles
from .indicators import enrich

def analyse(symbol: str) -> dict:
    df = get_candles(symbol)
    if len(df) < 60:
        return {"symbol": symbol, "signals": [], "error": "not enough history"}
    e = enrich(df)
    i, p = e.iloc[-1], e.iloc[-2]
    sig = []
    if p.ema20 <= p.ema50 and i.ema20 > i.ema50:
        sig.append({"type": "BUY", "why": "EMA20 crossed above EMA50 (trend turn)"})
    if p.ema20 >= p.ema50 and i.ema20 < i.ema50:
        sig.append({"type": "SELL", "why": "EMA20 crossed below EMA50"})
    if i.rsi14 < 32 and i.c > i.sma200:
        sig.append({"type": "BUY", "why": f"RSI {i.rsi14:.0f} oversold in uptrend (pullback)"})
    if i.rsi14 > 72 and i.macd_h < p.macd_h:
        sig.append({"type": "SELL", "why": f"RSI {i.rsi14:.0f} overbought, MACD fading"})
    if i.c > i.hi20 and i.v > 1.4 * i.vol20:
        sig.append({"type": "BUY", "why": "20-day breakout on high volume"})
    if i.c < i.lo20:
        sig.append({"type": "SELL", "why": "20-day range breakdown"})
    if p.macd_h < 0 and i.macd_h > 0:
        sig.append({"type": "WATCH", "why": "MACD histogram flipped positive"})
    if i.c < i.bb_lo:
        sig.append({"type": "WATCH", "why": "Close below lower Bollinger band (stretched)"})
    a = float(i.atr14)
    return {
        "symbol": symbol, "close": float(i.c),
        "rsi": round(float(i.rsi14), 1), "trend": "UP" if i.c > i.sma200 else "DOWN",
        "ema20": float(i.ema20), "ema50": float(i.ema50),
        "atr": a, "entry": float(i.c),
        "stop": float(i.c - 1.5 * a), "target": float(i.c + 3 * a),
        "signals": sig,
    }
