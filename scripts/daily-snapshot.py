#!/usr/bin/env python3
"""Record today's fired signals and score the open ones. Runs without the backend.

The signal tracker was a background task inside main.py, so it only recorded on days
uvicorn happened to be running: five snapshot days across three weeks, which is far too
sparse for /edge to say anything about an edge. Task Scheduler doesn't care whether the
API is up, so the series stays continuous.

Safe to run more than once a day, on weekends, and on holidays: snapshot_today is
idempotent via signal_outcomes' UNIQUE constraint, and a repeat of the same session
simply inserts nothing.

    python scripts/daily-snapshot.py [--backfill N]

--backfill N also reconstructs the last N cached sessions before snapshotting, which is
how the original three-week gap was recovered. Exact, not approximate: it replays the
same analyse_df the live path uses over truncated candles.
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

# config.py's bare load_dotenv() searches the cwd upward and so never finds
# backend/.env from anywhere else — Task Scheduler starts in system32, where that means
# falling back to the default DATABASE_URL and failing auth while still exiting 0.
os.chdir(BACKEND)
sys.path.insert(0, str(BACKEND))


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--backfill", type=int, metavar="N",
                    help="reconstruct the last N cached sessions first")
    args = ap.parse_args()

    from app.services.signal_eval import snapshot_today, evaluate_open, backfill

    now = datetime.now(ZoneInfo("Asia/Kolkata"))
    parts = [f"{now:%Y-%m-%d %H:%M} IST"]

    if args.backfill:
        parts.append(f"backfill={backfill(args.backfill)}")
    parts.append(f"logged={snapshot_today()}")
    parts.append(f"scored={evaluate_open()}")

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
