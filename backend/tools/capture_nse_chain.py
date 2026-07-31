"""Capture NSE's live option chain to raw JSON files, for building a parser against.

Run during market hours (Mon-Fri 09:15-15:30 IST) — outside them NSE returns HTTP 200
with an empty body, which is what we got probing on a Saturday.

    python tools/capture_nse_chain.py

Writes timestamped raw payloads to backend/tools/nse_captures/. Deliberately does NOT
parse: the point is to capture ground truth so the parser is written against a real
schema rather than a guessed one.

Notes on NSE's undocumented API, learned the hard way:
  - A warm-up GET on the HTML page is mandatory; it sets the cookies the /api/ paths need.
  - A browser User-Agent and Referer are required or you get 403.
  - /api/option-chain-indices (the path in most tutorials) is DEAD — returns 404.
    The live path is /api/option-chain-v3?type=Indices|Equities&symbol=...
"""
import json
import sys
import time
from datetime import datetime
from pathlib import Path

import httpx

OUT = Path(__file__).parent / "nse_captures"
WARMUP = "https://www.nseindia.com/option-chain"
TARGETS = [
    ("NIFTY", "https://www.nseindia.com/api/option-chain-v3?type=Indices&symbol=NIFTY"),
    ("BANKNIFTY", "https://www.nseindia.com/api/option-chain-v3?type=Indices&symbol=BANKNIFTY"),
    ("RELIANCE", "https://www.nseindia.com/api/option-chain-v3?type=Equities&symbol=RELIANCE"),
]
HEADERS = {
    "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                   "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"),
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": WARMUP,
}


def summarise(payload: dict) -> str:
    """One line of shape info, so a glance tells you whether the capture is usable."""
    rec = payload.get("records") or payload.get("data") or {}
    if isinstance(rec, dict):
        rows = rec.get("data") or []
        expiries = rec.get("expiryDates") or []
        spot = rec.get("underlyingValue")
    else:
        rows, expiries, spot = rec, [], None
    iv = None
    for r in rows if isinstance(rows, list) else []:
        ce = r.get("CE") or {}
        if ce.get("impliedVolatility"):
            iv = f"strike {ce.get('strikePrice')} IV {ce['impliedVolatility']} LTP {ce.get('lastPrice')}"
            break
    return (f"top-level keys={list(payload)[:6]} rows={len(rows) if isinstance(rows, list) else '?'} "
            f"expiries={len(expiries)} spot={spot} sample_CE=({iv})")


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    print(f"capture at {datetime.now():%Y-%m-%d %H:%M:%S} (local)\n")

    ok = 0
    with httpx.Client(headers=HEADERS, timeout=30, follow_redirects=True) as c:
        w = c.get(WARMUP)
        print(f"warm-up: HTTP {w.status_code}, {len(c.cookies)} cookies")
        if w.status_code != 200 or not len(c.cookies):
            print("  !! warm-up failed — every /api/ call will 403. Aborting.")
            return 1

        for name, url in TARGETS:
            time.sleep(1.0)   # be a polite client; NSE rate-limits hard
            try:
                r = c.get(url)
            except Exception as e:
                print(f"{name:<10} ERROR {type(e).__name__}: {e}")
                continue
            if r.status_code != 200:
                print(f"{name:<10} HTTP {r.status_code} — not captured")
                continue
            if len(r.content) < 100:
                print(f"{name:<10} HTTP 200 but {len(r.content)}b (empty — market closed?)")
                continue

            path = OUT / f"{name}-{stamp}.json"
            path.write_bytes(r.content)
            ok += 1
            try:
                print(f"{name:<10} HTTP 200  {len(r.content):>8}b -> {path.name}")
                print(f"           {summarise(r.json())}")
            except Exception:
                print(f"{name:<10} saved but is not valid JSON — inspect {path.name}")

    print(f"\n{ok}/{len(TARGETS)} captured into {OUT}")
    if not ok:
        print("Nothing captured. If it's a weekday inside 09:15-15:30 IST, NSE is likely "
              "blocking this client — try again from a browser-adjacent context.")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
