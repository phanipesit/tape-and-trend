"""Yahoo ticker mapping. Pure string logic — no DB, no network."""
import pytest

from app.services.data import yf_symbol, BSE_OVERRIDE


def test_indian_equity_defaults_to_nse():
    assert yf_symbol("RELIANCE", "IN") == "RELIANCE.NS"


def test_bse_override_applies_to_daily_when_populated(monkeypatch):
    # The mechanism, exercised without pinning a specific symbol — BSE_OVERRIDE is
    # currently empty because Yahoo's .BO feed degraded (see the comment on it).
    monkeypatch.setattr("app.services.data.BSE_OVERRIDE", {"WONKY"})
    assert yf_symbol("WONKY", "IN") == "WONKY.BO"


def test_bse_override_never_applies_to_intraday(monkeypatch):
    # Yahoo serves no current intraday for .BO at all — a 5m request returns "possibly
    # delisted, no price data". Routing intraday through BSE doesn't error, it just
    # silently stops advancing, which is how a Friday bar was served as live.
    monkeypatch.setattr("app.services.data.BSE_OVERRIDE", {"WONKY"})
    assert yf_symbol("WONKY", "IN", intraday=True) == "WONKY.NS"


def test_hdfcbank_now_routes_to_nse():
    # Verified live 2026-08-03: .BO returns 2 bars over six months, .NS returns 125.
    assert yf_symbol("HDFCBANK", "IN") == "HDFCBANK.NS"


def test_intraday_flag_is_a_no_op_for_symbols_not_overridden():
    assert yf_symbol("TCS", "IN", intraday=True) == yf_symbol("TCS", "IN") == "TCS.NS"


@pytest.mark.parametrize("sym", ["^NSEI", "^NSEBANK", "^GSPC"])
def test_index_tickers_pass_through_unchanged(sym):
    assert yf_symbol(sym, "IN") == yf_symbol(sym, "IN", intraday=True) == sym


def test_us_symbols_pass_through_unchanged():
    assert yf_symbol("AAPL", "US") == yf_symbol("AAPL", "US", intraday=True) == "AAPL"


def test_global_symbols_pass_through_unchanged():
    # market='GLOBAL' must not get an Indian suffix — Yahoo wants ^FTSE as-is.
    assert yf_symbol("^FTSE", "GLOBAL") == "^FTSE"
    assert yf_symbol("000001.SS", "GLOBAL") == "000001.SS"
