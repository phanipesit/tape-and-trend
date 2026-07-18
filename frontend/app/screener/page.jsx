"use client";
import { useEffect, useState, useCallback } from "react";
import Link from "next/link";
import { api, fmt } from "../../lib/api";

export default function Screener() {
  const [f, setF] = useState({ max_pe: 60, min_roe: 0, max_de: 5, rsi_lo: 0, rsi_hi: 100, above_ema50: false, market: "" });
  const [rows, setRows] = useState([]);
  const run = useCallback(() => {
    const p = new URLSearchParams(Object.entries(f).filter(([, v]) => v !== "" && v !== false));
    api(`/api/screener?${p}`).then(setRows).catch(() => {});
  }, [f]);
  useEffect(() => { run(); }, [run]);
  const set = (k) => (e) => setF({ ...f, [k]: e.target.type === "checkbox" ? e.target.checked : e.target.value });

  return (
    <div className="space-y-4">
      <h1 className="text-xl font-bold">Screener</h1>
      <p className="text-mut text-sm">Fundamentals come from yfinance — hit "Refresh all fundamentals" once after setup, then whenever you want fresh ratios.</p>
      <div className="card flex flex-wrap gap-3 items-end text-xs">
        <label className="flex flex-col gap-1 text-mut">Market
          <select value={f.market} onChange={set("market")}><option value="">All</option><option value="IN">India</option><option value="US">US</option></select></label>
        <label className="flex flex-col gap-1 text-mut">Max P/E<input type="number" className="w-20" value={f.max_pe} onChange={set("max_pe")} /></label>
        <label className="flex flex-col gap-1 text-mut">Min ROE %<input type="number" className="w-20" value={f.min_roe} onChange={set("min_roe")} /></label>
        <label className="flex flex-col gap-1 text-mut">Max D/E<input type="number" step="0.1" className="w-20" value={f.max_de} onChange={set("max_de")} /></label>
        <label className="flex flex-col gap-1 text-mut">RSI ≥<input type="number" className="w-16" value={f.rsi_lo} onChange={set("rsi_lo")} /></label>
        <label className="flex flex-col gap-1 text-mut">RSI ≤<input type="number" className="w-16" value={f.rsi_hi} onChange={set("rsi_hi")} /></label>
        <label className="flex items-center gap-2 text-mut pb-1"><input type="checkbox" checked={f.above_ema50} onChange={set("above_ema50")} />Above EMA50</label>
        <button className="ghost" onClick={() => api("/api/fundamentals/refresh-all", { method: "POST" }).then(run)}>↻ Refresh all fundamentals</button>
      </div>
      <div className="card overflow-x-auto">
        <table className="w-full"><thead><tr>
          <th>SYMBOL</th><th>SECTOR</th><th>LAST</th><th>P/E</th><th>ROE%</th><th>D/E</th><th>RSI</th><th>TREND</th>
        </tr></thead><tbody>
          {rows.map((r) => (
            <tr key={r.symbol}>
              <td><Link className="font-bold hover:text-brass" href={`/charts?symbol=${r.symbol}`}>{r.symbol}</Link> <span className="text-dim text-[10px]">{r.market}</span></td>
              <td className="text-mut">{r.sector}</td><td>{fmt(r.close)}</td>
              <td>{fmt(r.pe, 1)}</td>
              <td className={r.roe >= 15 ? "text-up" : ""}>{fmt(r.roe, 1)}</td>
              <td className={r.de > 2 ? "text-down" : ""}>{fmt(r.de, 2)}</td>
              <td className={r.rsi < 32 ? "text-up" : r.rsi > 72 ? "text-down" : ""}>{fmt(r.rsi, 0)}</td>
              <td className={r.trend === "UP" ? "text-up" : "text-down"}>{r.trend}</td>
            </tr>))}
          {rows.length === 0 && <tr><td colSpan={8} className="text-dim">Nothing passes these filters — loosen one, or refresh fundamentals first.</td></tr>}
        </tbody></table>
      </div>
    </div>
  );
}
