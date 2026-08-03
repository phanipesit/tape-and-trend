#!/usr/bin/env python3
"""Refresh intraday data at the NSE open and write a report of what fired.

The point is survivability: the equivalent check scheduled inside a Claude session
dies when that session exits. This runs from Windows Task Scheduler, so it produces
its report whether or not anything else is running, and the report is waiting when
you next sit down.

Writes to claude_code/files/market-open-YYYY-MM-DD.md and prints the same to stdout.
Exits 0 even when nothing fired — "no setup" is a valid, expected result. Non-zero
only on a real failure, so a red task in Task Scheduler means something broke.
"""
from __future__ import annotations

import os
import sys
import traceback
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

BACKEND = Path(__file__).resolve().parents[1] / "backend"
OUT_DIR = Path(r"C:\users\phani\claude_code\files")
SYMBOLS = ["TCS", "HDFCBANK", "TATAELXSI", "^NSEI", "^NSEBANK"]
INTERVAL = "5m"

# config.py calls load_dotenv() with no path, which searches the CWD and its parents
# and so never looks *into* backend/. Launched from anywhere else — Task Scheduler
# starts in system32 — DATABASE_URL silently falls back to the built-in default and
# every query fails auth. Both lines are required: cwd for the .env, path for imports.
os.chdir(BACKEND)
sys.path.insert(0, str(BACKEND))


def main() -> int:
    from app.services import data, intraday_signals
    from app.services.market_hours import all_venues

    ist = ZoneInfo("Asia/Kolkata")
    now = datetime.now(ist)
    lines = [f"# Market open check — {now:%a %Y-%m-%d %H:%M} IST", ""]

    nse = next((v for v in all_venues() if v["code"] == "NSE"), None)
    state = nse["state"] if nse else "UNKNOWN"
    lines.append(f"NSE state: **{state}**")
    if state != "OPEN":
        # No holiday calendar exists by design, so a CLOSED reading here is
        # trustworthy but an OPEN one on a public holiday is not.
        lines += ["", "Not open — nothing to check. (Note: no holiday calendar is "
                      "applied, so an OPEN state on a holiday would be wrong.)"]
        return write(lines, now)

    lines += ["", "| symbol | bar | close | vwap | rvol | signal | score | dir | entry | stop | target | rule |",
              "|---|---|---|---|---|---|---|---|---|---|---|---|"]
    problems: list[str] = []

    for sym in SYMBOLS:
        try:
            data.refresh_intraday(sym, INTERVAL)
            df = data.get_intraday(sym, INTERVAL)
            if df is None or df.empty:
                problems.append(f"{sym}: no intraday bars returned")
                continue
            res = intraday_signals.analyse(sym, INTERVAL)
            sigs = res.get("signals") or []
            top = sigs[0] if sigs else None
            # analyse() returns `close`, not `last` — the daily engine's key names
            # do not carry over to the intraday one.
            vwap, rvol = res.get("vwap"), res.get("rvol")
            lines.append(
                f"| {sym} | {res.get('ts')} | {res.get('close')} "
                f"| {'—' if vwap is None else round(vwap, 2)} "
                f"| {'—' if rvol is None else round(rvol, 2)} "
                f"| {top['type'] if top else 'none'} | {res.get('score')} "
                f"| {res.get('direction')} | {res.get('entry')} | {res.get('stop')} "
                f"| {res.get('target')} | {top['why'] if top else '—'} |")
        except Exception:
            problems.append(f"{sym}: {traceback.format_exc(limit=3)}")

    lines += ["", f"Bars are {INTERVAL}. Index symbols report zero volume from Yahoo, so "
                  "vwap is null for ^NSEI/^NSEBANK and volume-gated rules cannot fire — "
                  "expected, not a fault.",
              "", "Opening-range rules need the first 15 minutes to complete; a run this "
                  "early may legitimately show nothing."]
    if problems:
        lines += ["", "## Problems", ""] + [f"- {p}" for p in problems]
    return write(lines, now, failed=bool(problems))


def write(lines: list[str], now: datetime, failed: bool = False) -> int:
    text = "\n".join(lines) + "\n"
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUT_DIR / f"market-open-{now:%Y-%m-%d}.md").write_text(text, encoding="utf-8")
    print(text)
    return 1 if failed else 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception:
        traceback.print_exc()
        sys.exit(1)
