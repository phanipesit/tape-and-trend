"use client";
import { useEffect, useState } from "react";
import { api, fmt } from "../lib/api";

// FII/DII cash flows. Deliberately a thin strip, not a card: NSE publishes no history,
// so this starts at one day and fills in daily, and a large panel would spend a
// fortnight looking broken.

const REGIME_STYLE = {
  "DUAL BUYING": "border-up text-up",
  "FII NET BUYER": "border-up text-up",
  "DII ABSORPTION": "border-brass text-brass",
  MIXED: "border-line2 text-mut",
  "FII NET SELLER": "border-down text-down",
  "DUAL SELLING": "border-down text-down",
};

const cr = (v) => (v == null ? "—" : `${v > 0 ? "+" : "−"}${fmt(Math.abs(v), 0)}cr`);
const cls = (v) => (v > 0 ? "text-up" : v < 0 ? "text-down" : "text-mut");

// "+3 buying" / "−6 selling"; a flat day breaks the run and reads as 0.
const streak = (n) =>
  n === 0 ? "no run" : `${Math.abs(n)}d ${n > 0 ? "buying" : "selling"}`;

export default function FlowsStrip() {
  const [d, setD] = useState(null);
  const [busy, setBusy] = useState(false);

  const load = () => api("/api/flows").then(setD).catch(() => setD(null));
  useEffect(() => { load(); }, []);

  const refresh = () => {
    setBusy(true);
    api("/api/flows/refresh", { method: "POST" }).then(load)
      .catch(() => {}).finally(() => setBusy(false));
  };

  if (!d) return null;              // silent when unavailable; it is supplementary
  const s = d.summary;

  return (
    <div className="card text-xs">
      <div className="flex flex-wrap items-center gap-x-5 gap-y-2">
        <span className="font-semibold text-sm">Institutional flows
          <span className="text-dim font-normal text-[11px]"> · NSE cash market</span></span>

        {s.regime && (
          <span className={`font-mono border rounded-full px-2 py-0.5 ${REGIME_STYLE[s.regime] || "border-line2 text-mut"}`}>
            {s.regime}</span>)}

        <span className="font-mono">
          <span className="text-dim">FII </span>
          <span className={cls(s.fii?.net)}>{cr(s.fii?.net)}</span>
          <span className="text-dim"> · {streak(s.fii?.streak ?? 0)} · MTD </span>
          <span className={cls(s.fii?.mtd)}>{cr(s.fii?.mtd)}</span>
        </span>

        <span className="font-mono">
          <span className="text-dim">DII </span>
          <span className={cls(s.dii?.net)}>{cr(s.dii?.net)}</span>
          <span className="text-dim"> · {streak(s.dii?.streak ?? 0)} · MTD </span>
          <span className={cls(s.dii?.mtd)}>{cr(s.dii?.mtd)}</span>
        </span>

        {s.absorption_pct != null && (
          <span className="text-brass font-mono" title="DII buying as a share of FII selling">
            absorption {s.absorption_pct}%</span>)}

        <span className="text-dim font-mono ml-auto">
          {s.as_of} · {s.days}d history
          <button className="ghost !py-0.5 !px-2 ml-2" onClick={refresh} disabled={busy}>
            {busy ? "…" : "↻"}</button>
        </span>
      </div>
      {s.verdict && <p className="text-mut mt-2">{s.verdict}</p>}
    </div>
  );
}
