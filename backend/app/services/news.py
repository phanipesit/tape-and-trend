"""News: yfinance per-ticker news (keyless) + optional NewsAPI top business headlines."""
import asyncio
import logging
from datetime import datetime, timezone

import httpx
import yfinance as yf
from .data import yf_symbol, get_symbol, YF_LOCK
from ..db import q
from ..config import NEWSAPI_KEY

log = logging.getLogger(__name__)

def _iso(ts) -> str | None:
    """Normalise a publish time to one UTC ISO-8601 string.

    Upstream hands us three shapes — yfinance's legacy `providerPublishTime`
    (epoch seconds), its newer `pubDate` (ISO with a `Z`), and NewsAPI's
    `publishedAt` (ISO with an offset). A blended wire can only be sorted if
    they agree, and normalising to UTC also makes the strings sort
    lexicographically, which is what `wire()` relies on.
    """
    if ts is None or ts == "":
        return None
    if isinstance(ts, (int, float)):
        return datetime.fromtimestamp(ts, tz=timezone.utc).isoformat()
    try:
        dt = datetime.fromisoformat(str(ts).replace("Z", "+00:00"))
    except ValueError:
        return None
    # A naive timestamp is assumed UTC — astimezone() would otherwise read it as
    # the server's local time and shift every headline by the machine's offset.
    dt = dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt
    return dt.astimezone(timezone.utc).isoformat()

def ticker_news(symbol: str, limit: int = 8) -> list[dict]:
    meta = get_symbol(symbol)
    try:
        with YF_LOCK:
            items = yf.Ticker(yf_symbol(symbol, meta["market"])).news or []
    except Exception:
        log.warning("news fetch failed for %s", symbol, exc_info=True)
        items = []
    out = []
    for n in items[:limit]:
        content = n.get("content", n)
        out.append({
            "title": content.get("title"),
            "publisher": (content.get("provider") or {}).get("displayName")
                          if isinstance(content.get("provider"), dict) else n.get("publisher"),
            "link": (content.get("canonicalUrl") or {}).get("url")
                     if isinstance(content.get("canonicalUrl"), dict) else n.get("link"),
            "published": _iso(content.get("pubDate") or n.get("providerPublishTime")),
            "symbol": symbol,
        })
    return [x for x in out if x["title"]]

async def market_headlines(country: str = "in", limit: int = 10) -> list[dict]:
    if not NEWSAPI_KEY:
        return []
    url = ("https://newsapi.org/v2/top-headlines"
           f"?country={country}&category=business&pageSize={limit}&apiKey={NEWSAPI_KEY}")
    async with httpx.AsyncClient(timeout=10) as cl:
        r = await cl.get(url)
        arts = r.json().get("articles", [])
    return [{"title": a["title"], "publisher": (a.get("source") or {}).get("name"),
             "link": a.get("url"), "published": _iso(a.get("publishedAt")),
             "symbol": None} for a in arts]

def order(items: list[dict]) -> list[dict]:
    """Dedupe by title, newest first. Undated stories sort last rather than
    blowing up the comparison against a string."""
    seen, out = set(), []
    for n in items:
        key = (n.get("title") or "").strip().lower()
        if not key or key in seen:
            continue
        seen.add(key)
        out.append(n)
    out.sort(key=lambda n: (n.get("published") is not None, n.get("published") or ""),
             reverse=True)
    return out

async def wire(limit: int = 30) -> list[dict]:
    """Blend NewsAPI headlines (if key set) with watchlist ticker news."""
    # ticker_news (yfinance, behind YF_LOCK) and q() are blocking. Called straight
    # from an async endpoint they'd run *on* the event loop and stall every other
    # request plus the alert loop for the length of ~4 network calls — hence
    # to_thread.
    in_, us = await asyncio.gather(market_headlines("in"), market_headlines("us"))
    items = in_ + us
    rows = await asyncio.to_thread(q, "SELECT symbol FROM watchlist LIMIT 4")
    for batch in await asyncio.gather(
            *(asyncio.to_thread(ticker_news, r["symbol"], 3) for r in rows)):
        items += batch
    return order(items)[:limit]
