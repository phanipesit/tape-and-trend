"""Heatmap tiles: AI tagging, share normalisation, board assembly. No DB: q() is
monkeypatched and dispatches on which of the two queries board() is running."""
import pytest

from app.services import heatmap


# ---------------------------------------------------------------- is_ai

@pytest.mark.parametrize("sector", [
    "AI Software", "AI Infrastructure", "Cloud/AI Infra", "IT/AI Services",
    "Digital/AI Services", "AI/Design Engineering", "AI/Auto Software",
])
def test_ai_labels_are_tagged(sector):
    assert heatmap.is_ai(sector)


@pytest.mark.parametrize("sector", ["Semiconductors", "Technology"])
def test_ai_trade_sectors_are_tagged(sector):
    # The chipmakers and hyperscalers never say "AI" in their label but are the trade.
    assert heatmap.is_ai(sector)


@pytest.mark.parametrize("sector", ["Retail", "Airlines", "Consumer/Paints"])
def test_substring_lookalikes_are_not_tagged(sector):
    # Ret-ai-l, -Ai-rlines, P-ai-nts: the exact reason the match is tokenised.
    assert not heatmap.is_ai(sector)


@pytest.mark.parametrize("sector", ["Banking", "Pharmaceuticals", None, ""])
def test_unrelated_sectors_are_not_tagged(sector):
    assert not heatmap.is_ai(sector)


# ---------------------------------------------------------------- _shares

def test_shares_are_per_market_not_global():
    """The whole point: an INR value and a USD value never land in the same total."""
    rows = [
        {"market": "IN", "turnover": 300.0},
        {"market": "IN", "turnover": 100.0},
        {"market": "US", "turnover": 50.0},
    ]
    heatmap._shares(rows, "turnover")
    assert [r["turnover_share"] for r in rows] == [0.75, 0.25, 1.0]


def test_shares_handle_none_and_empty_totals():
    rows = [{"market": "IN", "mcap": None}, {"market": "IN", "mcap": None}]
    heatmap._shares(rows, "mcap")
    assert all(r["mcap_share"] == 0.0 for r in rows)


# ---------------------------------------------------------------- board

SYMS = [
    {"symbol": "NVDA", "name": "NVIDIA", "market": "US", "sector": "Semiconductors", "mcap": 400.0},
    {"symbol": "AAPL", "name": "Apple", "market": "US", "sector": "Technology", "mcap": 600.0},
    {"symbol": "TRENT", "name": "Trent", "market": "IN", "sector": "Retail", "mcap": 100.0},
    {"symbol": "GHOST", "name": "No candles", "market": "IN", "sector": "Banking", "mcap": 50.0},
]
BARS = [
    # symbol, d, c, v  — two consecutive sessions each, oldest first
    {"symbol": "AAPL", "d": "2026-07-30", "c": 100.0, "v": 10},
    {"symbol": "AAPL", "d": "2026-07-31", "c": 110.0, "v": 10},
    {"symbol": "NVDA", "d": "2026-07-30", "c": 200.0, "v": 10},
    {"symbol": "NVDA", "d": "2026-07-31", "c": 190.0, "v": 10},
    {"symbol": "TRENT", "d": "2026-07-30", "c": 50.0, "v": 4},
    {"symbol": "TRENT", "d": "2026-07-31", "c": 50.0, "v": 4},
]


@pytest.fixture
def wired(monkeypatch):
    def fake_q(sql, **kw):
        return BARS if "ohlcv" in sql else [
            s for s in SYMS if not kw.get("m") or s["market"] == kw["m"]]
    monkeypatch.setattr(heatmap, "q", fake_q)


def by_symbol(board):
    return {r["symbol"]: r for r in board["rows"]}


def test_board_computes_change_off_the_previous_bar(wired):
    r = by_symbol(heatmap.board())
    assert r["AAPL"]["pct"] == 10.0 and r["AAPL"]["change"] == 10.0
    assert r["NVDA"]["pct"] == -5.0 and r["NVDA"]["change"] == -10.0
    assert r["TRENT"]["pct"] == 0.0


def test_board_uses_the_latest_bar_for_turnover(wired):
    assert by_symbol(heatmap.board())["AAPL"]["turnover"] == 1100.0  # 110 x 10


def test_board_tags_ai_without_catching_retail(wired):
    r = by_symbol(heatmap.board())
    assert r["NVDA"]["ai"] and r["AAPL"]["ai"]
    assert not r["TRENT"]["ai"]
    assert heatmap.board()["ai_count"] == 2


def test_board_reports_symbols_with_no_cached_candles(wired):
    b = heatmap.board()
    assert b["missing"] == ["GHOST"]
    assert "GHOST" not in by_symbol(b)


def test_board_shares_are_scoped_per_market(wired):
    r = by_symbol(heatmap.board())
    # TRENT is the only Indian tile with candles, so it owns 100% of India's
    # turnover — it must not be diluted by the far larger US numbers.
    assert r["TRENT"]["turnover_share"] == 1.0
    assert r["AAPL"]["turnover_share"] + r["NVDA"]["turnover_share"] == pytest.approx(1.0)


def test_board_sorts_biggest_tile_first(wired):
    # TRENT, not AAPL: shares are per-market, so the only Indian tile owns all of
    # India's turnover and outranks AAPL's 55% of the US. That is the normalisation
    # working — an unfiltered board gives each market the same total canvas.
    assert [r["symbol"] for r in heatmap.board()["rows"]] == ["TRENT", "NVDA", "AAPL"]
    assert [r["symbol"] for r in heatmap.board("US")["rows"]] == ["NVDA", "AAPL"]


def test_board_groups_roll_up_by_sector_group(wired):
    groups = {g["group"]: g for g in heatmap.board()["groups"]}
    assert groups["Semiconductors"]["n"] == 1
    assert groups["IT & Software"]["avg_pct"] == 10.0
    # Sorted by the share of activity they represent, biggest first — NVDA's 1900
    # of turnover against AAPL's 1100.
    assert [g["group"] for g in heatmap.board("US")["groups"]] == \
        ["Semiconductors", "IT & Software"]


def test_board_market_filter_narrows_the_universe(wired):
    b = heatmap.board("US")
    assert {r["symbol"] for r in b["rows"]} == {"NVDA", "AAPL"}
    assert b["market"] == "US"


def test_board_reports_as_of_from_the_latest_bar(wired):
    assert heatmap.board()["as_of"] == "2026-07-31"


def test_board_on_empty_universe_is_not_an_error(monkeypatch):
    monkeypatch.setattr(heatmap, "q", lambda sql, **kw: [])
    assert heatmap.board() == {"rows": [], "groups": [], "as_of": None,
                               "market": None, "missing": []}
