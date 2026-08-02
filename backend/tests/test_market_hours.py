"""Session-clock tests. `now` is injected everywhere, so these are deterministic and
do not depend on when the suite runs. Dates are in August 2026 — US/UK summer time is
in effect, which is deliberate: the IST offsets differ from winter and that is the
point of computing them from real datetimes instead of hardcoding.

2026-08-03 is a Monday; 08-01 Saturday, 08-02 Sunday, 08-07 Friday.
"""
from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from app.services import market_hours as mh

IST = ZoneInfo("Asia/Kolkata")
ET = ZoneInfo("America/New_York")
JST = ZoneInfo("Asia/Tokyo")


def at(tz, y, m, d, hh, mm=0):
    return datetime(y, m, d, hh, mm, tzinfo=tz)


# ---- basic open / closed ----------------------------------------------------

def test_nse_open_during_session():
    s = mh.venue_state("NSE", at(IST, 2026, 8, 3, 10, 0))
    assert s["state"] == "OPEN"
    assert s["closes_in_seconds"] == pytest.approx((5 * 3600 + 30 * 60), abs=60)


@pytest.mark.parametrize("hh,mm", [(9, 0), (15, 45), (18, 0)])
def test_nse_closed_outside_session(hh, mm):
    assert mh.venue_state("NSE", at(IST, 2026, 8, 3, hh, mm))["state"] == "CLOSED"


def test_nse_boundaries_are_half_open():
    """Open at exactly 09:15, shut at exactly 15:30 — no double-counting the close."""
    assert mh.venue_state("NSE", at(IST, 2026, 8, 3, 9, 15))["state"] == "OPEN"
    assert mh.venue_state("NSE", at(IST, 2026, 8, 3, 15, 30))["state"] == "CLOSED"


def test_weekend_reads_weekend_not_closed():
    for day in (1, 2):   # Sat, Sun
        assert mh.venue_state("NSE", at(IST, 2026, 8, day, 11, 0))["state"] == "WEEKEND"


def test_next_open_skips_the_weekend():
    s = mh.venue_state("NSE", at(IST, 2026, 8, 1, 11, 0))     # Saturday
    assert s["opens_at_home"] == "Mon 09:15"
    assert s["opens_in_seconds"] == pytest.approx(2 * 86400 - 6300, abs=120)


# ---- lunch breaks -----------------------------------------------------------

def test_tse_lunch_break_is_not_closed():
    assert mh.venue_state("TSE", at(JST, 2026, 8, 3, 12, 0))["state"] == "LUNCH"
    assert mh.venue_state("TSE", at(JST, 2026, 8, 3, 10, 0))["state"] == "OPEN"
    assert mh.venue_state("TSE", at(JST, 2026, 8, 3, 13, 0))["state"] == "OPEN"


def test_single_segment_venue_never_reports_lunch():
    """NSE has one segment, so the lunch branch must not fire for it at any hour."""
    states = {mh.venue_state("NSE", at(IST, 2026, 8, 3, h))["state"] for h in range(24)}
    assert "LUNCH" not in states


# ---- futures: the session that starts Sunday and wraps midnight -------------

def test_comex_opens_sunday_evening():
    """Metals reopen Sun 18:00 ET. A weekday-only model put this a full day late."""
    assert mh.venue_state("COMEX", at(ET, 2026, 8, 2, 18, 30))["state"] == "OPEN"
    assert mh.venue_state("COMEX", at(ET, 2026, 8, 2, 17, 30))["state"] == "CLOSED"


def test_comex_session_wraps_past_midnight():
    """Monday morning is inside the session that began Sunday evening."""
    assert mh.venue_state("COMEX", at(ET, 2026, 8, 3, 10, 0))["state"] == "OPEN"
    assert mh.venue_state("COMEX", at(ET, 2026, 8, 3, 17, 30))["state"] == "CLOSED"  # settlement gap


def test_comex_saturday_is_weekend_but_friday_night_is_merely_closed():
    assert mh.venue_state("COMEX", at(ET, 2026, 8, 1, 12, 0))["state"] == "WEEKEND"
    assert mh.venue_state("COMEX", at(ET, 2026, 8, 7, 20, 0))["state"] == "CLOSED"


def test_comex_next_open_from_saturday_is_sunday_evening():
    s = mh.venue_state("COMEX", at(ET, 2026, 8, 1, 12, 0))
    assert s["opens_at_home"] == "Mon 03:30"   # Sun 18:00 ET == Mon 03:30 IST


# ---- home-timezone rendering ------------------------------------------------

def test_nyse_session_rendered_in_ist():
    s = mh.venue_state("NYSE", at(ET, 2026, 8, 3, 10, 0))
    assert s["session"] == "09:30-16:00"
    assert s["session_home"] == "19:00-01:30"     # EDT -> IST
    assert s["home_tz"] == "Asia/Kolkata"


def test_home_rendering_follows_dst():
    """The IST offset of the US open moves by an hour between EDT and EST. Computing
    from concrete datetimes tracks it; a hardcoded offset would not."""
    summer = mh.venue_state("NYSE", at(ET, 2026, 8, 3, 10, 0))["session_home"]
    winter = mh.venue_state("NYSE", at(ET, 2026, 1, 5, 10, 0))["session_home"]
    assert summer == "19:00-01:30"
    assert winter == "20:00-02:30"
    assert summer != winter


def test_lunch_venue_renders_both_segments_in_home_tz():
    s = mh.venue_state("TSE", at(JST, 2026, 8, 3, 10, 0))
    assert s["session_home"] == "05:30-08:00 / 09:00-12:00"


def test_session_home_still_shown_on_a_closed_day():
    """On a weekend the card should still display normal hours, not an empty string."""
    assert mh.venue_state("NSE", at(IST, 2026, 8, 2, 11, 0))["session_home"] == "09:15-15:30"


# ---- contract ---------------------------------------------------------------

def test_every_venue_declares_holidays_not_applied():
    """No holiday calendar is bundled. Callers must be able to see that."""
    for v in mh.all_venues(at(IST, 2026, 8, 3, 10, 0)):
        assert v["holidays_applied"] is False


def test_all_venues_covers_every_mapped_symbol():
    assert set(mh.SYMBOL_VENUE.values()) <= set(mh.VENUES)


def test_open_venue_has_no_next_open_and_vice_versa():
    for v in mh.all_venues(at(IST, 2026, 8, 3, 10, 0)):
        if v["state"] == "OPEN":
            assert v["closes_in_seconds"] is not None and v["opens_in_seconds"] is None
        else:
            assert v["opens_in_seconds"] is not None and v["opens_in_seconds"] > 0
