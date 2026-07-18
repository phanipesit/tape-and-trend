"use client";
import { useEffect, useState } from "react";
import Link from "next/link";
import { PieChart, Pie, Cell, Tooltip, ResponsiveContainer } from "recharts";
import { api, fmt } from "../../lib/api";

const COLORS = ["#F5B942", "#2ED47E", "#4DA3FF", "#A78BFA", "#FF5C5C", "#5EEAD4", "#FB923C", "#E879F9"];
const SETUPS = ["", "EMA cross", "Breakout", "RSI pullback", "MACD flip", "News/event", "Other"];

export default function Portfolio() {
  const [data, setData] = useState({ positions: [], transactions: [], journal: [], stats: { n: 0 }, total_inr: 0, usd_inr: null });
  const [syms, setSyms] = useState([]);
  const [form, setForm] = useState({ symbol: "RELIANCE", side: "BUY", qty: 10, price: "", setup: "", notes: "" });
  const load = () => api("/api/portfolio").then(setData).catch(() => {});
  useEffect(() => { load(); api("/api/symbols").then(setSyms).catch(() => {}); }, []);

  const add = async () => {
    try {
      await api("/api/portfolio/tx", { method: "POST",
        body: { ...form, qty: +form.qty, price: form.price ? +form.price : null } });
      setForm({ ...form, notes: "" }); load();
    } catch (e) { alert(e); }
  };
  const pos = data.positions, st = data.stats || { n: 0 };
  const totalInr = data.total_inr || 0;

  return (
    <div className="space-y-4">
      <div className="flex items-baseline gap-3 flex-wrap">
        <h1 className="text-xl font-bold">Portfolio & journal</h1>
        <span className="font-mono text-lg text-brass">₹{fmt(totalInr, 0)}</span>
        {data.usd_inr && <span className="text-dim text-[11px]">total, USD converted @ ₹{fmt(data.usd_inr, 2)}/$</span>}
      </div>
      <div className="card space-y-2 text-xs">
        <div className="flex flex-wrap gap-3 items-end">
          <select value={form.symbol} onChange={(e) => setForm({ ...form, symbol: e.target.value })}>
            {syms.map((s) => <option key={s.symbol}>{s.symbol}</option>)}</select>
          <select value={form.side} onChange={(e) => setForm({ ...form, side: e.target.value })}>
            <option>BUY</option><option>SELL</option></select>
          <label className="flex flex-col gap-1 text-mut">Qty<input className="w-20" type="number" value={form.qty} onChange={(e) => setForm({ ...form, qty: e.target.value })} /></label>
          <label className="flex flex-col gap-1 text-mut">Price (blank = last)<input className="w-24" type="number" value={form.price} onChange={(e) => setForm({ ...form, price: e.target.value })} /></label>
          <label className="flex flex-col gap-1 text-mut">Setup<select value={form.setup} onChange={(e) => setForm({ ...form, setup: e.target.value })}>
            {SETUPS.map((s) => <option key={s} value={s}>{s || "—"}</option>)}</select></label>
          <button className="btn" onClick={add}>Add trade</button>
        </div>
        <input className="w-full" placeholder="Journal note: why this trade, the plan, or the lesson learned…"
          value={form.notes} onChange={(e) => setForm({ ...form, notes: e.target.value })} />
      </div>

      {st.n > 0 && (
        <div className="grid grid-cols-2 md:grid-cols-6 gap-3">
          {[["Closed trades", st.n, ""], ["Win rate", st.win_rate + "%", st.win_rate >= 50 ? "text-up" : "text-down"],
            ["Avg win", "+" + st.avg_win_pct + "%", "text-up"], ["Avg loss", st.avg_loss_pct + "%", "text-down"],
            ["Expectancy/trade", st.expectancy_pct + "%", st.expectancy_pct >= 0 ? "text-up" : "text-down"],
            ["Best / worst", `+${st.best_pct}% / ${st.worst_pct}%`, ""]].map(([k, v, cls]) => (
            <div key={k} className="card"><p className="text-[10px] text-dim uppercase tracking-wide">{k}</p>
              <p className={`font-mono text-base font-semibold ${cls}`}>{v}</p></div>))}
        </div>)}

      <div className="grid md:grid-cols-3 gap-4">
        <div className="card md:col-span-2 overflow-x-auto">
          <h2 className="font-semibold text-sm mb-2">Open positions</h2>
          <table className="w-full"><thead><tr><th>SYMBOL</th><th>QTY</th><th>AVG</th><th>LAST</th><th>VALUE</th><th>P&L</th><th>P&L%</th></tr></thead><tbody>
            {pos.map((p) => (
              <tr key={p.symbol}>
                <td><Link className="font-bold hover:text-brass" href={`/charts?symbol=${p.symbol}`}>{p.symbol}</Link> <span className="text-dim text-[10px]">{p.market}</span></td>
                <td>{fmt(p.qty, 0)}</td><td>{fmt(p.avg)}</td><td>{fmt(p.last)}</td><td>{fmt(p.value, 0)}</td>
                <td className={p.pnl >= 0 ? "text-up" : "text-down"}>{p.pnl >= 0 ? "+" : ""}{fmt(p.pnl, 0)}</td>
                <td className={p.pnl >= 0 ? "text-up" : "text-down"}>{fmt(p.pnl_pct, 1)}%</td>
              </tr>))}
            {pos.length === 0 && <tr><td colSpan={7} className="text-dim">No open positions.</td></tr>}
          </tbody></table>
        </div>
        <div className="card h-64">
          <p className="text-[10px] text-dim uppercase tracking-wide mb-1">Allocation by value</p>
          {pos.length > 0 && (
            <ResponsiveContainer width="100%" height="90%">
              <PieChart>
                <Pie data={pos} dataKey="value_inr" nameKey="symbol" innerRadius="55%" outerRadius="85%" paddingAngle={2}>
                  {pos.map((_, i) => <Cell key={i} fill={COLORS[i % COLORS.length]} stroke="none" />)}
                </Pie>
                <Tooltip contentStyle={{ background: "#121722", border: "1px solid #2A3448" }}
                  formatter={(v, n) => [`₹${fmt(v, 0)} (${fmt((v / totalInr) * 100, 0)}%)`, n]} />
              </PieChart>
            </ResponsiveContainer>)}
        </div>
      </div>

      <div className="card overflow-x-auto">
        <h2 className="font-semibold text-sm mb-2">Trade journal — closed trades</h2>
        <table className="w-full"><thead><tr>
          <th>DATE</th><th>SYMBOL</th><th>QTY</th><th>AVG IN</th><th>OUT</th><th>P&L</th><th>RET%</th><th>SETUP</th><th>NOTES</th>
        </tr></thead><tbody>
          {(data.journal || []).map((r) => (
            <tr key={r.id}>
              <td className="text-dim">{String(r.traded_at).slice(0, 10)}</td>
              <td className="font-bold">{r.symbol}</td><td>{fmt(r.qty, 0)}</td>
              <td>{fmt(r.avg_in)}</td><td>{fmt(r.out)}</td>
              <td className={r.pnl >= 0 ? "text-up" : "text-down"}>{r.pnl >= 0 ? "+" : ""}{fmt(r.pnl, 0)}</td>
              <td className={r.pnl >= 0 ? "text-up" : "text-down"}>{fmt(r.ret_pct, 1)}</td>
              <td className="text-brass">{r.setup || "—"}</td>
              <td className="text-mut whitespace-normal max-w-xs">{r.notes || "—"}</td>
            </tr>))}
          {(!data.journal || data.journal.length === 0) && <tr><td colSpan={9} className="text-dim">No closed trades yet — journal entries appear when you SELL.</td></tr>}
        </tbody></table>
      </div>
      <p className="text-dim text-xs">Expectancy = win-rate × avg win + loss-rate × avg loss, in % per trade. Positive over 20+ trades means your process has an edge. Educational tool — not investment advice.</p>
    </div>
  );
}
