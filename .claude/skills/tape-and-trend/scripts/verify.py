#!/usr/bin/env python3
"""Pre-commit verification for Tape & Trend.

Runs the checks that were previously done by hand, in the order that catches the
most for the least time: the test suite first, then — only if the dev servers
happen to already be running — that every frontend route still renders and the
backend's OpenAPI schema still parses.

It never starts or stops a server. `npm run build` would clobber a running dev
server's .next directory, and this script exists partly so nobody reaches for it.
Server-dependent checks are SKIPPED, not failed, when nothing is listening.

Usage:  python .claude/skills/tape-and-trend/scripts/verify.py [--no-tests]
Exit:   0 all passed (skips are fine), 1 something failed.
"""
from __future__ import annotations

import argparse
import json
import re
import socket
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
BACKEND, FRONTEND = ROOT / "backend", ROOT / "frontend"
API, WEB = "http://localhost:8000", "http://localhost:3000"

PASS, FAIL, SKIP = "PASS", "FAIL", "SKIP"
results: list[tuple[str, str, str]] = []


def record(status: str, name: str, detail: str = "") -> None:
    results.append((status, name, detail))
    mark = {PASS: "ok  ", FAIL: "FAIL", SKIP: "skip"}[status]
    print(f"  {mark}  {name}{f' — {detail}' if detail else ''}", flush=True)


def venv_python() -> Path | None:
    for rel in ("Scripts/python.exe", "bin/python"):
        p = BACKEND / ".venv" / rel
        if p.exists():
            return p
    return None


def listening(port: int) -> bool:
    with socket.socket() as s:
        s.settimeout(0.4)
        return s.connect_ex(("127.0.0.1", port)) == 0


def fetch(url: str, timeout: float = 20.0) -> tuple[int, str]:
    try:
        with urllib.request.urlopen(url, timeout=timeout) as r:
            return r.status, r.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8", "replace")


def run_tests() -> None:
    print("\nBackend tests")
    py = venv_python()
    if py is None:
        record(FAIL, "pytest", "no venv at backend/.venv — create it before verifying")
        return
    proc = subprocess.run([str(py), "-m", "pytest", "-q"], cwd=BACKEND,
                          capture_output=True, text=True)
    tail = [ln for ln in proc.stdout.strip().splitlines() if ln.strip()]
    summary = tail[-1] if tail else "no output"
    record(PASS if proc.returncode == 0 else FAIL, "pytest", summary)
    if proc.returncode != 0:
        print("\n".join(tail[-25:]))


def check_backend() -> None:
    print("\nBackend API (localhost:8000)")
    if not listening(8000):
        record(SKIP, "api", "not running — start with: python -m uvicorn app.main:app --reload")
        return
    status, body = fetch(f"{API}/openapi.json")
    if status != 200:
        record(FAIL, "GET /openapi.json", f"HTTP {status}")
        return
    try:
        paths = json.loads(body).get("paths", {})
    except json.JSONDecodeError as e:
        record(FAIL, "GET /openapi.json", f"unparseable: {e}")
        return
    record(PASS, "GET /openapi.json", f"{len(paths)} routes registered")


def check_routers_registered() -> None:
    """Every routers/*.py must appear in main.py's ROUTERS tuple.

    Checked against main.py's source, not against URL paths: a module's name has no
    required relation to the paths it serves (quotes.py serves /api/watchlist,
    symbols_admin.py serves /api/symbols), so matching on paths gives false alarms.
    Forgetting the tuple is the real silent failure — the module imports fine and
    simply never mounts.
    """
    print("\nRouter registration")
    src = (BACKEND / "app" / "main.py").read_text(encoding="utf-8")
    m = re.search(r"^ROUTERS\s*=\s*\((.*?)\)", src, re.S | re.M)
    if not m:
        record(FAIL, "ROUTERS tuple", "not found in main.py")
        return
    listed = set(re.findall(r"[A-Za-z_][A-Za-z0-9_]*", m.group(1)))
    on_disk = {p.stem for p in (BACKEND / "app" / "routers").glob("*.py")
               if p.stem != "__init__"}
    missing = sorted(on_disk - listed)
    if missing:
        record(FAIL, "ROUTERS tuple",
               f"not mounted: {', '.join(missing)} — add to main.py's import AND ROUTERS")
    else:
        record(PASS, "ROUTERS tuple", f"all {len(on_disk)} routers mounted")


def check_frontend() -> None:
    print("\nFrontend routes (localhost:3000)")
    if not listening(3000):
        record(SKIP, "web", "not running — start with: npm run dev")
        return
    routes = ["/"] + sorted(
        f"/{p.parent.name}" for p in (FRONTEND / "app").glob("*/page.jsx"))
    for route in routes:
        status, body = fetch(WEB + route)
        low = body.lower()
        if status != 200:
            record(FAIL, route, f"HTTP {status}")
        elif "failed to compile" in low or "unhandled runtime error" in low:
            record(FAIL, route, "compile/runtime error in page")
        else:
            record(PASS, route)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--no-tests", action="store_true", help="skip the pytest run")
    args = ap.parse_args()

    print(f"Tape & Trend verify — {ROOT}")
    if not args.no_tests:
        run_tests()
    check_routers_registered()
    check_backend()
    check_frontend()

    failed = [r for r in results if r[0] == FAIL]
    skipped = [r for r in results if r[0] == SKIP]
    print(f"\n{len(results) - len(failed) - len(skipped)} passed, "
          f"{len(failed)} failed, {len(skipped)} skipped")
    if skipped:
        print("Skipped checks need the dev servers up — start them and re-run "
              "if this is a pre-commit check.")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
