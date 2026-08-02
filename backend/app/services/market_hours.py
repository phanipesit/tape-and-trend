"""Venue session state — is a market open right now, and when does it next change.

Pure functions over the IANA timezone database (zoneinfo, stdlib): no DB, no network,
no data feed. Kept separate from markets.py for that reason — it is fully deterministic
and testable by injecting `now`.

DELIBERATE LIMITATION: no holiday calendar. NSE alone closes ~15 days a year on dates
that move with the lunar calendar, and there is no bundled source for them. So a venue
that is shut for Diwali reads OPEN here. Every response carries holidays_applied=false
and callers must surface it — silently implying a holiday-aware clock would be worse
than not having one, because it would be trusted.
"""
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from ..config import HOME_TZ

# Regular cash sessions in venue-local time. Multiple segments = a lunch break
# (TSE/HKEX/SSE); the gap between segments reports as LUNCH, not CLOSED.
@dataclass(frozen=True)
class Venue:
    code: str
    name: str
    tz: str
    segments: tuple[tuple[time, time], ...]
    # Weekdays (Mon=0) on which a session *starts*. Futures start theirs on Sunday.
    days: tuple[int, ...] = (0, 1, 2, 3, 4)
    note: str = ""


VENUES: dict[str, Venue] = {
    "NSE":   Venue("NSE",   "India · NSE",     "Asia/Kolkata",
                   ((time(9, 15), time(15, 30)),)),
    "NYSE":  Venue("NYSE",  "US · NYSE",       "America/New_York",
                   ((time(9, 30), time(16, 0)),)),
    "LSE":   Venue("LSE",   "UK · LSE",        "Europe/London",
                   ((time(8, 0), time(16, 30)),)),
    "TSE":   Venue("TSE",   "Japan · TSE",     "Asia/Tokyo",
                   ((time(9, 0), time(11, 30)), (time(12, 30), time(15, 30)))),
    "HKEX":  Venue("HKEX",  "Hong Kong · HKEX", "Asia/Hong_Kong",
                   ((time(9, 30), time(12, 0)), (time(13, 0), time(16, 0)))),
    "SSE":   Venue("SSE",   "China · SSE",     "Asia/Shanghai",
                   ((time(9, 30), time(11, 30)), (time(13, 0), time(15, 0)))),
    # COMEX/NYMEX metals and energy: a session opens 18:00 ET and runs to 17:00 ET the
    # NEXT day, Sunday through Thursday — so the week opens Sunday evening, not Monday
    # morning, and the 17:00-18:00 gap between consecutive sessions is the daily
    # settlement break. Modelling this as weekday-only put the Sunday reopen a full day
    # late on the dashboard.
    "COMEX": Venue("COMEX", "Metals · COMEX",  "America/New_York",
                   ((time(18, 0), time(17, 0)),), days=(6, 0, 1, 2, 3),
                   note="near-24h futures session, Sun 18:00 - Fri 17:00 ET"),
}

# Which venue governs each symbol on the dashboard board.
SYMBOL_VENUE: dict[str, str] = {
    "^NSEI": "NSE", "^BSESN": "NSE", "^NSEBANK": "NSE",
    "^GSPC": "NYSE", "^IXIC": "NYSE", "^DJI": "NYSE", "^VIX": "NYSE",
    "^FTSE": "LSE", "^STOXX50E": "LSE", "^GDAXI": "LSE",
    "^N225": "TSE", "^HSI": "HKEX", "000001.SS": "SSE",
    "GC=F": "COMEX", "SI=F": "COMEX", "PL=F": "COMEX", "PA=F": "COMEX",
    "CL=F": "COMEX", "DX-Y.NYB": "COMEX",
}

