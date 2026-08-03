#!/usr/bin/env python3
"""Scaffold the next db/migration_NNN file by reading the directory.

Migration numbering in this repo cannot be taken from the docs: CLAUDE.md and
UPDATE-INSTRUCTIONS.md disagree with each other and both are stale (migration_002's
contents are actually the AI-universe migration its own header calls _003). Both
documents say so, and then say to check `db/` instead — which is what this does.

Usage:  python .claude/skills/tape-and-trend/scripts/next_migration.py <slug>
        python .claude/skills/tape-and-trend/scripts/next_migration.py --list
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

DB = Path(__file__).resolve().parents[4] / "db"
PATTERN = re.compile(r"^migration_(\d+)")

TEMPLATE = """\
-- migration_{num}_{slug}.sql
-- {title}
--
-- Additive only: never edit schema.sql or a shipped migration in place.
-- After adding a table here, add its name to TABLES in backend/app/main.py so the
-- startup check catches a migration that was never run.

BEGIN;

-- your DDL here

COMMIT;
"""


def existing() -> list[tuple[int, Path]]:
    found = []
    for f in sorted(DB.glob("migration_*.sql")):
        m = PATTERN.match(f.name)
        if m:
            found.append((int(m.group(1)), f))
    return sorted(found)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("slug", nargs="?", help="short name, e.g. 'options_chain'")
    ap.add_argument("--list", action="store_true", help="show existing migrations and exit")
    args = ap.parse_args()

    if not DB.is_dir():
        print(f"no db/ directory at {DB}", file=sys.stderr)
        return 1

    found = existing()
    if args.list or not args.slug:
        for num, f in found:
            print(f"  {num:03d}  {f.name}")
        nxt = (found[-1][0] + 1) if found else 1
        print(f"\nnext free number: {nxt:03d}")
        return 0 if args.list else 1

    slug = re.sub(r"[^a-z0-9_]+", "_", args.slug.lower()).strip("_")
    num = (found[-1][0] + 1) if found else 1
    path = DB / f"migration_{num:03d}_{slug}.sql"
    if path.exists():
        print(f"{path.name} already exists — refusing to overwrite", file=sys.stderr)
        return 1

    path.write_text(TEMPLATE.format(num=f"{num:03d}", slug=slug,
                                    title=slug.replace("_", " ").capitalize()),
                    encoding="utf-8")
    print(f"created db/{path.name}")
    print(f"apply with: psql -d tapetrend -f db/{path.name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
