"""Global board + trend synthesis. No DB, no network: market_context and get_candles
are both monkeypatched, which also asserts the read path never fetches (get_candles is
called with auto=False)."""
import pytest

from app.services import markets


def meta(symbol, name, cls, region):
    return {"symbol": symbol, "name": name, "asset_class": cls, "region": region,
            "market": "US"}


UNIVERSE = [
    meta("^NSEI", "Nifty 50", "index", "INDIA"),
    meta("^GSPC", "S&P 500", "index", "AMERICAS"),
    meta("^IXIC", "Nasdaq", "global", "AMERICAS"),
    meta("^FTSE", "FTSE 100", "global", "EUROPE"),
    meta("GC=F", "Gold", "metal", "METALS"),
    meta("SI=F", "Silver", "metal", "METALS"),
    meta("^VIX", "VIX", "macro", "MACRO"),
]


@pytest.fixture
def wire(monkeypatch, make_df):
    """Install a universe and a per-symbol close series."""
    def _wire(series: dict[str, list[float]], universe=UNIVERSE):
        monkeypatch.setattr(markets, "market_context", lambda *a, **k: universe)
        monkeypatch.setattr(markets, "get_candles",
                            lambda s, limit=260, auto=False: make_df(series[s]))
        monkeypatch.setattr(markets, "venue_for", lambda s: "NYSE")
        monkeypatch.setattr(markets, "venue_state", lambda v: {"state": "CLOSED"})
    return _wire


def rising(n=260, start=100.0, step=0.5):
    return [start + i * step for i in range(n)]


def falling(n=260, start=300.0, step=0.5):
    return [start - i * step for i in range(n)]


def flatish(n=260, level=100.0):
    return [level + (0.5 if i % 2 else -0.5) for i in range(n)]


# ---- regime -----------------------------------------------------------------

def test_all_indices_uptrending_reads_risk_on(wire):
    wire({s: rising() for s in ("^NSEI", "^GSPC", "^IXIC", "^FTSE")}
         | {"GC=F": rising(), "SI=F": rising(), "^VIX": flatish(level=14)})
    t = markets.board()["trend"]
    assert t["regime"] == "RISK-ON"
    assert t["above_sma200"] == t["scored"] == 4
    assert "above their 200-day" in t["verdict"]


def test_all_indices_downtrending_reads_risk_off(wire):
    wire({s: falling() for s in ("^NSEI", "^GSPC", "^IXIC", "^FTSE")}
         | {"GC=F": rising(), "SI=F": rising(), "^VIX": flatish(level=35)})
    t = markets.board()["trend"]
    assert t["regime"] == "RISK-OFF"
    assert t["above_sma200"] == 0


def test_split_market_reads_mixed(wire):
    wire({"^NSEI": rising(), "^GSPC": rising(), "^IXIC": falling(), "^FTSE": falling(),
          "GC=F": rising(), "SI=F": rising(), "^VIX": flatish(level=18)})
    t = markets.board()["trend"]
    assert t["regime"] == "MIXED"
    assert t["above_sma200"] == 2 and t["scored"] == 4


# ---- volatility -------------------------------------------------------------

@pytest.mark.parametrize("vix,label", [(12, "calm"), (15.99, "calm"),
                                       (22, "elevated"), (34, "stressed")])
def test_vix_bucketing(wire, vix, label):
    """15.99 must read calm — an earlier 15/25 split called a 16 handle 'elevated',
    which coloured the whole dashboard's tone wrongly."""
    wire({s: rising() for s in ("^NSEI", "^GSPC", "^IXIC", "^FTSE")}
         | {"GC=F": rising(), "SI=F": rising(), "^VIX": flatish(level=vix)})
    t = markets.board()["trend"]
    assert t["volatility"] == label
    assert t["vix"] == pytest.approx(vix, abs=1.0)


# ---- metals -----------------------------------------------------------------

def test_gold_silver_ratio(wire):
    wire({s: rising() for s in ("^NSEI", "^GSPC", "^IXIC", "^FTSE")}
         | {"GC=F": [2000.0] * 260, "SI=F": [25.0] * 260, "^VIX": flatish(level=15)})
    assert markets.board()["trend"]["gold_silver_ratio"] == 80.0


def test_ratio_is_none_without_both_legs(wire):
    universe = [m for m in UNIVERSE if m["symbol"] != "SI=F"]
    wire({s: rising() for s in ("^NSEI", "^GSPC", "^IXIC", "^FTSE")}
         | {"GC=F": rising(), "^VIX": flatish(level=15)}, universe=universe)
    assert markets.board()["trend"]["gold_silver_ratio"] is None


# ---- shape ------------------------------------------------------------------

def test_regions_grouped_and_ordered_home_market_first(wire):
    wire({s: rising() for s in ("^NSEI", "^GSPC", "^IXIC", "^FTSE")}
         | {"GC=F": rising(), "SI=F": rising(), "^VIX": flatish(level=15)})
    b = markets.board()
    assert [g["region"] for g in b["regions"]] == ["INDIA", "AMERICAS", "EUROPE"]
    assert [r["symbol"] for r in b["regions"][1]["rows"]] == ["^GSPC", "^IXIC"]


def test_metals_and_macro_are_not_counted_as_indices(wire):
    wire({s: rising() for s in ("^NSEI", "^GSPC", "^IXIC", "^FTSE")}
         | {"GC=F": rising(), "SI=F": rising(), "^VIX": flatish(level=15)})
    b = markets.board()
    assert b["trend"]["indices_total"] == 4
    assert {r["symbol"] for r in b["metals"]} == {"GC=F", "SI=F"}
    assert {r["symbol"] for r in b["macro"]} == {"^VIX"}


def test_best_and_worst_come_from_indices_only(wire):
    wire({"^NSEI": [100.0, 110.0] * 130, "^GSPC": rising(), "^IXIC": rising(),
          "^FTSE": [100.0, 90.0] * 130,
          "GC=F": rising(), "SI=F": rising(), "^VIX": flatish(level=15)})
    t = markets.board()["trend"]
    assert t["best"]["pct"] >= t["worst"]["pct"]
    assert t["best"]["symbol"] in {"^NSEI", "^GSPC", "^IXIC", "^FTSE"}


def test_symbol_with_no_cached_candles_is_reported_not_crashed(wire, monkeypatch, make_df):
    series = {s: rising() for s in ("^NSEI", "^GSPC", "^IXIC")} | {
        "GC=F": rising(), "SI=F": rising(), "^VIX": flatish(level=15)}
    monkeypatch.setattr(markets, "market_context", lambda *a, **k: UNIVERSE)
    monkeypatch.setattr(markets, "venue_for", lambda s: None)
    monkeypatch.setattr(markets, "get_candles",
                        lambda s, limit=260, auto=False:
                        make_df(series[s]) if s in series else make_df([]))
    b = markets.board()
    assert b["missing"] == ["^FTSE"]
    assert b["trend"]["indices_total"] == 3      # still produces a read


def test_read_path_never_triggers_a_network_refresh(wire, monkeypatch, make_df):
    """18 sequential yfinance fetches on a dashboard render is exactly the multi-minute
    stall routers/screener.py warns about — the board must read cache only."""
    seen = {}
    monkeypatch.setattr(markets, "market_context", lambda *a, **k: UNIVERSE)
    monkeypatch.setattr(markets, "venue_for", lambda s: None)

    def spy(s, limit=260, auto=False):
        seen[s] = auto
        return make_df(rising())
    monkeypatch.setattr(markets, "get_candles", spy)
    markets.board()
    assert seen and all(auto is False for auto in seen.values())
