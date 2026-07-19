"use client";
import { useEffect, useState } from "react";
import Link from "next/link";
import { api, fmt } from "../lib/api";

export default function Dashboard() {
  const [watch, setWatch] = useState([]);
  const [sigs, setSigs] = useState([]);
  const [alerts, setAlerts] = useState([]);
  const [err, setErr] = useState("");
  const [add, setAdd] = useState({ symbol: "", market: "IN" });
  const [adding, setAdding] = useState(false);

  const load = () => {
    api("/api/watchlist").then(setWatch).catch((e) => setErr(String(e)));
    api("/api/signals").then((r) => setSigs(r.sort((a, b) => b.score - a.score))).catch(() => {});
    api("/api/alerts").then((r) => setAlerts(r.filter((a) => a.triggered_at))).catch(() => {});
  };
  useEffect(() => { load(); const t = setInterval(load, 60000); return () => clearInterval(t); }, []);

  const addStock = async () => {
    if (!add.symbol.trim()) return;
    setAdding(true);
    try {
      const r = await api("/api/symbols", { method: "POST",
        body: { symbol: add.symbol.trim(), market: add.market, watch: true } });
      alert(`${r.symbol} added — ${r.candles_loaded} days of history loaded.`);
      setAdd({ ...add, symbol: "" }); load();
    } catch (e) { alert(String(e.message || e)); }
    finally { setAdding(false); }
  };
  const unwatch = (s) => api(`/api/watchlist/${s}`, { method: "DELETE" }).then(load);

  return (
    <div className="space-y-4">
      <div>
        <h1 className="text-xl font-bold">Market overview</h1>
        <p className="text-mut text-sm">Watchlist quotes refresh every minute from the cached EOD/latest bar.</p>
      </div>
      {err && <div className="card border-down text-down text-sm">Backend unreachable — is uvicorn running on :8000? {err}</div>}
      {alerts.length > 0 && (
        <div className="card border-brass text-sm">
          <b className="text-brass">🔔 {alerts.length} alert{alerts.length > 1 ? "s" : ""} fired:</b>{" "}
          {alerts.slice(0, 4).map((a) => `${a.symbol} ${a.condition.replace("_", " ")} ${fmt(a.threshold)} (now ${fmt(a.triggered_value)})`).join(" · ")}
          {" — "}<Link href="/alerts" className="text-brass underline">manage</Link>
        </div>)}
      <div className="grid md:grid-cols-2 gap-4">
        <div className="card">
          <h2 className="font-semibold mb-2">Watchlist</h2>
          <table className="w-full"><thead><tr><th>SYMBOL</th><th>LAST</th><th>CHG%</th><th></th></tr></thead>
            <tbody>{watch.map((q) => (
              <tr key={q.symbol}>
                <td><Link className="font-bold hover:text-brass" href={`/charts?symbol=${q.symbol}`}>{q.symbol}</Link></td>
                <td>{fmt(q.price)}</td>
                <td className={q.pct >= 0 ? "text-up" : "text-down"}>{q.pct >= 0 ? "+" : ""}{fmt(q.pct)}%</td>
                <td><button className="ghost !px-2 !py-0.5" title="Remove from watchlist" onClick={() => unwatch(q.symbol)}>✕</button></td>
              </tr>))}</tbody>
          </table>
          <div className="flex gap-2 items-center mt-3 pt-3 border-t border-line text-xs">
            <input className="w-32" placeholder="Add ticker e.g. ZOMATO" value={add.symbol}
              onChange={(e) => setAdd({ ...add, symbol: e.target.value.toUpperCase() })}
              onKeyDown={(e) => e.key === "Enter" && addStock()} />
            <select value={add.market} onChange={(e) => setAdd({ ...add, market: e.target.value })}>
              <option value="IN">India</option><option value="US">US</option></select>
            <button className="btn !py-1.5" onClick={addStock} disabled={adding}>{adding ? "Adding…" : "+ Add stock"}</button>
          </div>
          <p className="text-dim text-[11px] mt-2">Any NSE/BSE or US ticker — validated against Yahoo, then charts, signals, screener and backtests all work on it automatically.</p>
        </div>
        <div className="card">
          <h2 className="font-semibold mb-2">Today's focus <span className="text-dim text-xs font-normal">top 3 by conviction score</span></h2>
          {sigs.length === 0 && <p className="text-dim text-sm">No rules triggered on the latest bar.</p>}
          {sigs.slice(0, 3).map((a) => (
            <div key={a.symbol} className="py-2 border-b border-line">
              <div className="flex justify-between items-center">
                <div>
                  <Link className="font-mono font-bold hover:text-brass" href={`/charts?symbol=${a.symbol}`}>{a.symbol}</Link>
                  <span className="text-dim text-[10px] font-mono ml-2">score {fmt(a.score, 1)} · rvol {fmt(a.rvol, 1)}</span>
                  <p className="text-mut text-xs">{a.signals[0].why}</p>
                </div>
                <span className={`text-[11px] font-mono border rounded-full px-2 py-0.5 ${
                  a.signals[0].type === "BUY" ? "border-up text-up" :
                  a.signals[0].type === "SELL" ? "border-down text-down" : "border-brass text-brass"}`}>
                  {a.signals[0].type}</span>
              </div>
              <p className="font-mono text-[11px] text-dim mt-1">
                {a.direction === "SHORT" && <b className="text-down">SHORT · </b>}
                entry {fmt(a.entry)} · stop {fmt(a.stop)} · target {fmt(a.target)} ·{" "}
                <Link href={`/risk?symbol=${a.symbol}&entry=${a.entry}&stop=${a.stop}&target=${a.target}`}
                  className="text-brass hover:underline">size it →</Link></p>
            </div>))}
          {sigs.length > 3 && <Link href="/signals" className="ghost inline-block mt-2">All {sigs.length} setups →</Link>}
        </div>
      </div>
      <p className="text-dim text-xs">Educational tool — not investment advice. Signals are mechanical rules; verify everything before trading.</p>
    </div>
  );
}
