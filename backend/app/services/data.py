"""Candle + fundamentals layer: yfinance -> PostgreSQL cache -> API."""
import logging
from datetime import datetime, timedelta, timezone
import pandas as pd
import yfinance as yf
from ..db import q, engine
from ..config import CANDLE_STALE_HOURS, FX_STALE_MINUTES, USD_INR_FALLBACK

log = logging.getLogger(__name__)

BSE_OVERRIDE = {"HDFCBANK"}   # symbols with bad Yahoo NSE data → use BSE feed

_fx_cache = {"rate": None, "at": None}

def usd_inr_rate() -> float:
    """Spot USD→INR rate, cached in-process for FX_STALE_MINUTES."""
    now = datetime.now(timezone.utc)
    if _fx_cache["rate"] and now - _fx_cache["at"] < timedelta(minutes=FX_STALE_MINUTES):
        return _fx_cache["rate"]
    try:
        info = yf.Ticker("INR=X").info or {}
        rate = info.get("regularMarketPrice") or info.get("previousClose")
        if rate:
            _fx_cache["rate"], _fx_cache["at"] = float(rate), now
    except Exception:
        log.warning("USD/INR fetch failed, serving %s",
                    "cached rate" if _fx_cache["rate"] else "hardcoded fallback", exc_info=True)
    return _fx_cache["rate"] or USD_INR_FALLBACK

def yf_symbol(symbol: str, market: str) -> str:
    if market == "IN":
        return f"{symbol}.BO" if symbol in BSE_OVERRIDE else f"{symbol}.NS"
    return symbol

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
            log.warning("candle refresh failed for %s, serving stale cache", symbol, exc_info=True)
    rows = q("SELECT d,o,h,l,c,v FROM ohlcv WHERE symbol=:s ORDER BY d DESC LIMIT :n",
             s=symbol, n=limit)
    df = pd.DataFrame(rows[::-1])
    if not df.empty:
        df[["o", "h", "l", "c"]] = df[["o", "h", "l", "c"]].astype(float)
        df["v"] = df["v"].astype("int64")
    return df

def refresh_fundamentals(symbol: str) -> dict:
    meta = get_symbol(symbol)
    candidates = [yf_symbol(symbol, meta["market"])]
    if meta["market"] == "IN":
        first = candidates[0]
        candidates.append(f"{symbol}.BO" if first.endswith(".NS") else f"{symbol}.NS")
    info, last_err = {}, None
    for ysym in candidates:
        try:
            info = yf.Ticker(ysym).info or {}
        except Exception as e:
            last_err = e
            info = {}
            continue
        if info.get("trailingPE") or info.get("marketCap"):
            break
    if not (info.get("trailingPE") or info.get("marketCap")):
        # Don't overwrite a previously-good cache row with nulls, and don't stamp
        # fundamentals_at=now() — that would make a real failure look like a
        # freshly-confirmed "no data available" instead of something to retry.
        tried = ", ".join(candidates)
        raise RuntimeError(f"no fundamentals for {symbol} (tried {tried})") from last_err
    vals = dict(
        pe=info.get("trailingPE"),
        roe=(info.get("returnOnEquity") or 0) * 100 or None,
        de=(info.get("debtToEquity") or 0) / 100 or None,   # yahoo reports in %
        rev_growth=(info.get("revenueGrowth") or 0) * 100 or None,
        mcap=info.get("marketCap"),
        div_yield=round(float(info.get("dividendYield") or 0), 2) or None,
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
