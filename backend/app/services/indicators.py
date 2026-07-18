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
    return 100 - 100 / (1 + rs)

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
