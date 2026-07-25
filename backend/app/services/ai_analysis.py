"""AI stock analysis: Claude API when ANTHROPIC_API_KEY is set, rule-based narrative otherwise."""
import json
import logging

from .data import get_candles, get_symbol
from .indicators import enrich
from .news import ticker_news
from .signals import analyse
from ..config import ANTHROPIC_API_KEY

log = logging.getLogger(__name__)

CLAUDE_MODEL = "claude-opus-4-8"

SYSTEM = """You are the analysis engine inside Tape & Trend, an educational trading workbench \
covering Indian (NSE/BSE) and US equities. You are given a JSON snapshot of one stock: daily \
OHLC history summary, technical indicators, the app's mechanical swing signals with an \
ATR-based trade plan, cached fundamentals, and recent headlines.

Write a clear, honest read of the chart and the stock in Markdown, for a retail swing trader. \
Structure it exactly as:

## Trend
## Momentum & volume
## Key levels
## Fundamentals
## What could go wrong
## Bottom line

Rules: ground every claim in the supplied data — never invent prices, events, or fundamentals. \
If a field is null, say the data isn't available rather than guessing. Reference the mechanical \
signals and say whether you agree with them and why. Keep it under 350 words, plain language, \
no hype. End with a one-line reminder that this is educational analysis, not investment advice."""

SYSTEM_OPTIONS = """You are the analysis engine inside Tape & Trend, an educational trading workbench \
covering Indian (NSE/BSE) and US equities and indices. You are given a JSON snapshot of one \
underlying (daily OHLC history summary, technical indicators, the app's mechanical swing signals \
with an ATR-based trade plan, cached fundamentals, recent headlines) plus a specific options \
strategy the user is considering on it (legs, net premium, max profit/loss, break-even prices).

Write a clear, honest read in Markdown for a retail options trader. Structure it exactly as:

## Trend
## Momentum & volume
## Key levels
## Strategy fit
## Fundamentals
## What could go wrong
## Bottom line

Rules: ground every claim in the supplied data — never invent prices, events, fundamentals, or \
implied volatility (none is supplied; the strategy's premiums are illustrative placeholders, not \
live option-chain quotes — say so explicitly if you discuss premium richness/cheapness). If a \
field is null, say the data isn't available rather than guessing. In "Strategy fit", state the \
strategy's directional/volatility bias plainly and compare it against the underlying's mechanical \
signals and trend — does the current technical read support this trade, conflict with it, or is \
it a volatility/range play where trend direction barely matters? Note that "direction" in the \
supplied data defaults to LONG whenever no rule has actually fired (score 0.0, empty \
mechanical_signals) — that default is a data-plumbing placeholder, not a bullish signal, so never \
describe it as supporting a bullish trade unless mechanical_signals is non-empty. Comment on \
whether the break-even(s) sit inside or outside the current 20-day range / ATR-based plan. Keep it under 400 \
words, plain language, no hype. End with a one-line reminder that premiums shown are placeholders \
and this is educational analysis, not investment advice."""


def _pct(cur: float, past: float) -> float | None:
    return round((cur / past - 1) * 100, 1) if past else None


def _context(symbol: str) -> dict:
    meta = get_symbol(symbol)
    a = analyse(symbol)
    if "error" in a:
        raise ValueError(f"{symbol}: {a['error']}")
    e = enrich(get_candles(symbol))
    c = e["c"]
    last = e.iloc[-1]
    lookbacks = {"1w": 5, "1m": 21, "3m": 63, "6m": 126, "1y": 252}
    perf = {k: _pct(float(c.iloc[-1]), float(c.iloc[-n - 1]))
            for k, n in lookbacks.items() if len(c) > n}
    yr = e.tail(252)
    news = [n["title"] for n in ticker_news(symbol, 5)]
    return {
        "symbol": symbol, "name": meta.get("name"), "market": meta["market"],
        "sector": meta.get("sector"), "close": a["close"], "performance_pct": perf,
        "52w_high": round(float(yr["h"].max()), 2), "52w_low": round(float(yr["l"].min()), 2),
        "indicators": {
            "rsi14": a["rsi"], "ema20": round(a["ema20"], 2), "ema50": round(a["ema50"], 2),
            "sma200": round(float(last.sma200), 2) if last.sma200 == last.sma200 else None,
            "macd_hist": round(float(last.macd_h), 3), "atr14": round(a["atr"], 2),
            "rvol": a["rvol"], "bb_upper": round(float(last.bb_up), 2),
            "bb_lower": round(float(last.bb_lo), 2),
            "high_20d": round(float(last.hi20), 2), "low_20d": round(float(last.lo20), 2),
        },
        "trend": a["trend"], "mechanical_signals": a["signals"],
        "conviction_score": a["score"], "direction": a["direction"],
        "trade_plan": {"entry": round(a["entry"], 2), "stop": round(a["stop"], 2),
                       "target": round(a["target"], 2)},
        "fundamentals": {k: (float(meta[k]) if meta.get(k) is not None else None)
                         for k in ("pe", "roe", "de", "rev_growth", "div_yield", "mcap")},
        "recent_headlines": news,
    }


