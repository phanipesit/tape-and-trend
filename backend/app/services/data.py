"""Candle + fundamentals layer: yfinance -> PostgreSQL cache -> API."""
from datetime import datetime, timedelta, timezone
import pandas as pd
import yfinance as yf
from ..db import q, engine
from ..config import CANDLE_STALE_HOURS

def yf_symbol(symbol: str, market: str) -> str:
    return f"{symbol}.NS" if market == "IN" else symbol

def get_symbol(symbol: str) -> dict:
    rows = q("SELECT * FROM symbols WHERE symbol=:s", s=symbol)
    if not rows:
        raise ValueError(f"unknown symbol {symbol}")
    return rows[0]

def all_symbols(market: str | None = None) -> list[dict]:
    if market in ("IN", "US"):
        return q("SELECT * FROM symbols WHERE market=:m ORDER BY symbol", m=market)
    return q("SELECT * FROM symbols ORDER BY market, symbol")

def _cache_fresh(symbol: str) -> bool:
    rows = q("SELECT max(d) AS last FROM ohlcv WHERE symbol=:s", s=symbol)
    last = rows[0]["last"]
    if last is None:
        return False
    return (datetime.now(timezone.utc).date() - last) <= timedelta(days=1) or \
           _recent_fetch(symbol)

def _recent_fetch(symbol: str) -> bool:
    # crude staleness guard: if we've written today's/yesterday's bar, don't refetch within CANDLE_STALE_HOURS
    return False

def refresh_candles(symbol: str, period: str = "2y") -> int:
    meta = get_symbol(symbol)
    df = yf.download(yf_symbol(symbol, meta["market"]), period=period,
                     interval="1d", auto_adjust=True, progress=False)
    if df.empty:
        return 0
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    df = df.rename(columns={"Open": "o", "High": "h", "Low": "l", "Close": "c", "Volume": "v"})
    df = df[["o", "h", "l", "c", "v"]].dropna()
    with engine.begin() as cx:
        for d, r in df.iterrows():
            cx.exec_driver_sql(
                """INSERT INTO ohlcv (symbol,d,o,h,l,c,v) VALUES (%s,%s,%s,%s,%s,%s,%s)
                   ON CONFLICT (symbol,d) DO UPDATE SET o=EXCLUDED.o,h=EXCLUDED.h,
                   l=EXCLUDED.l,c=EXCLUDED.c,v=EXCLUDED.v""",
                (symbol, d.date(), float(r.o), float(r.h), float(r.l), float(r.c), int(r.v or 0)))
    return len(df)

def get_candles(symbol: str, limit: int = 500, auto: bool = True) -> pd.DataFrame:
    if auto and not _cache_fresh(symbol):
        try:
            refresh_candles(symbol)
        except Exception:
            pass  # serve stale cache if yahoo hiccups
    rows = q("SELECT d,o,h,l,c,v FROM ohlcv WHERE symbol=:s ORDER BY d DESC LIMIT :n",
             s=symbol, n=limit)
    df = pd.DataFrame(rows[::-1])
    if not df.empty:
        df[["o", "h", "l", "c"]] = df[["o", "h", "l", "c"]].astype(float)
        df["v"] = df["v"].astype("int64")
    return df

def refresh_fundamentals(symbol: str) -> dict:
    meta = get_symbol(symbol)
    info = yf.Ticker(yf_symbol(symbol, meta["market"])).info or {}
    vals = dict(
        pe=info.get("trailingPE"),
        roe=(info.get("returnOnEquity") or 0) * 100 or None,
        de=(info.get("debtToEquity") or 0) / 100 or None,   # yahoo reports in %
        rev_growth=(info.get("revenueGrowth") or 0) * 100 or None,
        mcap=info.get("marketCap"),
        div_yield=(info.get("dividendYield") or 0) * 100 or None,
    )
    q("""UPDATE symbols SET pe=:pe, roe=:roe, de=:de, rev_growth=:rev_growth,
         mcap=:mcap, div_yield=:div_yield, fundamentals_at=now() WHERE symbol=:s""",
      s=symbol, **vals)
    return vals

def quote(symbol: str) -> dict:
    df = get_candles(symbol, limit=2, auto=False)
    if len(df) < 2:
        df = get_candles(symbol, limit=2, auto=True)
    if df.empty:
        return {"symbol": symbol, "price": None, "change": None, "pct": None}
    last, prev = df.iloc[-1], df.iloc[-2] if len(df) > 1 else df.iloc[-1]
    return {"symbol": symbol, "price": float(last.c),
            "change": float(last.c - prev.c),
            "pct": float((last.c / prev.c - 1) * 100) if prev.c else 0.0,
            "date": str(last.d)}