def _segments_on(v: Venue, d: date) -> list[tuple[datetime, datetime]]:
    """Concrete open/close datetimes for sessions *starting* on local day `d`.

    A segment whose end <= start wraps past midnight and closes the following day —
    that is how the COMEX 18:00->17:00 session is expressed.
    """
    if d.weekday() not in v.days:
        return []
    tz = ZoneInfo(v.tz)
    out = []
    for start, end in v.segments:
        end_day = d if end > start else d + timedelta(days=1)
        out.append((datetime.combine(d, start, tz), datetime.combine(end_day, end, tz)))
    return out


def _sessions_around(v: Venue, d: date) -> list[tuple[datetime, datetime]]:
    """Sessions that could contain a moment on day `d` — including one that started
    yesterday and wraps past midnight into today."""
    return _segments_on(v, d - timedelta(days=1)) + _segments_on(v, d)


def venue_state(code: str, now: datetime | None = None) -> dict:
    """State of one venue. `now` is any tz-aware datetime; injected by tests."""
    v = VENUES[code]
    tz = ZoneInfo(v.tz)
    now = (now or datetime.now(tz)).astimezone(tz)
    today = now.date()

    state, closes_at = "CLOSED", None
    for start, end in _sessions_around(v, today):
        if start <= now < end:
            state, closes_at = "OPEN", end
            break
    else:
        segs = _segments_on(v, today)
        # Inside the day's trading window but not in a segment = lunch break (TSE /
        # HKEX / SSE), which is a different thing to the market being shut.
        if len(segs) > 1 and segs[0][0] < now < segs[-1][1]:
            state = "LUNCH"
        elif today.weekday() in (5, 6) and today.weekday() not in v.days:
            # Only an actual Sat/Sun reads WEEKEND. COMEX starts no session on a Friday
            # (the week's last one began Thursday evening), but Friday night is plainly
            # not the weekend — that is an ordinary CLOSED.
            state = "WEEKEND"

    next_open = None
    if state != "OPEN":
        for offset in range(8):          # 8 days covers any weekend from any day
            for start, _end in _segments_on(v, today + timedelta(days=offset)):
                if start > now:
                    next_open = start
                    break
            if next_open:
                break

    # Everything also rendered in the user's own zone (config.HOME_TZ). An India-based
    # trader wants "NYSE opens 19:00 IST", not "09:30 America/New_York" plus arithmetic.
    # Computed from concrete datetimes, so DST on either side is handled — the IST
    # offset of the US open shifts by an hour twice a year and this follows it.
    home = ZoneInfo(HOME_TZ)
    ref = _segments_on(v, today) or _segments_on(v, _next_trading_day(v, today))
    session_home = " / ".join(
        f"{s.astimezone(home):%H:%M}-{e.astimezone(home):%H:%M}" for s, e in ref)

    return {
        "code": v.code, "name": v.name, "tz": v.tz, "note": v.note,
        "local_time": now.strftime("%H:%M"),
        "local_date": now.date().isoformat(),
        "state": state,
        "session": " / ".join(f"{s:%H:%M}-{e:%H:%M}" for s, e in v.segments),
        "session_home": session_home,
        "home_tz": HOME_TZ,
        "home_time": now.astimezone(home).strftime("%H:%M"),
        "opens_at_home": next_open.astimezone(home).strftime("%a %H:%M") if next_open else None,
        "closes_at_home": closes_at.astimezone(home).strftime("%H:%M") if closes_at else None,
        "closes_in_seconds": int((closes_at - now).total_seconds()) if closes_at else None,
        "opens_in_seconds": int((next_open - now).total_seconds()) if next_open else None,
        # Never let a caller present this as authoritative — see module docstring.
        "holidays_applied": False,
    }


def _next_trading_day(v: Venue, d: date) -> date:
    """First weekday on or after `d` that has segments — used only to render a session
    window on days the venue is shut, so the card still shows its normal hours."""
    for offset in range(1, 8):
        nxt = d + timedelta(days=offset)
        if _segments_on(v, nxt):
            return nxt
    return d


def all_venues(now: datetime | None = None) -> list[dict]:
    return [venue_state(c, now) for c in VENUES]


def venue_for(symbol: str) -> str | None:
    return SYMBOL_VENUE.get(symbol)
