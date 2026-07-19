"use client";
import { useEffect, useState } from "react";
import Link from "next/link";
import { api, fmt } from "../../lib/api";

export default function Signals() {
  const [rows, setRows] = useState([]);
  const [mkt, setMkt] = useState("");
  useEffect(() => {
    api(`/api/signals${mkt ? `?market=${mkt}` : ""}`).then(setRows).catch(() => {});
  }, [mkt]);
  return (
    <div className="space-y-4">
      <h1 className="text-xl font-bold">Swing signal desk</h1>
      <div className="flex gap-2">
        {[["", "All"], ["IN", "India"], ["US", "United States"]].map(([v, l]) => (
          <button key={v} className={`ghost ${mkt === v ? "on" : ""}`} onClick={() => setMkt(v)}>{l}</button>))}
      </div>
      <div className="grid md:grid-cols-2 gap-4">
        {rows.length === 0 && <p className="text-dim text-sm">No triggered setups right now.</p>}
        {rows.map((a) => (
          <div className="card" key={a.symbol}>
            <div className="flex justify-between">
              <Link className="font-mono font-bold hover:text-brass" href={`/charts?symbol=${a.symbol}`}>{a.symbol}</Link>
              <span className="font-mono">{fmt(a.close)}</span>
            </div>
            {a.signals.map((s, i) => (
              <p key={i} className="text-xs text-mut py-1.5 border-b border-line">
                <b className={s.type === "BUY" ? "text-up" : s.type === "SELL" ? "text-down" : "text-brass"}>{s.type}</b> — {s.why}</p>))}
            <p className="font-mono text-xs mt-2 text-mut">
              {a.direction === "SHORT" && <b className="text-down">SHORT · </b>}
              entry {fmt(a.entry)} · <span className="text-down">stop {fmt(a.stop)}</span> · <span className="text-up">target {fmt(a.target)}</span></p>
          </div>))}
      </div>
    </div>
  );
}
