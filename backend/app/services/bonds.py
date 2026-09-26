"""Government bond yields: India's G-Sec par curve and US Treasuries.

**India comes from FBIL, not Yahoo.** Yahoo carries US Treasuries but no India yield under
any ticker (probed 2026-09-26: IN10Y=RR, ^IN10Y, GIND10YR and friends all 404). NSE's
`liveBonds-traded-on-cm?type=gsec` does answer, but it is retail cash-market prints — the
sample row was 100 units that jumped 5% to its price band — which is a trade, not a
benchmark. FBIL (Financial Benchmarks India) administers the official G-Sec valuation
and publishes its par yield curve daily, 3M to 40Y in quarter-year steps.

Two things about FBIL worth not rediscovering:

- The data is an **xlsx download**, one file per date, from `/wasdm/gsec/downloadPublished
  ?date=YYYY-MM-DD`; `/wasdm/gsec/fetchfiltered` lists which dates exist. The par curve is
  the sheet named "Par Yield". It is parsed with zipfile + ElementTree rather than pulling
  in openpyxl for one sheet of two columns.
- **The public archive list trails by about a week** (on 2026-09-26 its newest entry was
  09-18). Files for later dates *do* download if asked for by name, but the list is FBIL's
  statement of what it publishes to unauthenticated users, so only listed dates are
  fetched. The board reports `as_of` and `lag_days` so a week-old curve never passes for
  today's.

Unlike FII/DII flows the archive has history (back to 2024-01-01), so a missed day heals
on the next run: `refresh_in` diffs the listed dates against what is stored and downloads
only the gap.

**Changes are in basis points, never percent.** A move from 7.08% to 7.14% is +6bp; calling
it "+0.85%" is how yield moves get misread. Yahoo quotes US yields in percent (^TNX 5.18
means 5.18%), and ^IRX is the 13-week bill's discount rate, not a bond-equivalent yield —
close enough for a curve-shape read, a few bp off for anything finer.

The slope compared across both markets is **10Y minus 3M**, because it is the one pair
both sources carry (Yahoo has no 2Y) and it is the spread the NY Fed's recession model uses.
"""
from __future__ import annotations

import io
import logging
import re
import time
import xml.etree.ElementTree as ET
import zipfile
from datetime import date, datetime, timedelta

import httpx

from ..db import engine, q
from .data import get_candles, market_context, refresh_candles

log = logging.getLogger(__name__)

FBIL = "https://www.fbil.org.in/wasdm/gsec"
HEADERS = {
    "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                   "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"),
    "Accept": "application/json, text/plain, */*",
    "Referer": "https://www.fbil.org.in/",
}

# A year and a bit, so 1-month changes and a year of context exist from the first run.
# After that each run downloads only the handful of dates it hasn't stored.
BACKFILL_DAYS = 400
DOWNLOAD_PAUSE = 0.2        # seconds between files — this is someone else's server

IN_TENORS = (0.25, 2, 5, 10, 30)
US_TENORS = {"^IRX": 0.25, "^FVX": 5, "^TNX": 10, "^TYX": 30}

FLAT_BP = 50                # 10Y-3M under this is a flat curve; under zero, inverted
STEADY_BP = 10              # a monthly 10Y move smaller than this is noise

_M = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
_R = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}"


def tenor_label(t: float) -> str:
    return f"{round(t * 12)}M" if t < 1 else f"{t:g}Y"


def _bp(a: float | None, b: float | None) -> float | None:
    return None if a is None or b is None else round((a - b) * 100, 1)


# ---------------------------------------------------------------- FBIL parsing (pure)

def _sheet_path(z: zipfile.ZipFile, name: str) -> str:
    """Resolve a sheet by its visible name — FBIL's file has four sheets and the order is
    theirs to change, the name is what the page shows."""
    wb = ET.fromstring(z.read("xl/workbook.xml"))
    rid = next((s.get(f"{_R}id") for s in wb.iter(f"{_M}sheet") if s.get("name") == name), None)
    if rid is None:
        raise ValueError(f"no sheet named {name!r}")
    rels = ET.fromstring(z.read("xl/_rels/workbook.xml.rels"))
    target = next(r.get("Target") for r in rels if r.get("Id") == rid)
    return target.lstrip("/") if target.startswith("/xl/") else f"xl/{target}"


