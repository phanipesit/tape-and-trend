"""News: yfinance per-ticker news (keyless) + optional NewsAPI top business headlines."""
import httpx
import yfinance as yf
from .data import yf_symbol, get_symbol
from ..config import NEWSAPI_KEY

def ticker_news(symbol: str, limit: int = 8) -> list[dict]:
    meta = get_symbol(symbol)
    try:
        items = yf.Ticker(yf_symbol(symbol, meta["market"])).news or []
    except Exception:
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
            "published": content.get("pubDate") or n.get("providerPublishTime"),
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
             "link": a.get("url"), "published": a.get("publishedAt")} for a in arts]
