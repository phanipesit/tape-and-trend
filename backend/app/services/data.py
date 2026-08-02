"""Candle + fundamentals layer: yfinance -> PostgreSQL cache -> API."""
import logging
import threading
from datetime import datetime, timedelta, timezone
import pandas as pd
import yfinance as yf
from ..db import q, engine
from ..config import CANDLE_STALE_HOURS, FX_STALE_MINUTES, USD_INR_FALLBACK, INTRADAY_STALE_MINUTES

log = logging.getLogger(__name__)

BSE_OVERRIDE = {"HDFCBANK"}   # symbols with bad Yahoo NSE data → use BSE feed

# yfinance shares one session/cache across threads and is NOT thread-safe:
# concurrent downloads from parallel request handlers (e.g. /watchlist and
# /signals fired together by the dashboard) can cross-wire responses, writing
# symbol A's candles under symbol B. All yfinance network access must hold
# this lock.
YF_LOCK = threading.Lock()

def yf_download(ysym: str, **kwargs) -> pd.DataFrame:
    with YF_LOCK:
        return yf.download(ysym, progress=False, **kwargs)

def yf_info(ysym: str) -> dict:
    with YF_LOCK:
        return yf.Ticker(ysym).info or {}

_fx_cache = {"rate": None, "at": None}

def usd_inr_rate() -> float:
    """Spot USD→INR rate, cached in-process for FX_STALE_MINUTES."""
    now = datetime.now(timezone.utc)
    if _fx_cache["rate"] and now - _fx_cache["at"] < timedelta(minutes=FX_STALE_MINUTES):
        return _fx_cache["rate"]
    try:
        info = yf_info("INR=X")
        rate = info.get("regularMarketPrice") or info.get("previousClose")
        if rate:
            _fx_cache["rate"], _fx_cache["at"] = float(rate), now
    except Exception:
        if _fx_cache["rate"]:
            _fx_cache["at"] = now   # hold the cached rate for a full window before re-hitting a failing feed
        log.warning("USD/INR fetch failed, serving %s",
                    "cached rate" if _fx_cache["rate"] else "hardcoded fallback", exc_info=True)
    return _fx_cache["rate"] or USD_INR_FALLBACK

def yf_symbol(symbol: str, market: str) -> str:
    if symbol.startswith("^"):   # index ticker (e.g. ^NSEI, ^GSPC) — already the exact Yahoo symbol
        return symbol
    if market == "IN":
        return f"{symbol}.BO" if symbol in BSE_OVERRIDE else f"{symbol}.NS"
    return symbol

def get_symbol(symbol: str) -> dict:
    rows = q("SELECT * FROM symbols WHERE symbol=:s", s=symbol)
    if not rows:
        raise ValueError(f"unknown symbol {symbol}")
    return rows[0]

def all_symbols(market: str | None = None, include_index: bool = False) -> list[dict]:
    # Filter on asset_class, not is_index. migration_010 added display-only rows
    # (world indices, metals, WTI/DXY/VIX) that are deliberately is_index=false so
    # they stay out of the options-underlying picker and out of get_index_symbol()'s
    # regime lookup — but that means an is_index filter alone would have leaked gold
    # futures into every *stock* picker instead. asset_class carries the distinction.
    classes = "'equity','index'" if include_index else "'equity'"
    conds, params = [f"asset_class IN ({classes})"], {}
    if market in ("IN", "US"):
        conds.append("market = :m")
        params["m"] = market
    where = "WHERE " + " AND ".join(conds)
    return q(f"SELECT * FROM symbols {where} ORDER BY market, symbol", **params)


def market_context(asset_classes: tuple[str, ...] = ("index", "global", "metal", "macro")) -> list[dict]:
    """Display-only rows for the dashboard's global board — never stock pickers.
    Only rows with a region set appear; ^NSEBANK is an options underlying, not a
    headline gauge, so it is deliberately region-NULL and excluded."""
    classes = ",".join(f"'{c}'" for c in asset_classes)
    return q(f"""SELECT symbol, name, market, asset_class, region FROM symbols
                 WHERE asset_class IN ({classes}) AND region IS NOT NULL
                 ORDER BY region, symbol""")

def get_index_symbol(market: str) -> str:
    rows = q("SELECT symbol FROM symbols WHERE market=:m AND is_index=true LIMIT 1", m=market)
    if not rows:
        raise ValueError(f"no index symbol configured for market {market}")
    return rows[0]["symbol"]

_last_fetch: dict[str, datetime] = {}
_fetch_failed: set[str] = set()   # symbols whose most recent refresh attempt errored

def _cache_fresh(symbol: str) -> bool:
    rows = q("SELECT max(d) AS last FROM ohlcv WHERE symbol=:s", s=symbol)
    last = rows[0]["last"]
    if last is None:
        return False
    return (datetime.now(timezone.utc).date() - last) <= timedelta(days=1) or \
           _recent_fetch(symbol)

def _recent_fetch(symbol: str) -> bool:
    # Over weekends/holidays the newest bar stays >1 day old no matter how often we
    # refetch, so the max(d) check alone would re-hit yfinance on every read.
    at = _last_fetch.get(symbol)
    return at is not None and datetime.now(timezone.utc) - at < timedelta(hours=CANDLE_STALE_HOURS)

