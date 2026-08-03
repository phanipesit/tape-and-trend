"""Yahoo ticker mapping. Pure string logic — no DB, no network."""
import pytest

from app.services.data import yf_symbol, BSE_OVERRIDE


def test_indian_equity_defaults_to_nse():
    assert yf_symbol("RELIANCE", "IN") == "RELIANCE.NS"


def test_bse_override_applies_to_daily():
    # HDFCBANK's Yahoo NSE *daily* data is known-bad; that is what BSE_OVERRIDE is for.
    assert "HDFCBANK" in BSE_OVERRIDE
    assert yf_symbol("HDFCBANK", "IN") == "HDFCBANK.BO"


def test_bse_override_does_not_apply_to_intraday():
    # Yahoo serves no current intraday for .BO at all — a 5m request returns "possibly
    # delisted, no price data". Routing intraday through BSE doesn't error, it just
    # silently stops advancing, which is how a Friday bar was served as live.
    assert yf_symbol("HDFCBANK", "IN", intraday=True) == "HDFCBANK.NS"


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
