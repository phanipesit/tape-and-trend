"""AI stock analysis: Claude API, then a local model via Ollama, then a rule-based narrative."""
import json
import logging

from .data import get_candles, get_symbol
from .indicators import enrich
from .news import ticker_news
from .signals import analyse
from ..config import (ANTHROPIC_API_KEY, OLLAMA_MODEL, OLLAMA_NUM_CTX, OLLAMA_TIMEOUT,
                      OLLAMA_URL)

log = logging.getLogger(__name__)

CLAUDE_MODEL = "claude-opus-5"

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
If a field is null, say the data isn't available rather than guessing.

Do not re-derive anything already classified for you in the `derived` block: use \
`derived.rsi_zone` rather than judging the RSI number, `derived.volume_vs_20d_average` rather \
than judging RVOL, `derived.price_vs_sma200` and `derived.ema_stack` for trend structure, and \
`derived.any_signal_fired` rather than inferring from the signal list. Restate those in plain \
language instead of doing your own arithmetic.

Reference the mechanical signals and say whether you agree with them and why. `signal_direction` \
is null when no rule has fired — say there is no mechanical edge right now rather than inferring \
one; `trade_plan.direction` falls back to LONG so the plan is always loadable and is not a view. \
Keep it under 350 words, plain language, no hype. End with a one-line reminder that this is educational analysis, \
not investment advice."""

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

Rules: ground every claim in the supplied data — never invent prices, events, or fundamentals.

Do not compute or re-derive anything. The snapshot already contains the conclusions you need, \
pre-computed: use `derived.rsi_zone` rather than judging the RSI number yourself, \
`derived.volume_vs_20d_average` rather than judging RVOL, `derived.any_signal_fired` rather than \
inferring from the signal list, and `strategy.breakevens_vs_range` rather than comparing the \
break-evens against the range yourself. Restate those fields in plain language. If you ever find \
yourself doing arithmetic, stop and quote the pre-computed field instead.

The premiums are theoretical Black-Scholes values priced off the underlying's realized volatility \
(`strategy.realized_vol_pct`) at `strategy.days_to_expiry` days — NOT live option-chain quotes and \
NOT implied volatility. Say so if you discuss whether the premium is rich or cheap; real quotes \
will differ, usually because implied vol differs from realized. `strategy.position_greeks` are \
qty-weighted position totals (theta per calendar day, vega per 1 percentage point of vol).

If a field is null, say the data isn't available rather than guessing. In "Strategy fit", state the \
strategy's directional/volatility bias plainly and compare it against the underlying's mechanical \
signals and trend — does the current technical read support this trade, conflict with it, or is \
it a volatility/range play where trend direction barely matters? `signal_direction` is the ONLY \
field that carries a mechanical view: when it is null no rule has fired, so say plainly that \
nothing backs this trade either way, and never claim the strategy "aligns with the mechanical \
signals". Ignore `trade_plan.direction` for this judgement — it falls back to LONG so the plan is \
always loadable. Where the Greeks \
are informative, use them: theta is what the position bleeds per day, vega its exposure to a \
volatility shift. Keep it under 400 words, plain language, no hype. End with a one-line reminder \
that premiums are model estimates rather than live quotes, and that this is educational analysis, \
not investment advice."""


def _pct(cur: float, past: float) -> float | None:
    return round((cur / past - 1) * 100, 1) if past else None


# Small models reliably misread raw indicator values — llama3 called RSI 48.8 "oversold",
# RVOL 1.02 "relatively high", and a break-even inside the 20-day range "outside" it, then
# built a risk conclusion on that. So classify here and hand the model conclusions to
# narrate rather than numbers to derive. Shared with _rule_based so the two can't drift.
def _rsi_zone(rsi: float) -> str:
    return "oversold" if rsi < 32 else "overbought" if rsi > 72 else "neutral"


def _rvol_note(rvol: float) -> str:
    return ("unusually heavy" if rvol >= 1.5 else
            "above average" if rvol >= 1.15 else
            "below average" if rvol <= 0.85 else "about average")