def _claude(ctx: dict, system: str = SYSTEM, task: str = "stock") -> str:
    import anthropic  # lazy: the fallback path must work even if the package is absent

    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY, timeout=90.0, max_retries=1)
    response = client.messages.create(
        model=CLAUDE_MODEL,
        max_tokens=16000,
        thinking={"type": "adaptive"},
        system=system,
        messages=[{"role": "user", "content":
                   f"Analyse this {task}:\n\n```json\n{json.dumps(ctx, indent=1)}\n```"}],
    )
    if response.stop_reason == "refusal":
        raise RuntimeError("Claude declined to analyse this request")
    text = "".join(b.text for b in response.content if b.type == "text").strip()
    if not text:
        raise RuntimeError("empty response from Claude")
    return text


def _rule_based(ctx: dict) -> str:
    i, f = ctx["indicators"], ctx["fundamentals"]
    close, perf = ctx["close"], ctx["performance_pct"]
    lines = ["## Trend"]
    if i["sma200"] is not None:
        rel = "above" if close > i["sma200"] else "below"
        lines.append(f"Price {ctx['close']:.2f} is {rel} the 200-day average ({i['sma200']:.2f}) — "
                     f"the long-term trend reads **{ctx['trend']}**.")
    stack = "bullish (20 EMA over 50 EMA)" if i["ema20"] > i["ema50"] else "bearish (20 EMA under 50 EMA)"
    lines.append(f"The short-term EMA stack is {stack}. "
                 + " · ".join(f"{k}: {v:+.1f}%" for k, v in perf.items() if v is not None))

    lines.append("\n## Momentum & volume")
    rsi = i["rsi14"]
    zone = "oversold" if rsi < 32 else "overbought" if rsi > 72 else "neutral"
    macd = "positive" if i["macd_hist"] > 0 else "negative"
    lines.append(f"RSI-14 is {rsi:.0f} ({zone}); the MACD histogram is {macd}. "
                 f"Relative volume is {i['rvol']:.2f}× the 20-day average"
                 + (" — unusual activity." if i["rvol"] >= 1.5 else "."))

    lines.append("\n## Key levels")
    lines.append(f"20-day range: {i['low_20d']:.2f} – {i['high_20d']:.2f}. "
                 f"Bollinger band: {i['bb_lower']:.2f} – {i['bb_upper']:.2f}. "
                 f"52-week range: {ctx['52w_low']:.2f} – {ctx['52w_high']:.2f}. "
                 f"ATR-14 is {i['atr14']:.2f}, giving the {ctx['direction'].lower()} plan: "
                 f"entry {ctx['trade_plan']['entry']:.2f}, stop {ctx['trade_plan']['stop']:.2f}, "
                 f"target {ctx['trade_plan']['target']:.2f}.")

    if ctx.get("strategy"):
        st = ctx["strategy"]
        lines.append("\n## Strategy fit")
        lines.append(f"**{st['name']}** — {st['desc']}")
        leg_txt = "; ".join(f"{'long' if L['qty'] > 0 else 'short'} {L['type']} {L['strike']:g} "
                            f"(prem {L['premium']:.2f}, qty {L['qty']:+g})" for L in st["legs"])
        lines.append(f"Legs: {leg_txt}. Net premium {st['net_premium']:.2f}, "
                     f"max profit {st['max_profit']}, max loss {st['max_loss']}, "
                     f"break-even(s) {', '.join(f'{b:.2f}' for b in st['breakevens']) or 'none in range'}.")
        directional = "bullish" in st["desc"].lower() or "bearish" in st["desc"].lower()
        if not directional:
            lines.append("This is a volatility/range strategy — the mechanical trend direction "
                         "matters less here than whether price actually moves (or stays still) enough.")
        elif not ctx["mechanical_signals"]:
            lines.append("No mechanical signal is currently active (score 0.0) — this strategy's "
                         "directional bet isn't backed by a triggered rule either way right now.")
        else:
            agree = (("bullish" in st["desc"].lower() and ctx["direction"] == "LONG")
                    or ("bearish" in st["desc"].lower() and ctx["direction"] == "SHORT"))
            lines.append(f"The mechanical read (**{ctx['direction']}**, score {ctx['conviction_score']:.1f}) "
                         f"{'agrees with' if agree else 'sits against'} this strategy's stated bias.")
        lo20, hi20 = ctx["indicators"]["low_20d"], ctx["indicators"]["high_20d"]
        outside = [b for b in st["breakevens"] if b < lo20 or b > hi20]
        if st["breakevens"]:
            lines.append(f"20-day range is {lo20:.2f}–{hi20:.2f}; "
                         + (f"break-even(s) {', '.join(f'{b:.2f}' for b in outside)} sit outside it — "
                            "a bigger move than the recent range is needed." if outside
                            else "break-even(s) sit inside it — a smaller, more ordinary move would do it."))
        lines.append("*Premiums are illustrative placeholders, not live option-chain quotes.*")

    lines.append("\n## Fundamentals")
    fund_bits = []
    if f["pe"] is not None:
        fund_bits.append(f"P/E {f['pe']:.1f}" + (" (rich)" if f["pe"] > 40 else " (moderate)" if f["pe"] > 20 else " (cheap)"))
    if f["roe"] is not None:
        fund_bits.append(f"ROE {f['roe']:.1f}%" + (" — strong" if f["roe"] >= 15 else ""))
    if f["de"] is not None:
        fund_bits.append(f"D/E {f['de']:.2f}" + (" — leveraged" if f["de"] > 2 else ""))
    if f["rev_growth"] is not None:
        fund_bits.append(f"revenue growth {f['rev_growth']:.1f}%")
    if f["div_yield"] is not None:
        fund_bits.append(f"dividend yield {f['div_yield']:.2f}%")
    lines.append(("; ".join(fund_bits) + ".") if fund_bits
                 else "No cached fundamentals — refresh them from the screener page.")

    lines.append("\n## Mechanical signals")
    if ctx["mechanical_signals"]:
        lines += [f"- **{s['type']}** — {s['why']}" for s in ctx["mechanical_signals"]]
        lines.append(f"Net direction **{ctx['direction']}**, conviction score {ctx['conviction_score']:.1f}.")
    else:
        lines.append("No rules fired on the latest bar — no fresh setup here.")

    lines.append("\n## Bottom line")
    lines.append(f"{ctx['symbol']} is in a {ctx['trend'].lower()}-trend with {zone} momentum"
                 + (f" and {len(ctx['mechanical_signals'])} active signal(s)." if ctx["mechanical_signals"]
                    else " and no active setup — patience over action."))
    lines.append("\n*Rule-based summary (no AI key configured). Educational tool — not investment advice.*")
    return "\n".join(lines)


