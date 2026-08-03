from fastapi import APIRouter, HTTPException
from ..services import intraday_signals as isig
from ..services.data import refresh_intraday, get_intraday
from ..services.indicators import enrich_intraday

router = APIRouter(prefix="/api", tags=["intraday"])


@router.get("/intraday/candles/{symbol}")
def candles(symbol: str, interval: str = "5m", bars: int = 120):
    """Enriched intraday bars — the exact series the signal engine reasons over.

    Exists because TradingView's free widget is not entitled to NSE data ("this symbol
    is only available on TradingView"), so every Indian symbol drew a blank chart while
    the signals underneath were computed fine. Serving our own cached bars also removes
    a subtler problem: the widget was previously pointed at BSE for Indian names, so the
    chart and the analysis were reading different exchanges.
    """
    df = get_intraday(symbol.upper(), interval)
    if df.empty:
        raise HTTPException(404, f"no intraday bars cached for {symbol.upper()}")
    e = enrich_intraday(df, interval=interval).tail(max(bars, 10))

    def num(v):
        # NaN is not valid JSON and index symbols legitimately produce it for VWAP,
        # since Yahoo reports zero intraday volume for them.
        return None if v is None or v != v else round(float(v), 4)

    return {
        "symbol": symbol.upper(), "interval": interval, "bars": len(e),
        "candles": [{"ts": str(r.ts), "o": num(r.o), "h": num(r.h), "l": num(r.l),
                     "c": num(r.c), "v": int(r.v or 0), "vwap": num(r.vwap),
                     "ema9": num(r.ema9), "ema20": num(r.ema20)} for r in e.itertuples()],
        "or_hi": num(e["or_hi"].iloc[-1]), "or_lo": num(e["or_lo"].iloc[-1]),
    }

@router.get("/intraday/signals/{symbol}")
def signals(symbol: str, interval: str = "5m"):
    try:
        return isig.analyse(symbol.upper(), interval)
    except ValueError as e:
        raise HTTPException(400, str(e))

@router.post("/intraday/{symbol}/refresh")
def refresh(symbol: str, interval: str = "5m"):
    try:
        return {"rows": refresh_intraday(symbol.upper(), interval)}
    except ValueError as e:
        raise HTTPException(400, str(e))
