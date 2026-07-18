"use client";
import { useEffect, useState } from "react";
import Link from "next/link";
import { api, fmt } from "../lib/api";

export default function Dashboard() {
  const [watch, setWatch] = useState([]);
  const [sigs, setSigs] = useState([]);
  const [err, setErr] = useState("");

  const load = () => {
    api("/api/watchlist").then(setWatch).catch((e) => setErr(String(e)));
    api("/api/signals").then(setSigs).catch(() => {});
  };
  useEffect(() => { load(); const t = setInterval(load, 60000); return () => clearInterval(t); }, []);

  return (
    <div className="space-y-4">
      <div>
        <h1 className="text-xl font-bold">Market overview</h1>
        <p className="text-mut text-sm">Watchlist quotes refresh every minute from the cached EOD/latest bar.</p>
      </div>
      {err && <div className="card border-down text-down text-sm">Backend unreachable — is uvicorn running on :8000? {err}</div>}
      <div className="grid md:grid-cols-2 gap-4">
        <div className="card">
          <h2 className="font-semibold mb-2">Watchlist</h2>
          <table className="w-full"><thead><tr><th>SYMBOL</th><th>LAST</th><th>CHG%</th></tr></thead>
            <tbody>{watch.map((q) => (
              <tr key={q.symbol}>
                <td><Link className="font-bold hover:text-brass" href={`/charts?symbol=${q.symbol}`}>{q.symbol}</Link></td>
                <td>{fmt(q.price)}</td>
                <td className={q.pct >= 0 ? "text-up" : "text-down"}>{q.pct >= 0 ? "+" : ""}{fmt(q.pct)}%</td>
              </tr>))}</tbody>
          </table>
        </div>
        <div className="card">
          <h2 className="font-semibold mb-2">Triggered swing setups</h2>
          {sigs.length === 0 && <p className="text-dim text-sm">No rules triggered on the latest bar.</p>}
          {sigs.slice(0, 6).map((a) => (
            <div key={a.symbol} className="flex justify-between items-center py-2 border-b border-line">
              <div>
                <Link className="font-mono font-bold hover:text-brass" href={`/charts?symbol=${a.symbol}`}>{a.symbol}</Link>
                <p className="text-mut text-xs">{a.signals[0].why}</p>
              </div>
              <span className={`text-[11px] font-mono border rounded-full px-2 py-0.5 ${
                a.signals[0].type === "BUY" ? "border-up text-up" :
                a.signals[0].type === "SELL" ? "border-down text-down" : "border-brass text-brass"}`}>
                {a.signals[0].type}</span>
            </div>))}
        </div>
      </div>
      <p className="text-dim text-xs">Educational tool — not investment advice. Signals are mechanical rules; verify everything before trading.</p>
    </div>
  );
}