def _run(ctx: dict, system: str, task: str) -> dict:
    out = {"symbol": ctx["symbol"], "close": ctx["close"], "direction": ctx["direction"]}
    if ANTHROPIC_API_KEY:
        try:
            return {**out, "source": "claude", "model": CLAUDE_MODEL,
                    "analysis": _claude(ctx, system, task)}
        except Exception as e:
            log.warning("Claude analysis failed for %s, falling back to rules",
                       ctx["symbol"], exc_info=True)
            return {**out, "source": "rules", "analysis": _rule_based(ctx),
                    "note": f"Claude call failed ({type(e).__name__}) — showing rule-based analysis."}
    return {**out, "source": "rules", "analysis": _rule_based(ctx)}


def analyze(symbol: str) -> dict:
    return _run(_context(symbol), SYSTEM, "stock")


def analyze_options(symbol: str, strategy_name: str, strategy_desc: str, legs: list[dict],
                    net_premium: float, max_profit: str, max_loss: str,
                    breakevens: list[float]) -> dict:
    ctx = _context(symbol)
    ctx["strategy"] = {"name": strategy_name, "desc": strategy_desc, "legs": legs,
                       "net_premium": net_premium, "max_profit": max_profit,
                       "max_loss": max_loss, "breakevens": breakevens}
    return _run(ctx, SYSTEM_OPTIONS, "options strategy")