def _rows(z: zipfile.ZipFile, path: str) -> list[list[str]]:
    shared = []
    if "xl/sharedStrings.xml" in z.namelist():
        shared = ["".join(t.text or "" for t in si.iter(f"{_M}t"))
                  for si in ET.fromstring(z.read("xl/sharedStrings.xml"))]
    out = []
    for row in ET.fromstring(z.read(path)).iter(f"{_M}row"):
        vals = []
        for c in row.iter(f"{_M}c"):
            v = c.find(f"{_M}v")
            if v is not None:
                vals.append(shared[int(v.text)] if c.get("t") == "s" else v.text or "")
            else:
                inline = c.find(f"{_M}is")
                vals.append("".join(t.text or "" for t in inline.iter(f"{_M}t")) if inline is not None else "")
        out.append(vals)
    return out


def _float(s) -> float | None:
    try:
        return float(s)
    except (TypeError, ValueError):
        return None


def parse_par_curve(blob: bytes) -> tuple[date, list[tuple[float, float, float | None]]]:
    """FBIL xlsx -> (curve date, [(tenor_years, semi_annual_pct, annualised_pct)]).

    The date comes from the sheet's own header, not the request, so a file for the wrong
    day can be caught by the caller rather than silently filed under the date asked for."""
    z = zipfile.ZipFile(io.BytesIO(blob))
    rows = _rows(z, _sheet_path(z, "Par Yield"))
    curve_date = None
    for r in rows[:6]:
        for cell in r:
            if re.fullmatch(r"\d{2}-[A-Za-z]{3}-\d{4}", cell.strip()):
                curve_date = datetime.strptime(cell.strip(), "%d-%b-%Y").date()
                break
        if curve_date:
            break
    if curve_date is None:
        raise ValueError("par yield sheet has no header date")

    points = []
    for r in rows:
        tenor, semi = _float(r[0] if r else None), _float(r[1] if len(r) > 1 else None)
        if tenor is None or semi is None or tenor <= 0:
            continue
        points.append((tenor, semi, _float(r[2]) if len(r) > 2 else None))
    if not points:
        raise ValueError("par yield sheet has no tenor rows")
    return curve_date, points


# ---------------------------------------------------------------- fetch / store

def _published_dates(client: httpx.Client, start: date, end: date) -> list[date]:
    r = client.get(f"{FBIL}/fetchfiltered", params={
        "fromDate": start.isoformat(), "toDate": end.isoformat(), "authenticated": "false"})
    r.raise_for_status()
    return sorted({date.fromisoformat(x["processRunDate"]) for x in r.json()})


def refresh_in(days: int = BACKFILL_DAYS) -> dict:
    """Store every FBIL par curve published in the last `days` that we don't have yet."""
    end = date.today()
    start = end - timedelta(days=days)
    have = {r["curve_date"] for r in q(
        "SELECT DISTINCT curve_date FROM bond_yields WHERE country='IN' AND curve_date >= :s", s=start)}
    stored, failed = 0, []
    with httpx.Client(headers=HEADERS, timeout=30, follow_redirects=True) as c:
        published = _published_dates(c, start, end)
        for d in (d for d in published if d not in have):
            try:
                r = c.get(f"{FBIL}/downloadPublished", params={"date": d.isoformat()})
                r.raise_for_status()
                curve_date, points = parse_par_curve(r.content)
                if curve_date != d:
                    raise ValueError(f"file for {d} is dated {curve_date}")
                with engine.begin() as cx:
                    for tenor, semi, annual in points:
                        cx.exec_driver_sql(
                            """INSERT INTO bond_yields
                                 (country, curve_date, tenor_years, yield_pct, yield_annual, source)
                               VALUES ('IN', %s, %s, %s, %s, 'FBIL par yield')
                               ON CONFLICT (country, curve_date, tenor_years) DO UPDATE SET
                                 yield_pct=EXCLUDED.yield_pct, yield_annual=EXCLUDED.yield_annual,
                                 fetched_at=now()""",
                            (curve_date, tenor, semi, annual))
                stored += 1
            except Exception as e:
                failed.append(d.isoformat())
                log.warning("FBIL par curve %s failed: %s", d, e)
            time.sleep(DOWNLOAD_PAUSE)
    return {"stored": stored, "failed": failed,
            "published_latest": published[-1].isoformat() if published else None}


def refresh_us() -> dict:
    ok, failed = 0, []
    for meta in market_context(("bond",)):
        try:
            refresh_candles(meta["symbol"])
            ok += 1
        except Exception:
            failed.append(meta["symbol"])
            log.warning("treasury refresh failed for %s", meta["symbol"], exc_info=True)
    return {"refreshed": ok, "failed": failed}


def refresh() -> dict:
    """Both markets; one failing must not stop the other."""
    out = {}
    for key, fn in (("IN", refresh_in), ("US", refresh_us)):
        try:
            out[key] = fn()
        except Exception as e:
            out[key] = {"error": f"{type(e).__name__}: {str(e)[:120]}"}
    return out


