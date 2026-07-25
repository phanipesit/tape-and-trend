"""Technical indicators on pandas Series/DataFrames (no TA-Lib dependency)."""
import pandas as pd
import numpy as np

def sma(s: pd.Series, n: int) -> pd.Series:
    return s.rolling(n).mean()

def ema(s: pd.Series, n: int) -> pd.Series:
    return s.ewm(span=n, adjust=False).mean()

def rsi(s: pd.Series, n: int = 14) -> pd.Series:
    d = s.diff()
    up = d.clip(lower=0).ewm(alpha=1 / n, adjust=False).mean()
    dn = (-d.clip(upper=0)).ewm(alpha=1 / n, adjust=False).mean()
    rs = up / dn.replace(0, np.nan)
    out = 100 - 100 / (1 + rs)
    # zero losses so far would leave NaN: all-gains reads 100, truly flat reads 50
    return out.where(dn != 0, np.where(up > 0, 100.0, 50.0))

def macd(s: pd.Series, fast=12, slow=26, sig=9):
    m = ema(s, fast) - ema(s, slow)
    sg = ema(m, sig)
    return m, sg, m - sg

def bollinger(s: pd.Series, n=20, k=2.0):
    mid = sma(s, n)
    sd = s.rolling(n).std(ddof=0)
    return mid + k * sd, mid, mid - k * sd

def atr(df: pd.DataFrame, n: int = 14) -> pd.Series:
    hl = df["h"] - df["l"]
    hc = (df["h"] - df["c"].shift()).abs()
    lc = (df["l"] - df["c"].shift()).abs()
    tr = pd.concat([hl, hc, lc], axis=1).max(axis=1)
    return tr.ewm(span=n, adjust=False).mean()

def enrich(df: pd.DataFrame) -> pd.DataFrame:
    """Attach the standard indicator set used by signals/screener."""
    out = df.copy()
    c = out["c"]
    out["ema20"], out["ema50"], out["sma200"] = ema(c, 20), ema(c, 50), sma(c, 200)
    out["rsi14"] = rsi(c)
    _, _, out["macd_h"] = macd(c)
    out["bb_up"], out["bb_mid"], out["bb_lo"] = bollinger(c)
    out["atr14"] = atr(out)
    out["vol20"] = out["v"].rolling(20).mean()
    out["hi20"] = out["h"].shift(1).rolling(20).max()
    out["lo20"] = out["l"].shift(1).rolling(20).min()
    return out

def vwap(df: pd.DataFrame) -> pd.Series:
    """Cumulative volume-weighted average price, resetting each trading session.
    Sessions are grouped by the UTC calendar date of `ts` — both NSE (9:15-15:30 IST)
    and US (9:30-16:00 ET) market hours fall entirely within one UTC day, so this is a
    safe session boundary without needing per-market timezone conversion."""
    tp = (df["h"] + df["l"] + df["c"]) / 3
    session = df["ts"].dt.date
    cum_pv = (tp * df["v"]).groupby(session).cumsum()
    cum_v = df["v"].groupby(session).cumsum()
    return cum_pv / cum_v.replace(0, np.nan)

def opening_range(df: pd.DataFrame, bars: int) -> tuple[pd.Series, pd.Series]:
    """High/low of each session's first `bars` rows, broadcast across every row in
    that session — the opening-range breakout levels compared against all day."""
    session = df["ts"].dt.date
    grp = df.groupby(session)
    or_hi = grp["h"].transform(lambda s: s.iloc[:bars].max())
    or_lo = grp["l"].transform(lambda s: s.iloc[:bars].min())
    return or_hi, or_lo

def enrich_intraday(df: pd.DataFrame, interval: str = "5m", or_minutes: int = 15) -> pd.DataFrame:
    """Attach the intraday indicator set (VWAP, opening range, fast EMA/RSI) used by
    intraday_signals — a separate function from enrich() because VWAP's session-reset
    grouping is a different shape of computation than the daily indicators."""
    out = df.copy()
    c = out["c"]
    out["vwap"] = vwap(out)
    bars_per_period = int(interval.rstrip("m"))
    or_bars = max(1, or_minutes // bars_per_period)
    out["or_hi"], out["or_lo"] = opening_range(out, or_bars)
    out["ema9"], out["ema20"] = ema(c, 9), ema(c, 20)
    out["rsi7"] = rsi(c, 7)
    out["atr14"] = atr(out)
    out["vol20"] = out["v"].rolling(20).mean()
    return out