def _range_note(values: list[float], lo: float, hi: float) -> str | None:
    """Whether each value sits inside or outside the [lo, hi] band."""
    if not values:
        return None
    outside = [v for v in values if v < lo or v > hi]
    if not outside:
        return f"all inside the 20-day range {lo:.2f}-{hi:.2f}"
    return (f"{', '.join(f'{v:.2f}' for v in outside)} outside the 20-day range "
            f"{lo:.2f}-{hi:.2f} (a bigger move than recent action is needed)")


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
        "conviction_score": a["score"],
        # NOT a["direction"]. signals.analyse() defaults direction to LONG when nothing has
        # fired, so the risk calculator can always load a plan — that default is plumbing,
        # not a bullish read. Shipping it as a real field made the narrative describe flat
        # tape as "aligned with the mechanical signals". null is the honest value; the
        # default still travels with the plan below, where it means something.
        "signal_direction": a["direction"] if a["signals"] else None,
        # Pre-classified so the narrative can't invert them (see _rsi_zone comment).
        "derived": {
            "rsi_zone": _rsi_zone(a["rsi"]),
            "volume_vs_20d_average": _rvol_note(a["rvol"]),
            "price_vs_sma200": (None if last.sma200 != last.sma200 else
                                "above" if a["close"] > float(last.sma200) else "below"),
            "ema_stack": "bullish (20>50)" if a["ema20"] > a["ema50"] else "bearish (20<50)",
            "any_signal_fired": bool(a["signals"]),
        },
        "trade_plan": {"direction": a["direction"], "entry": round(a["entry"], 2),
                       "stop": round(a["stop"], 2), "target": round(a["target"], 2),
                       "note": ("ATR-based levels. Direction falls back to LONG when no rule "
                                "has fired, so the plan is always loadable — check "
                                "signal_direction before reading it as a view.")},
        "fundamentals": {k: (float(meta[k]) if meta.get(k) is not None else None)
                         for k in ("pe", "roe", "de", "rev_growth", "div_yield", "mcap")},
        "recent_headlines": news,
    }


def _user_msg(ctx: dict, task: str) -> str:
    return f"Analyse this {task}:\n\n```json\n{json.dumps(ctx, indent=1)}\n```"


def _claude(ctx: dict, system: str = SYSTEM, task: str = "stock") -> str:
    import anthropic  # lazy: the fallback path must work even if the package is absent

    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY, timeout=90.0, max_retries=1)
    response = client.messages.create(
        model=CLAUDE_MODEL,
        max_tokens=16000,
        thinking={"type": "adaptive"},
        system=system,
        messages=[{"role": "user", "content": _user_msg(ctx, task)}],
    )
    if response.stop_reason == "refusal":
        raise RuntimeError("Claude declined to analyse this request")
    text = "".join(b.text for b in response.content if b.type == "text").strip()
    if not text:
        raise RuntimeError("empty response from Claude")
    return text