# ---------------------------------------------------------------- read path (cache only)

def _in_series() -> dict[date, dict[float, float]]:
    rows = q("""SELECT curve_date, tenor_years, yield_pct FROM bond_yields
                WHERE country='IN' AND tenor_years = ANY(:t)
                  AND curve_date >= (SELECT MAX(curve_date) FROM bond_yields WHERE country='IN') - 45""",
             t=[float(t) for t in IN_TENORS])
    out: dict[date, dict[float, float]] = {}
    for r in rows:
        out.setdefault(r["curve_date"], {})[float(r["tenor_years"])] = float(r["yield_pct"])
    return out


def _us_series() -> dict[date, dict[float, float]]:
    out: dict[date, dict[float, float]] = {}
    for meta in market_context(("bond",)):
        tenor = US_TENORS.get(meta["symbol"])
        if tenor is None:
            continue
        df = get_candles(meta["symbol"], limit=40, auto=False)
        for d, c in zip(df["d"], df["c"]) if not df.empty else ():
            out.setdefault(d, {})[float(tenor)] = round(float(c), 3)   # float32 noise off Yahoo
    return out


def summarise(series: dict[date, dict[float, float]], tenors, source: str,
              today: date | None = None) -> dict | None:
    """Latest curve points, 1-day and ~1-month changes in bp, and the curve's shape.
    Pure: a {date: {tenor: yield}} map in, conclusions out."""
    dates = sorted(d for d, pts in series.items() if 10 in pts)
    if not dates:
        return None
    today = today or date.today()
    last = dates[-1]
    prev = dates[-2] if len(dates) > 1 else None
    month = next((d for d in reversed(dates) if d <= last - timedelta(days=28)), None)
    cur = series[last]

    points = []
    for t in tenors:
        t = float(t)
        y = cur.get(t)
        points.append({
            "tenor": t, "label": tenor_label(t), "yield": y,
            "chg_bp": _bp(y, series[prev].get(t)) if prev else None,
            "chg_1m_bp": _bp(y, series[month].get(t)) if month else None,
        })

    slope = _bp(cur.get(10.0), cur.get(0.25))
    shape = (None if slope is None else "inverted" if slope < 0
             else "flat" if slope < FLAT_BP else "normal")
    ten_1m = next(p["chg_1m_bp"] for p in points if p["tenor"] == 10.0)
    trend = (None if ten_1m is None else "steady" if abs(ten_1m) < STEADY_BP
             else "rising" if ten_1m > 0 else "falling")

    return {"source": source, "as_of": last.isoformat(), "lag_days": (today - last).days,
            "points": points, "ten_year": cur.get(10.0), "slope_10y_3m_bp": slope,
            "curve": shape, "ten_year_1m": trend}


def ten_year_on(series: dict[date, dict[float, float]], on: date) -> tuple[date, float] | None:
    """The 10Y on `on`, or the latest session before it."""
    d = max((d for d, pts in series.items() if d <= on and 10.0 in pts), default=None)
    return (d, series[d][10.0]) if d else None


def read(india: dict | None, us: dict | None, us_matched: tuple[date, float] | None = None) -> dict:
    """The one-line read, so the UI renders conclusions rather than deriving them.

    The spread is taken on India's date, not each side's latest: FBIL's public curve trails
    by about a week, and pairing it with today's Treasury close measured a week of US
    moves as if it were the spread (US 10Y moved 46bp in the month this was built)."""
    spread, spread_as_of = None, None
    if india and us_matched:
        spread, spread_as_of = _bp(india["ten_year"], us_matched[1]), us_matched[0].isoformat()
    parts = []
    for name, m in (("India", india), ("US", us)):
        if m and m["curve"]:
            s = f"{name} curve {m['curve']}"
            if m["ten_year_1m"]:
                s += f", 10Y {m['ten_year_1m']} over the month"
            parts.append(s)
    if spread is not None:
        parts.append(f"India 10Y {'over' if spread >= 0 else 'under'} US by {abs(spread):g}bp")
    return {"spread_10y_bp": spread, "spread_as_of": spread_as_of,
            "verdict": "; ".join(parts) or "no bond data cached yet"}


def board(today: date | None = None) -> dict:
    us_s = _us_series()
    india = summarise(_in_series(), IN_TENORS, "FBIL par yield · semi-annual", today)
    us = summarise(us_s, sorted(US_TENORS.values()), "Yahoo · ^IRX ^FVX ^TNX ^TYX", today)
    matched = ten_year_on(us_s, date.fromisoformat(india["as_of"])) if india else None
    return {"IN": india, "US": us, **read(india, us, matched)}
