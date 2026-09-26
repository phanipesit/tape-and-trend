#!/usr/bin/env python3
"""Record today's fired signals and score the open ones. Runs without the backend.

The signal tracker was a background task inside main.py, so it only recorded on days
uvicorn happened to be running: five snapshot days across three weeks, which is far too
sparse for /edge to say anything about an edge. Task Scheduler doesn't care whether the
API is up, so the series stays continuous.

Every run reconstructs the last CATCH_UP_SESSIONS sessions before snapshotting, so a
missed run costs nothing as long as another happens within a fortnight. That matters:
scheduling alone was not enough — the task recorded nothing between 2026-08-04 and 08-13
because the machine was off at 18:10, and snapshot_today() can only capture the latest
bar, so those days were gone.

Safe to run more than once a day, on weekends, and on holidays: inserts are idempotent
via signal_outcomes' UNIQUE constraint, so a repeat simply writes nothing.

    python scripts/daily-snapshot.py [--backfill N]   # N=0 to snapshot today only

Reconstruction is exact, not approximate: it replays the same analyse_df the live path
uses over candles truncated at each past date.
"""
from __future__ import annotations

import argparse
import os
import sys
import traceback
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

BACKEND = Path(__file__).resolve().parents[1] / "backend"
LOG = Path(r"C:\users\phani\claude_code\files\signal-tracker.log")

# Sessions reconstructed on every run, so a long outage still heals. Cheap: ~0.1s per
# symbol per 30 sessions, and re-inserting an existing row is a no-op via the table's
# UNIQUE constraint.
#
# Was 15, described as "two weeks with room to spare". There was no room: the laptop
# slept from 2026-09-06 to 09-26, which is exactly 14 trading sessions, and the single
# catch-up run on wake reconstructed all of them with one session to spare. One more
# trading day and the oldest would have been unrecoverable. The window has to be sized
# against how long the machine might be shut, not against how often the job is scheduled
# — those are unrelated numbers, and only the first one decides what survives.
#
# 60 covers roughly a quarter. The real ceiling is cached candle depth, which is 534 bars
# per symbol on average, so there is room to raise this again if an outage ever needs it.
CATCH_UP_SESSIONS = 60

# config.py's bare load_dotenv() searches the cwd upward and so never finds
# backend/.env from anywhere else — Task Scheduler starts in system32, where that means
# falling back to the default DATABASE_URL and failing auth while still exiting 0.
os.chdir(BACKEND)
sys.path.insert(0, str(BACKEND))


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--backfill", type=int, default=CATCH_UP_SESSIONS, metavar="N",
                    help=f"sessions to reconstruct before snapshotting (default {CATCH_UP_SESSIONS}, 0 to skip)")
    args = ap.parse_args()

    from app.services.signal_eval import snapshot_today, evaluate_open, backfill

    now = datetime.now(ZoneInfo("Asia/Kolkata"))
    parts = [f"{now:%Y-%m-%d %H:%M} IST"]

    # Always catch up, never just "today". Scheduling this daily was not enough on its
    # own: between 2026-08-04 and 08-13 the task recorded nothing, because the machine
    # was off at 18:10 and StartWhenAvailable fires one catch-up on wake rather than one
    # per missed day. snapshot_today() can only ever record the latest bar, so every
    # missed day was lost for good. backfill() reconstructs them exactly from cached
    # candles, so running it every time turns "must run daily" into "must run
    # occasionally" — the difference between a fragile job and a self-healing one.
    if args.backfill:
        parts.append(f"backfill={backfill(args.backfill)}")
    parts.append(f"logged={snapshot_today()}")
    parts.append(f"scored={evaluate_open()}")

    # FII/DII capture lives here because NSE publishes no history: the endpoint serves
    # the latest trading day and nothing else, so a day not captured is gone for good.
    # Unlike the signal snapshot above, no backfill can rescue it. Failure must not take
    # the rest of the run down with it.
    try:
        from app.services.flows import refresh as refresh_flows
        parts.append(f"flows={refresh_flows()}")
    except Exception as e:
        parts.append(f"flows=FAILED({type(e).__name__}: {str(e)[:60]})")

    # Bond yields. Unlike flows, FBIL keeps an archive, so a missed day heals on the next
    # run — refresh_in downloads only the listed dates not yet stored. It lives here for
    # the same reason chains do: the board reads cache only, and nothing else drives it.
    try:
        from app.services.bonds import refresh as refresh_bonds
        b = refresh_bonds()
        parts.append(f"bonds[IN]={b['IN'].get('stored', b['IN'])} bonds[US]={b['US'].get('refreshed', b['US'])}")
    except Exception as e:
        parts.append(f"bonds=FAILED({type(e).__name__}: {str(e)[:60]})")

    # Option chains refresh only when someone opens the Options page, so ^NSEI sat on a
    # 2026-08-03 fetch for a month while the lab happily priced off it. The staleness
    # window exists but nothing drives it. Only the index underlyings: those are the ones
    # the lab defaults to, and equity chains are fetched on demand.
    from app.services.nse_chain import refresh_chain, prune_expired
    for sym in ("^NSEI", "^NSEBANK"):
        try:
            parts.append(f"chain[{sym}]={refresh_chain(sym)}")
        except Exception as e:
            parts.append(f"chain[{sym}]=FAILED({type(e).__name__}: {str(e)[:40]})")

    # refresh_chain prunes only the symbol it just fetched, so a name looked up once on
    # the Options page and never again keeps its dead contracts forever. Sweep the whole
    # table instead, and after the refreshes rather than before, so a contract expiring
    # today is replaced by the live one in the same run.
    try:
        parts.append(f"pruned={prune_expired()}")
    except Exception as e:
        parts.append(f"pruned=FAILED({type(e).__name__}: {str(e)[:40]})")

    line = " | ".join(parts)
    print(line)
    LOG.parent.mkdir(parents=True, exist_ok=True)
    with LOG.open("a", encoding="utf-8") as f:
        f.write(line + "\n")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception:
        traceback.print_exc()
        sys.exit(1)