def refresh_candles(symbol: str, period: str = "2y") -> int:
    meta = get_symbol(symbol)
    ysym = yf_symbol(symbol, meta["market"])
    df = yf_download(ysym, period=period, interval="1d", auto_adjust=True)
    if meta["market"] == "IN" and len(df) < 50:
        # one exchange's Yahoo feed sometimes goes bad (returns a bar or two);
        # fall back to the other listing before giving up
        alt = f"{symbol}.NS" if ysym.endswith(".BO") else f"{symbol}.BO"
        alt_df = yf_download(alt, period=period, interval="1d", auto_adjust=True)
        if len(alt_df) > len(df):
            log.warning("%s: %s returned %d bars, using %s (%d bars) instead",
                        symbol, ysym, len(df), alt, len(alt_df))
            df = alt_df
    _last_fetch[symbol] = datetime.now(timezone.utc)
    _fetch_failed.discard(symbol)
    if df.empty:
        return 0
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    df = df.rename(columns={"Open": "o", "High": "h", "Low": "l", "Close": "c", "Volume": "v"})
    df = df[["o", "h", "l", "c", "v"]].dropna()
    rows = [(symbol, d.date(), float(r.o), float(r.h), float(r.l), float(r.c), int(r.v or 0))
            for d, r in df.iterrows()]
    with engine.begin() as cx:
        cx.exec_driver_sql(
            "INSERT INTO ohlcv (symbol,d,o,h,l,c,v) VALUES "
            + ",".join(["(%s,%s,%s,%s,%s,%s,%s)"] * len(rows))
            + """ ON CONFLICT (symbol,d) DO UPDATE SET o=EXCLUDED.o,h=EXCLUDED.h,
                  l=EXCLUDED.l,c=EXCLUDED.c,v=EXCLUDED.v""",
            tuple(p for row in rows for p in row))
    return len(rows)

def get_candles(symbol: str, limit: int = 500, auto: bool = True) -> pd.DataFrame:
    if auto and not _cache_fresh(symbol):
        try:
            refresh_candles(symbol)
        except Exception:
            _fetch_failed.add(symbol)
            log.warning("candle refresh failed for %s, serving stale cache", symbol, exc_info=True)
    rows = q("SELECT d,o,h,l,c,v FROM ohlcv WHERE symbol=:s ORDER BY d DESC LIMIT :n",
             s=symbol, n=limit)
    df = pd.DataFrame(rows[::-1])
    if not df.empty:
        df[["o", "h", "l", "c"]] = df[["o", "h", "l", "c"]].astype(float)
        df["v"] = df["v"].astype("int64")
    return df

# Yahoo's real intraday history limits (verified live against this app's pinned
# yfinance version): 1m bars only go back 7 days, 5m/15m go back 60 days.
_INTRADAY_PERIOD = {"1m": "7d", "5m": "60d", "15m": "60d"}
_intraday_last_fetch: dict[tuple[str, str], datetime] = {}

def _intraday_cache_fresh(symbol: str, interval: str) -> bool:
    at = _intraday_last_fetch.get((symbol, interval))
    return at is not None and datetime.now(timezone.utc) - at < timedelta(minutes=INTRADAY_STALE_MINUTES)

def refresh_intraday(symbol: str, interval: str = "5m") -> int:
    if interval not in _INTRADAY_PERIOD:
        raise ValueError(f"unsupported intraday interval {interval}")
    meta = get_symbol(symbol)
    ysym = yf_symbol(symbol, meta["market"])
    df = yf_download(ysym, period=_INTRADAY_PERIOD[interval], interval=interval, auto_adjust=True)
    _intraday_last_fetch[(symbol, interval)] = datetime.now(timezone.utc)
    if df.empty:
        return 0
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    df = df.rename(columns={"Open": "o", "High": "h", "Low": "l", "Close": "c", "Volume": "v"})
    df = df[["o", "h", "l", "c", "v"]].dropna()
    rows = [(symbol, interval, ts.to_pydatetime(), float(r.o), float(r.h), float(r.l),
            float(r.c), int(r.v or 0)) for ts, r in df.iterrows()]
    with engine.begin() as cx:
        cx.exec_driver_sql(
            "INSERT INTO intraday_ohlcv (symbol,interval,ts,o,h,l,c,v) VALUES "
            + ",".join(["(%s,%s,%s,%s,%s,%s,%s,%s)"] * len(rows))
            + """ ON CONFLICT (symbol,interval,ts) DO UPDATE SET o=EXCLUDED.o,h=EXCLUDED.h,
                  l=EXCLUDED.l,c=EXCLUDED.c,v=EXCLUDED.v""",
            tuple(p for row in rows for p in row))
    return len(rows)

def get_intraday(symbol: str, interval: str = "5m", limit: int = 500, auto: bool = True) -> pd.DataFrame:
    if auto and not _intraday_cache_fresh(symbol, interval):
        try:
            refresh_intraday(symbol, interval)
        except Exception:
            log.warning("intraday refresh failed for %s@%s, serving stale cache",
                       symbol, interval, exc_info=True)
    rows = q("""SELECT ts,o,h,l,c,v FROM intraday_ohlcv WHERE symbol=:s AND interval=:i
                ORDER BY ts DESC LIMIT :n""", s=symbol, i=interval, n=limit)
    df = pd.DataFrame(rows[::-1])
    if not df.empty:
        df[["o", "h", "l", "c"]] = df[["o", "h", "l", "c"]].astype(float)
        df["v"] = df["v"].astype("int64")
        df["ts"] = pd.to_datetime(df["ts"], utc=True)
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
            info = yf_info(ysym)
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
        return {"symbol": symbol, "price": None, "change": None, "pct": None, "stale": True}
    last, prev = df.iloc[-1], df.iloc[-2] if len(df) > 1 else df.iloc[-1]
    return {"symbol": symbol, "price": float(last.c),
            "change": float(last.c - prev.c),
            "pct": float((last.c / prev.c - 1) * 100) if prev.c else 0.0,
            "date": str(last.d), "stale": symbol in _fetch_failed}
