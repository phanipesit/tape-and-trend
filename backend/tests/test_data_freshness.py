"""The candle staleness gate. No network: q() and the venue clock are monkeypatched.

The bug being pinned: today's daily bar exists from the moment a session opens, so a
"do we have today's bar?" test called it fresh and nothing refetched for the rest of the
day — including the dashboard's refresh button.
"""
from datetime import date, datetime, timedelta, timezone

import pytest

from app.services import data


@pytest.fixture
def gate(monkeypatch):
    """Cache holds today's bar. Returns a setter for venue state and last-fetch time."""
    monkeypatch.setattr(data, "q", lambda *a, **k: [{"last": date.today()}])
    monkeypatch.setattr(data, "_venue_of", lambda s: "NSE")
    state = {"open": True}
    monkeypatch.setattr(data, "venue_state", lambda v: {"state": "OPEN" if state["open"] else "CLOSED"})

    def _set(open_now=True, fetched_minutes_ago=None):
        state["open"] = open_now
        data._last_fetch.pop("X", None)
        if fetched_minutes_ago is not None:
            data._last_fetch["X"] = (datetime.now(timezone.utc)
                                     - timedelta(minutes=fetched_minutes_ago))
    return _set


def test_todays_bar_is_not_fresh_during_an_open_session(gate):
    gate(open_now=True, fetched_minutes_ago=None)
    assert data._cache_fresh("X", live=True) is False


def test_a_recent_fetch_is_fresh_during_an_open_session(gate):
    gate(open_now=True, fetched_minutes_ago=2)
    assert data._cache_fresh("X", live=True) is True


def test_an_old_fetch_goes_stale_during_an_open_session(gate):
    gate(open_now=True, fetched_minutes_ago=60)
    assert data._cache_fresh("X", live=True) is False


def test_todays_bar_is_fresh_once_the_venue_shuts(gate):
    # After the close the bar is final — the old rule is correct and must survive.
    gate(open_now=False, fetched_minutes_ago=None)
    assert data._cache_fresh("X", live=True) is True


def test_live_is_opt_in(gate):
    """Without live=True the session must not matter — this is what stops the
    ~124-symbol screener sweep turning into 124 live fetches."""
    gate(open_now=True, fetched_minutes_ago=None)
    assert data._cache_fresh("X", live=False) is True


def test_no_cached_bars_is_never_fresh(monkeypatch):
    monkeypatch.setattr(data, "q", lambda *a, **k: [{"last": None}])
    assert data._cache_fresh("X") is False
    assert data._cache_fresh("X", live=True) is False


def test_symbol_with_no_venue_falls_back_to_the_old_rule(monkeypatch):
    monkeypatch.setattr(data, "q", lambda *a, **k: [{"last": date.today()}])
    monkeypatch.setattr(data, "_venue_of", lambda s: None)
    assert data.session_open("X") is False
    assert data._cache_fresh("X", live=True) is True


def test_lunch_break_counts_as_shut(monkeypatch):
    # TSE/HKEX/SSE break mid-session; prices don't move, so there's nothing to refetch.
    monkeypatch.setattr(data, "_venue_of", lambda s: "TSE")
    monkeypatch.setattr(data, "venue_state", lambda v: {"state": "LUNCH"})
    assert data.session_open("X") is False


def test_venue_clock_failure_does_not_break_reads(monkeypatch):
    def boom(v):
        raise RuntimeError("clock exploded")
    monkeypatch.setattr(data, "_venue_of", lambda s: "NSE")
    monkeypatch.setattr(data, "venue_state", boom)
    assert data.session_open("X") is False
