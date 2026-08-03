"""NSE chain symbol targeting, blank handling and strike/expiry selection.
No DB, no network: q() and _fetch are monkeypatched."""
from datetime import date, datetime, timedelta, timezone

import pytest

from app.services import nse_chain


# ---------------------------------------------------------------- targeting

def test_index_symbols_map_to_nse_names():
    assert nse_chain.nse_target("^NSEI") == ("NIFTY", "Indices")
    assert nse_chain.nse_target("^NSEBANK") == ("BANKNIFTY", "Indices")


def test_foreign_index_has_no_chain():
    # ^GSPC is on the dashboard board; NSE obviously does not quote options on it.
    assert nse_chain.nse_target("^GSPC") is None


def test_us_equity_has_no_chain(monkeypatch):
    monkeypatch.setattr("app.services.data.get_symbol", lambda s: {"market": "US"})
    assert nse_chain.nse_target("AAPL") is None


def test_indian_equity_is_an_equities_target(monkeypatch):
    monkeypatch.setattr("app.services.data.get_symbol", lambda s: {"market": "IN"})
    assert nse_chain.nse_target("RELIANCE") == ("RELIANCE", "Equities")


def test_unknown_symbol_has_no_chain(monkeypatch):
    def boom(s):
        raise ValueError("unknown symbol")
    monkeypatch.setattr("app.services.data.get_symbol", boom)
    assert nse_chain.nse_target("NOPE") is None


# ---------------------------------------------------------------- blanks

@pytest.mark.parametrize("blank", [None, 0, 0.0, "-", ""])
def test_unquoted_values_become_none_not_zero(blank):
    # NSE sends 0 for strikes nobody has traded. Zero is a blank, not a measurement —
    # passing it to black_scholes() collapses the option to intrinsic value.
    assert nse_chain._num(blank) is None


def test_real_values_survive():
    assert nse_chain._num(12.76) == 12.76
    assert nse_chain._num("18.5") == 18.5


def test_expiry_parsing():
    assert nse_chain._parse_expiry("04-Aug-2026") == date(2026, 8, 4)
    assert nse_chain._parse_expiry("garbage") is None
    assert nse_chain._parse_expiry(None) is None


# ---------------------------------------------------------------- implied_vol

NEAR = date.today() + timedelta(days=2)
FAR = date.today() + timedelta(days=40)


def row(expiry, strike, opt_type, iv, ltp=1.0):
    return {"symbol": "^NSEI", "expiry": expiry, "strike": strike, "opt_type": opt_type,
            "iv": iv, "ltp": ltp, "oi": 10, "volume": 5, "spot": 24550.0,
            "fetched_at": datetime.now(timezone.utc)}


@pytest.fixture
def chain(monkeypatch):
    rows = [
        row(NEAR, 24500, "CE", 12.5), row(NEAR, 24600, "CE", 13.0),
        row(NEAR, 24500, "PE", 14.0), row(NEAR, 25500, "CE", 29.27),
        row(FAR, 24500, "CE", 18.0),
        row(NEAR, 23000, "CE", None),        # unquoted — must be skipped, not used as 0
    ]
    monkeypatch.setattr(nse_chain, "get_chain", lambda s, expiry=None, auto=True, want=None: rows)
    return rows


def test_picks_the_nearest_strike(chain):
    iv = nse_chain.implied_vol("^NSEI", 24510, "call", days=2)
    assert iv["strike_used"] == 24500 and iv["iv_pct"] == 12.5


def test_iv_is_returned_as_a_decimal_not_a_percent(chain):
    # NSE publishes 12.5 meaning 12.5%; black_scholes wants 0.125.
    assert nse_chain.implied_vol("^NSEI", 24500, "call", days=2)["vol"] == 0.125


def test_calls_and_puts_are_separate(chain):
    # The whole point of per-leg IV: at one strike the two sides differ.
    assert nse_chain.implied_vol("^NSEI", 24500, "call", days=2)["iv_pct"] == 12.5
    assert nse_chain.implied_vol("^NSEI", 24500, "put", days=2)["iv_pct"] == 14.0


def test_wings_keep_their_own_vol(chain):
    # A skew this size is exactly what a single realized number cannot express.
    assert nse_chain.implied_vol("^NSEI", 25500, "call", days=2)["iv_pct"] == 29.27


def test_expiry_nearest_the_requested_horizon_wins(chain):
    assert nse_chain.implied_vol("^NSEI", 24500, "call", days=2)["expiry"] == str(NEAR)
    assert nse_chain.implied_vol("^NSEI", 24500, "call", days=40)["expiry"] == str(FAR)


def test_unquoted_strikes_are_not_selected(chain):
    # 23000 CE has iv=None; asking for it must fall to a real quote, never return 0 vol.
    iv = nse_chain.implied_vol("^NSEI", 23000, "call", days=2)
    assert iv is not None and iv["strike_used"] != 23000 and iv["vol"] > 0


def test_empty_chain_returns_none_so_callers_fall_back(monkeypatch):
    monkeypatch.setattr(nse_chain, "get_chain", lambda s, expiry=None, auto=True, want=None: [])
    assert nse_chain.implied_vol("^NSEI", 24500, "call") is None


def test_get_chain_never_raises_when_the_fetch_fails(monkeypatch):
    """An NSE outage must cost accuracy, not availability."""
    monkeypatch.setattr(nse_chain, "_cache_fresh", lambda s, want=None: False)
    def boom(*a, **k):
        raise RuntimeError("NSE down")
    monkeypatch.setattr(nse_chain, "refresh_chain", boom)
    monkeypatch.setattr(nse_chain, "q", lambda *a, **k: [])
    assert nse_chain.get_chain("^NSEI") == []


# ---------------------------------------------------------------- expiry targeting

def test_cache_is_stale_when_no_expiry_is_near_the_horizon(monkeypatch):
    """The bug: only the front expiry was ever cached, so a 90-day strategy priced off
    the 1-day contract forever. A cached chain far from the horizon is not usable."""
    monkeypatch.setattr(nse_chain, "q", lambda *a, **k: [
        {"expiry": date.today() + timedelta(days=1), "f": datetime.now(timezone.utc)}])
    assert nse_chain._cache_fresh("^NSEI", want=date.today() + timedelta(days=2)) is True
    assert nse_chain._cache_fresh("^NSEI", want=date.today() + timedelta(days=90)) is False


def test_cache_without_a_horizon_only_checks_age(monkeypatch):
    monkeypatch.setattr(nse_chain, "q", lambda *a, **k: [
        {"expiry": date.today() + timedelta(days=1), "f": datetime.now(timezone.utc)}])
    assert nse_chain._cache_fresh("^NSEI") is True


def test_stale_timestamp_beats_a_well_matched_expiry(monkeypatch):
    old = datetime.now(timezone.utc) - timedelta(hours=5)
    monkeypatch.setattr(nse_chain, "q", lambda *a, **k: [
        {"expiry": date.today() + timedelta(days=30), "f": old}])
    assert nse_chain._cache_fresh("^NSEI", want=date.today() + timedelta(days=30)) is False


def test_implied_vol_asks_for_the_horizon_it_needs(monkeypatch):
    """implied_vol must pass the target date down so the right contract gets fetched."""
    seen = {}
    def fake_get_chain(sym, expiry=None, auto=True, want=None):
        seen["want"] = want
        return []
    monkeypatch.setattr(nse_chain, "get_chain", fake_get_chain)
    nse_chain.implied_vol("^NSEI", 24500, "call", days=90)
    assert seen["want"] == date.today() + timedelta(days=90)
