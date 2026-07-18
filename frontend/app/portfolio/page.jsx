"use client";
import { useEffect, useState } from "react";
import Link from "next/link";
import { PieChart, Pie, Cell, Tooltip, ResponsiveContainer } from "recharts";
import { api, fmt } from "../../lib/api";

const COLORS = ["#F5B942", "#2ED47E", "#4DA3FF", "#A78BFA", "#FF5C5C", "#5EEAD4", "#FB923C", "#E879F9"];

export default function Portfolio() {
  const [data, setData] = useState({ positions: [], transactions: [] });
  const [syms, setSyms] = useState([]);
  const [form, setForm] = useState({ symbol: "RELIANCE", side: "BUY", qty: 10, price: "" });
  const load = () => api("/api/portfolio").then(setData).catch(() => {});
  useEffect(() => { load(); api("/api/symbols").then(setSyms).catch(() => {}); }, []);

  const add = async () => {
    try {
      await api("/api/portfolio/tx", { method: "POST",
        body: { ...form, qty: +form.qty, price: form.price ? +form.price : null } });
      load();
    } catch (e) { alert(e); }
  };
  const pos = data.positions;
  const total = pos.reduce((s, p) => s + p.value, 0);

  return (
    <div className="space-y-4">
      <h1 className="text-xl font-bold">Portfolio</h1>
      <div className="card flex flex-wrap gap-3 items-end text-xs">
        <select value={form.symbol} onChange={(e) => setForm({ ...form, symbol: e.target.value })}>
          {syms.map((s) => <option key={s.symbol}>{s.symbol}</option>)}</select>
        <select value={form.side} onChange={(e) => setForm({ ...form, side: e.target.value })}>
          <option>BUY</option><option>SELL</option></select>
        <label className="flex flex-col gap-1 text-mut">Qty<input className="w-20" type="number" value={form.qty} onChange={(e) => setForm({ ...form, qty: e.target.value })} /></label>
        <label className="flex flex-col gap-1 text-mut">Price (blank = last)<input className="w-24" type="number" value={form.price} onChange={(e) => setForm({ ...form, price: e.target.value })} /></label>
        <button className="btn" onClick={add}>Add trade</button>
      </div>
      <div className="grid md:grid-cols-3 gap-4">
        <div className="card md:col-span-2 overflow-x-auto">
          <table className="w-full"><thead><tr><th>SYMBOL</th><th>QTY</th><th>AVG</th><th>LAST</th><th>VALUE</th><th>P&L</th><th>P&L%</th></tr></thead><tbody>
            {pos.map((p) => (
              <tr key={p.symbol}>
                <td><Link className="font-bold hover:text-brass" href={`/charts?symbol=${p.symbol}`}>{p.symbol}</Link> <span className="text-dim text-[10px]">{p.market}</span></td>
                <td>{fmt(p.qty, 0)}</td><td>{fmt(p.avg)}</td><td>{fmt(p.last)}</td><td>{fmt(p.value, 0)}</td>
                <td className={p.pnl >= 0 ? "text-up" : "text-down"}>{p.pnl >= 0 ? "+" : ""}{fmt(p.pnl, 0)}</td>
                <td className={p.pnl >= 0 ? "text-up" : "text-down"}>{fmt(p.pnl_pct, 1)}%</td>
              </tr>))}
            {pos.length === 0 && <tr><td colSpan={7} className="text-dim">No open positions — log your first trade above.</td></tr>}
          </tbody></table>
        </div>
        <div className="card h-64">
          <p className="text-[10px] text-dim uppercase tracking-wide mb-1">Allocation by value</p>
          {pos.length > 0 && (
            <ResponsiveContainer width="100%" height="90%">
              <PieChart>
                <Pie data={pos} dataKey="value" nameKey="symbol" innerRadius="55%" outerRadius="85%" paddingAngle={2}>
                  {pos.map((_, i) => <Cell key={i} fill={COLORS[i % COLORS.length]} stroke="none" />)}
                </Pie>
                <Tooltip contentStyle={{ background: "#121722", border: "1px solid #2A3448" }}
                  formatter={(v, n) => [`${fmt(v, 0)} (${fmt((v / total) * 100, 0)}%)`, n]} />
              </PieChart>
            </ResponsiveContainer>)}
        </div>
      </div>
      <p className="text-dim text-xs">Note: values mix ₹ and $ books at face value — add an FX conversion in the backend if you want a single base currency.</p>
    </div>
  );
}