def _ollama(ctx: dict, system: str = SYSTEM, task: str = "stock") -> str:
    """Local model through Ollama's /api/chat. No key, no cost, but slow and much smaller
    than Claude — the prompts are shared, so quality is the only thing that differs."""
    import httpx  # lazy, same reason as _claude

    r = httpx.post(
        f"{OLLAMA_URL}/api/chat",
        timeout=OLLAMA_TIMEOUT,
        json={
            "model": OLLAMA_MODEL,
            "stream": False,
            "messages": [{"role": "system", "content": system},
                         {"role": "user", "content": _user_msg(ctx, task)}],
            # num_ctx must be set explicitly: Ollama truncates to 4096 by default, which
            # would silently cut the tail off our JSON snapshot.
            "options": {"temperature": 0.3, "num_ctx": OLLAMA_NUM_CTX},
        },
    )
    r.raise_for_status()
    text = (r.json().get("message") or {}).get("content", "").strip()
    if not text:
        raise RuntimeError("empty response from Ollama")
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
    zone = _rsi_zone(rsi)
    macd = "positive" if i["macd_hist"] > 0 else "negative"
    lines.append(f"RSI-14 is {rsi:.0f} ({zone}); the MACD histogram is {macd}. "
                 f"Relative volume is {i['rvol']:.2f}× the 20-day average "
                 f"({_rvol_note(i['rvol'])}).")

    lines.append("\n## Key levels")
    lines.append(f"20-day range: {i['low_20d']:.2f} – {i['high_20d']:.2f}. "
                 f"Bollinger band: {i['bb_lower']:.2f} – {i['bb_upper']:.2f}. "
                 f"52-week range: {ctx['52w_low']:.2f} – {ctx['52w_high']:.2f}. "
                 f"ATR-14 is {i['atr14']:.2f}, giving the {ctx['trade_plan']['direction'].lower()} plan: "
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
        if st.get("realized_vol_pct") is not None:
            lines.append(f"Priced at {st['realized_vol_pct']:.1f}% realized volatility, "
                         f"{st.get('days_to_expiry', '?')} days to expiry.")
        g = st.get("position_greeks")
        if g:
            lines.append(f"Position Greeks — delta {g['delta']:+.3f}, theta {g['theta']:+.3f}/day, "
                         f"vega {g['vega']:+.3f} per 1% vol, gamma {g['gamma']:.4f}. "
                         + ("Time decay works against you here."
                            if g["theta"] < 0 else "Time decay works in your favour here."))
        directional = "bullish" in st["desc"].lower() or "bearish" in st["desc"].lower()
        if not directional:
            lines.append("This is a volatility/range strategy — the mechanical trend direction "
                         "matters less here than whether price actually moves (or stays still) enough.")
        elif ctx["signal_direction"] is None:
            lines.append("No mechanical signal is currently active (score 0.0) — this strategy's "
                         "directional bet isn't backed by a triggered rule either way right now.")
        else:
            agree = (("bullish" in st["desc"].lower() and ctx["signal_direction"] == "LONG")
                    or ("bearish" in st["desc"].lower() and ctx["signal_direction"] == "SHORT"))
            lines.append(f"The mechanical read (**{ctx['signal_direction']}**, score {ctx['conviction_score']:.1f}) "
                         f"{'agrees with' if agree else 'sits against'} this strategy's stated bias.")
        if st.get("breakevens_vs_range"):
            lines.append(f"Break-even(s): {st['breakevens_vs_range']}.")
        lines.append("*Premiums are theoretical Black-Scholes values from realized volatility, "
                     "not live option-chain quotes — real premiums will differ.*")

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
        lines.append(f"Net direction **{ctx['signal_direction']}**, conviction score {ctx['conviction_score']:.1f}.")
    else:
        lines.append("No rules fired on the latest bar — no fresh setup here.")

    lines.append("\n## Bottom line")
    lines.append(f"{ctx['symbol']} is in a {ctx['trend'].lower()}-trend with {zone} momentum"
                 + (f" and {len(ctx['mechanical_signals'])} active signal(s)." if ctx["mechanical_signals"]
                    else " and no active setup — patience over action."))
    lines.append("\n*Rule-based summary (no AI model available). Educational tool — not investment advice.*")
    return "\n".join(lines)


def _providers() -> list[tuple[str, str, callable]]:
    """(source, model, fn) for each configured AI backend, best first. Anything not
    configured is simply absent, so `_run` degrades to the rule-based narrative."""
    p = []
    if ANTHROPIC_API_KEY:
        p.append(("claude", CLAUDE_MODEL, _claude))
    if OLLAMA_MODEL:
        p.append(("ollama", OLLAMA_MODEL, _ollama))
    return p


def _run(ctx: dict, system: str, task: str) -> dict:
    # `direction` is null when no rule fired — the plan's fallback LONG is not a view.
    out = {"symbol": ctx["symbol"], "close": ctx["close"], "direction": ctx["signal_direction"]}
    failed = []
    for source, model, call in _providers():
        try:
            return {**out, "source": source, "model": model, "analysis": call(ctx, system, task)}
        except Exception as e:
            log.warning("%s analysis failed for %s, trying next provider",
                        source, ctx["symbol"], exc_info=True)
            failed.append(f"{source} ({type(e).__name__})")
    res = {**out, "source": "rules", "analysis": _rule_based(ctx)}
    if failed:
        res["note"] = f"{', '.join(failed)} failed — showing rule-based analysis."
    return res


def analyze(symbol: str) -> dict:
    return _run(_context(symbol), SYSTEM, "stock")


def analyze_options(symbol: str, strategy_name: str, strategy_desc: str, legs: list[dict],
                    net_premium: float, max_profit: str, max_loss: str,
                    breakevens: list[float], days_to_expiry: int | None = None,
                    vol_pct: float | None = None, greeks: dict | None = None) -> dict:
    ctx = _context(symbol)
    i = ctx["indicators"]
    ctx["strategy"] = {"name": strategy_name, "desc": strategy_desc, "legs": legs,
                       "net_premium": net_premium, "max_profit": max_profit,
                       "max_loss": max_loss, "breakevens": breakevens,
                       "days_to_expiry": days_to_expiry,
                       "realized_vol_pct": vol_pct, "position_greeks": greeks,
                       # Pre-computed: the model kept getting this comparison backwards.
                       "breakevens_vs_range": _range_note(breakevens, i["low_20d"], i["high_20d"])}
    return _run(ctx, SYSTEM_OPTIONS, "options strategy")
