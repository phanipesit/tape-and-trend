"""Publish-time normalisation and wire ordering. No DB, no network: q() and the
two fetchers are monkeypatched."""
import asyncio

import pytest

from app.services import news


# ---------------------------------------------------------------- _iso

def test_iso_epoch_seconds():
    # yfinance's legacy providerPublishTime
    assert news._iso(1_700_000_000) == "2023-11-14T22:13:20+00:00"


def test_iso_zulu_string():
    assert news._iso("2026-08-02T09:30:00Z") == "2026-08-02T09:30:00+00:00"


def test_iso_offset_string_converts_to_utc():
    # NewsAPI can send a non-UTC offset; the wire sorts lexicographically, so it
    # has to land on +00:00 or ordering silently breaks.
    assert news._iso("2026-08-02T15:00:00+05:30") == "2026-08-02T09:30:00+00:00"


def test_iso_naive_string_assumed_utc():
    # Not read as the server's local time — that would shift every headline by
    # whatever offset the machine happens to run in.
    assert news._iso("2026-08-02T09:30:00") == "2026-08-02T09:30:00+00:00"


@pytest.mark.parametrize("bad", [None, "", "not a date"])
def test_iso_unparseable_is_none(bad):
    assert news._iso(bad) is None


# ---------------------------------------------------------------- order

def item(title, published=None, symbol=None):
    return {"title": title, "published": published, "symbol": symbol,
            "publisher": "Wire", "link": "http://x"}


def test_order_is_newest_first():
    out = news.order([
        item("old", "2026-08-01T09:00:00+00:00"),
        item("new", "2026-08-02T09:00:00+00:00"),
        item("mid", "2026-08-01T18:00:00+00:00"),
    ])
    assert [n["title"] for n in out] == ["new", "mid", "old"]


def test_order_puts_undated_last():
    out = news.order([item("undated"), item("dated", "2026-08-01T09:00:00+00:00")])
    assert [n["title"] for n in out] == ["dated", "undated"]


def test_order_dedupes_by_title_case_insensitively():
    # The same story reaching us from a ticker feed and a headline feed.
    out = news.order([
        item("Reliance beats estimates", "2026-08-02T09:00:00+00:00", "RELIANCE"),
        item("  reliance beats estimates ", "2026-08-02T08:00:00+00:00"),
    ])
    assert len(out) == 1
    assert out[0]["symbol"] == "RELIANCE"  # first occurrence wins


def test_order_drops_titleless_items():
    assert news.order([item(""), item(None), item("real", "2026-08-02T09:00:00+00:00")]) \
        == [item("real", "2026-08-02T09:00:00+00:00")]


# ---------------------------------------------------------------- wire

@pytest.fixture
def wired(monkeypatch):
    """Two watchlist symbols, one headline feed, all deterministic."""
    monkeypatch.setattr(news, "q", lambda *a, **k: [{"symbol": "TCS"}, {"symbol": "AAPL"}])

    async def headlines(country="in", limit=10):
        return [item(f"{country} macro headline", "2026-08-02T12:00:00+00:00")] if country == "in" else []
    monkeypatch.setattr(news, "market_headlines", headlines)

    stories = {
        "TCS": [item("TCS wins deal", "2026-08-02T06:00:00+00:00", "TCS")],
        "AAPL": [item("Apple ships thing", "2026-08-02T18:00:00+00:00", "AAPL")],
    }
    monkeypatch.setattr(news, "ticker_news", lambda s, limit=8: stories[s])


def test_wire_blends_and_sorts(wired):
    out = asyncio.run(news.wire())
    assert [n["title"] for n in out] == [
        "Apple ships thing", "in macro headline", "TCS wins deal"]


def test_wire_respects_limit(wired):
    assert len(asyncio.run(news.wire(limit=2))) == 2
