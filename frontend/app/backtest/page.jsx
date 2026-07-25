"use client";
import { Suspense, useEffect, useState } from "react";
import { useSearchParams } from "next/navigation";
import { LineChart, Line, XAxis, YAxis, Tooltip, ResponsiveContainer } from "recharts";
import { api, fmt } from "../../lib/api";

function BacktestInner() {
  const sp = useSearchParams();
  const [syms, setSyms] = useState([]);
  const [form, setForm] = useState({ symbol: sp.get("symbol") || "TCS", strategy: "emax", fast: 20, slow: 50, buy: 30, sell: 60, rsi2_buy: 5, entry_days: 20, exit_days: 10, fee_bps: 5, slip_bps: 5 });
  const [res, setRes] = useState(null);
  const [busy, setBusy] = useState(false);
  useEffect(() => { api("/api/symbols").then(setSyms).catch(() => {}); }, []);

  const run = async () => {
    setBusy(true);
    try {
      const { symbol, strategy, ...params } = form;
      setRes(await api("/api/backtest", { method: "POST", body: { symbol, strategy, params: Object.fromEntries(Object.entries(params).map(([k, v]) => [k, +v])) } }));
    } catch (e) { alert(e); } finally { setBusy(false); }
  };
  const set = (k) => (e) => setForm({ ...form, [k]: e.target.value });
  const chart = res?.curve?.map((v, i) => ({ i, equity: v }));

  return (
    <div className="space-y-4">
      <h1 className="text-xl font-bold">Backtester</h1>
      <p className="text-mut text-sm">Runs on real cached daily bars with commission + slippage (bps per side). Results are saved to <code>backtest_runs</code> in Postgres.</p>
      <div className="card flex flex-wrap gap-3 items-end text-xs">
        <select value={form.symbol} onChange={set("symbol")}>{syms.map((s) => <option key={s.symbol}>{s.symbol}</option>)}</select>
        <select value={form.strategy} onChange={set("strategy")}>
          <option value="emax">EMA crossover</option><option value="rsi">RSI mean reversion</option><option value="macd">MACD flip</option>
          <option value="signal">Live signal engine</option>
          <option value="rsi2">RSI(2) mean reversion</option><option value="donchian">Donchian breakout (Turtle)</option></select>
        {form.strategy === "emax" && <>
          <label className="flex flex-col gap-1 text-mut">Fast<input className="w-16" type="number" value={form.fast} onChange={set("fast")} /></label>
          <label className="flex flex-col gap-1 text-mut">Slow<input className="w-16" type="number" value={form.slow} onChange={set("slow")} /></label></>}
        {form.strategy === "rsi" && <>
          <label className="flex flex-col gap-1 text-mut">Buy&lt;<input className="w-16" type="number" value={form.buy} onChange={set("buy")} /></label>
          <label className="flex flex-col gap-1 text-mut">Sell&gt;<input className="w-16" type="number" value={form.sell} onChange={set("sell")} /></label></>}
        {form.strategy === "rsi2" && <>
          <label className="flex flex-col gap-1 text-mut">RSI(2) buy&lt;<input className="w-16" type="number" value={form.rsi2_buy} onChange={set("rsi2_buy")} /></label>
          <span className="text-dim pb-2">only long above 200-day SMA · exits above 5-day SMA</span></>}
        {form.strategy === "donchian" && <>
          <label className="flex flex-col gap-1 text-mut">Entry days<input className="w-16" type="number" value={form.entry_days} onChange={set("entry_days")} /></label>
          <label className="flex flex-col gap-1 text-mut">Exit days<input className="w-16" type="number" value={form.exit_days} onChange={set("exit_days")} /></label></>}
        <label className="flex flex-col gap-1 text-mut">Fee bps<input className="w-16" type="number" value={form.fee_bps} onChange={set("fee_bps")} /></label>
        <label className="flex flex-col gap-1 text-mut">Slip bps<input className="w-16" type="number" value={form.slip_bps} onChange={set("slip_bps")} /></label>
        <button className="btn" onClick={run} disabled={busy}>{busy ? "Running…" : "Run backtest"}</button>
      </div>
      {res && !res.error && (<>
        <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-7 gap-3">
          {[["Return", res.total_return + "%", res.total_return >= 0], ["CAGR", res.cagr + "%", res.cagr >= 0],
            ["Buy & hold", res.buy_hold + "%", null], ["Win rate", res.win_rate + "%", null],
            ["Max DD", "−" + res.max_drawdown + "%", false], ["Sharpe", res.sharpe, null],
            ["Trades", res.n_trades, null]].map(([k, v, up]) => (
            <div key={k} className="card">
              <p className="text-[10px] text-dim uppercase tracking-wide">{k}</p>
              <p className={`font-mono text-lg font-semibold ${up === true ? "text-up" : up === false ? "text-down" : ""}`}>{v}</p>
            </div>))}
        </div>
        <div className="card h-72">
          <ResponsiveContainer width="100%" height="100%">
            <LineChart data={chart}>
              <XAxis dataKey="i" hide /><YAxis stroke="#5A6478" fontSize={11} domain={["auto", "auto"]} width={70} />
              <Tooltip contentStyle={{ background: "#121722", border: "1px solid #2A3448" }} formatter={(v) => fmt(v, 0)} />
              <Line type="monotone" dataKey="equity" stroke="#F5B942" dot={false} strokeWidth={1.6} />
            </LineChart>
          </ResponsiveContainer>
        </div>
        <div className="card max-h-64 overflow-auto">
          <table className="w-full"><thead><tr><th>#</th><th>ENTRY</th><th>EXIT</th><th>RET%</th></tr></thead><tbody>
            {res.trades.map((t, i) => (
              <tr key={i}><td className="text-dim">{i + 1}</td><td>{fmt(t.in)}</td><td>{fmt(t.out)}</td>
                <td className={t.ret >= 0 ? "text-up" : "text-down"}>{fmt(t.ret)}</td></tr>))}
          </tbody></table>
        </div></>)}
      {res?.error && <div className="card text-down text-sm">{res.error}</div>}
    </div>
  );
}
export default function Backtest() {
  return <Suspense><BacktestInner /></Suspense>;
}
