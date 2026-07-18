"use client";
import { Suspense, useEffect, useState } from "react";
import { useSearchParams } from "next/navigation";
import { api, fmt } from "../../lib/api";

const CONDS = [
  ["price_above", "Price above"], ["price_below", "Price below"],
  ["rsi_above", "RSI above"], ["rsi_below", "RSI below"],
];

function AlertsInner() {
  const sp = useSearchParams();
  const [syms, setSyms] = useState([]);
  const [rows, setRows] = useState([]);
  const [f, setF] = useState({ symbol: sp.get("symbol") || "RELIANCE", condition: "price_above", threshold: "" });
  const [busy, setBusy] = useState(false);
  const load = () => api("/api/alerts").then(setRows).catch(() => {});
  useEffect(() => { load(); api("/api/symbols").then(setSyms).catch(() => {}); }, []);

  const add = async () => {
    if (!f.threshold) return alert("Enter a threshold value");
    await api("/api/alerts", { method: "POST", body: { ...f, threshold: +f.threshold } });
    setF({ ...f, threshold: "" }); load();
  };
  const checkNow = async () => {
    setBusy(true);
    try { const r = await api("/api/alerts/check", { method: "POST" });
      alert(r.fired.length ? `${r.fired.length} alert(s) fired!` : "No alerts triggered."); load();
    } finally { setBusy(false); }
  };

  return (
    <div className="space-y-4">
      <h1 className="text-xl font-bold">Alerts</h1>
      <p className="text-mut text-sm">Checked automatically every 5 minutes while the backend runs, against the latest cached bar. Use "Check now" to force a pass.</p>
      <div className="card flex flex-wrap gap-3 items-end text-xs">
        <select value={f.symbol} onChange={(e) => setF({ ...f, symbol: e.target.value })}>
          {syms.map((s) => <option key={s.symbol}>{s.symbol}</option>)}</select>
        <select value={f.condition} onChange={(e) => setF({ ...f, condition: e.target.value })}>
          {CONDS.map(([v, l]) => <option key={v} value={v}>{l}</option>)}</select>
        <label className="flex flex-col gap-1 text-mut">Threshold<input className="w-28" type="number" step="0.05" value={f.threshold} onChange={(e) => setF({ ...f, threshold: e.target.value })} /></label>
        <button className="btn" onClick={add}>Create alert</button>
        <button className="ghost" onClick={checkNow} disabled={busy}>{busy ? "Checking…" : "Check now"}</button>
      </div>
      <div className="card overflow-x-auto">
        <table className="w-full"><thead><tr>
          <th>SYMBOL</th><th>CONDITION</th><th>THRESHOLD</th><th>STATUS</th><th>VALUE AT TRIGGER</th><th></th>
        </tr></thead><tbody>
          {rows.map((a) => (
            <tr key={a.id}>
              <td className="font-bold">{a.symbol}</td>
              <td className="text-mut">{CONDS.find(([v]) => v === a.condition)?.[1]}</td>
              <td>{fmt(a.threshold)}</td>
              <td>{a.triggered_at
                ? <span className="text-up">● Fired</span>
                : <span className="text-brass">◐ Watching</span>}</td>
              <td>{a.triggered_value ? fmt(a.triggered_value) : "—"}</td>
              <td className="flex gap-2">
                {a.triggered_at && <button className="ghost" onClick={() => api(`/api/alerts/${a.id}/reset`, { method: "POST" }).then(load)}>Re-arm</button>}
                <button className="ghost" onClick={() => api(`/api/alerts/${a.id}`, { method: "DELETE" }).then(load)}>✕</button>
              </td>
            </tr>))}
          {rows.length === 0 && <tr><td colSpan={6} className="text-dim">No alerts yet — create one above (e.g. RELIANCE · Price above · 1400).</td></tr>}
        </tbody></table>
      </div>
    </div>
  );
}
export default function Alerts() {
  return <Suspense><AlertsInner /></Suspense>;
}
