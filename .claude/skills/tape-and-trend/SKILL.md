---
name: tape-and-trend
description: Build, verify and ship changes in the Tape & Trend trading workbench (FastAPI + Next.js + PostgreSQL). Use this skill whenever work touches this repo — adding an endpoint, service, migration, or page; wiring a new feature area; running the test suite; or checking a change before committing. Also use it when about to run the backend, the frontend, or a database migration, since several obvious-looking commands here fail in specific ways. Do not skip it because a change looks small.
---

# Tape & Trend

`CLAUDE.md` describes *what the architecture is* and is already in context. This skill
covers what prose can't: the commands that fail in non-obvious ways, and the two
workflows that should be mechanical rather than remembered.

Read `CLAUDE.md` for architecture. Read this before running anything.

## Commands that fail if you type the obvious thing

| Do | Not | Why |
|---|---|---|
| `python -m uvicorn app.main:app --reload` | `uvicorn app.main:app` | Device Guard blocks pip's unsigned `.exe` shims |
| Stop the dev server, then `npm run build` | `npm run build` while `npm run dev` runs | Both use `.next`; the build overwrites what dev is serving and **every** route 500s, including ones you didn't touch. Recovery: stop dev, `rm -rf .next`, restart |
| `backend/.venv/Scripts/python.exe -m pytest` | `pytest` | Tests must run under the venv interpreter |
| Check `db/` for the highest `migration_NNN` | Trust `CLAUDE.md` or `UPDATE-INSTRUCTIONS.md` numbering | Both documents are wrong about it — see the "Known inconsistency" section. `scripts/next_migration.py` reads the directory instead |

There is **no frontend test runner, linter, or type checker**. Don't invent commands for
them. Verify frontend changes by fetching the route (`scripts/verify.py` does this).

## Workflow: adding a feature area

Every step is load-bearing; a missing one fails silently at request time, not at startup.

1. **Migration** — `python .claude/skills/tape-and-trend/scripts/next_migration.py <slug>`
   scaffolds the next free number. **Additive only** — never edit `schema.sql` or a
   shipped migration in place.
2. **Service** — `backend/app/services/<name>.py`. All logic lives here.
   - Read paths use **cached candles only** (`get_candles(..., auto=False)`). A live
     yfinance fetch per symbol across a universe is the multi-minute stall
     `routers/screener.py` warns about. Refresh is an explicit opt-in path.
   - Compute conclusions, not raw numbers, when the output feeds a model or a template —
     see `ai_analysis._context()`'s `derived` block for why.
3. **Router** — `backend/app/routers/<name>.py`, thin: parse, call the service, return.
4. **Register it** — add the module to **both** the import tuple and `ROUTERS` in
   `backend/app/main.py`. Two places, not one.
5. **New table?** — add it to `TABLES` in `main.py` so the startup check catches a
   migration that was never run.
6. **Frontend** — `frontend/app/<route>/page.jsx` (`"use client"`, calls `lib/api.js`'s
   `api()`), plus a `Nav.jsx` entry. Reuse the Tailwind palette tokens
   (`bg/panel/panel2/line/line2/txt/mut/dim/brass/up/down/info`); don't introduce colours.
7. **Tests** — `backend/tests/test_<name>.py`, DB-free: monkeypatch `q()` and any
   fetchers. See `test_markets.py` or `test_heatmap.py` for the fixture shape.
8. **Verify** — `python .claude/skills/tape-and-trend/scripts/verify.py`.
9. **Document** — add the *why*, not the *what*, to `CLAUDE.md`.

## Workflow: before committing

Run `python .claude/skills/tape-and-trend/scripts/verify.py`. It runs the suite, then —
if the dev servers happen to be up — checks every frontend route renders and the
OpenAPI schema still parses. It never starts or stops a server, and skips those checks
cleanly when nothing is listening.

Then: branch off `main`, commit, fast-forward `main`, push. Explain *why* in the commit
body — this repo's history carries the reasoning, not just the change.

## Traps that have actually bitten

- **Mixed currencies.** `symbols.mcap` and turnover are in each listing's own currency.
  Reliance reads 17.3T (₹) against NVIDIA's 5.0T ($). Never size, rank or total across
  markets on a raw value — normalise per market first (`services/heatmap._shares`).
- **Substring matching on sector labels.** `'%ai%'` also matches Ret**ai**l, **Ai**rlines
  and P**ai**nts, all seeded in the Indian universe. Match tokens, not substrings.
- **`asset_class`, not `is_index`,** is what keeps rows out of stock pickers.
  `is_index` means "tradeable options underlying".
- **Weekend/holiday staleness is not a bug.** A Saturday serving Friday's close with
  `stale:false` is the guard working. There is deliberately no holiday calendar.
- **Index symbols report zero intraday volume** from Yahoo, so VWAP is `null` and
  volume-gated intraday rules never fire for them. Expected.
- **A browser tab can serve a stale client bundle** after an edit — Next reports a
  hydration mismatch reading `Server: "<new>" / Client: "<old>"`. Verify against
  `curl` of the route, which is the source of truth, rather than chasing it as a bug.
