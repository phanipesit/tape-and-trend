"use client";
import { useEffect, useState } from "react";
import { LineChart, Line, XAxis, YAxis, Tooltip, ResponsiveContainer } from "recharts";
import { api, fmt } from "../../lib/api";

export default function Rotation() {
  const [form, setForm] = useState({
    market: "IN", top_n: 20, momentum_days: 90, rebalance_days: 5,
    risk_pct: 0.1, fee_bps: 5, slip_bps: 5,
  });
  const [res, setRes] = useState(null);
  const [busy, setBusy] = useState(false);
  const [hist, setHist] = useState([]);
  const loadHistory = () => api(`/api/rotation/history?market=${form.market}`).then(setHist).catch(() => {});
  useEffect(() => { loadHistory(); }, [form.market]);

  const run = async () => {
    setBusy(true);
    try {
      const { market, ...params } = form;
      const out = await api("/api/rotation", { method: "POST",
        body: { market, params: Object.fromEntries(Object.entries(params).map(([k, v]) => [k, +v])) } });
      setRes(out); loadHistory();
    } catch (e) { alert(e); } finally { setBusy(false); }
  };
  const set = (k) => (e) => setForm({ ...form, [k]: e.target.value });
  const chart = res?.curve?.map((v, i) => ({ i, equity: v }));

  return (
    <div className="space-y-4">
      <h1 className="text-xl font-bold">Momentum rotation</h1>
      <p className="text-mut text-sm">
        Andreas Clenow's "Stocks on the Move": ranks the whole {form.market === "IN" ? "NIFTY" : "US watchlist"} universe
        by risk-adjusted momentum, holds the top N sized by ATR risk-parity, and only opens new
        positions while the market index is above its own 200-day average. Runs entirely off
        cached candles — refresh the universe from the Screener page first if it's stale.
      </p>
      <div className="card flex flex-wrap gap-3 items-end text-xs">
        <label className="flex flex-col gap-1 text-mut">Market
          <select value={form.market} onChange={set("market")}>
            <option value="IN">India (NIFTY 50 + Next 50)</option>
            <option value="US">US (watchlist)</option></select></label>
        <label className="flex flex-col gap-1 text-mut">Top N<input className="w-16" type="number" value={form.top_n} onChange={set("top_n")} /></label>
        <label className="flex flex-col gap-1 text-mut">Momentum days<input className="w-20" type="number" value={form.momentum_days} onChange={set("momentum_days")} /></label>
        <label className="flex flex-col gap-1 text-mut">Rebalance every<input className="w-16" type="number" value={form.rebalance_days} onChange={set("rebalance_days")} /></label>
        <label className="flex flex-col gap-1 text-mut">Risk % / position<input className="w-20" type="number" step="0.05" value={form.risk_pct} onChange={set("risk_pct")} /></label>
        <label className="flex flex-col gap-1 text-mut">Fee bps<input className="w-16" type="number" value={form.fee_bps} onChange={set("fee_bps")} /></label>
        <label className="flex flex-col gap-1 text-mut">Slip bps<input className="w-16" type="number" value={form.slip_bps} onChange={set("slip_bps")} /></label>
        <button className="btn" onClick={run} disabled={busy}>{busy ? "Running…" : "Run rotation backtest"}</button>
      </div>

      {res?.error && <div className="card text-down text-sm">{res.error}</div>}
      {res && !res.error && (<>
        <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-7 gap-3">
          {[["Return", res.total_return + "%", res.total_return >= 0], ["CAGR", res.cagr + "%", res.cagr >= 0],
            ["Index buy & hold", res.buy_hold + "%", null], ["Win rate", res.win_rate + "%", null],
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
          <table className="w-full"><thead><tr><th>#</th><th>SYMBOL</th><th>QTY</th><th>ENTRY</th><th>EXIT</th><th>RET%</th></tr></thead><tbody>
            {res.trades.map((t, i) => (
              <tr key={i}><td className="text-dim">{i + 1}</td><td className="font-bold">{t.symbol}</td>
                <td>{fmt(t.qty, 0)}</td><td>{fmt(t.in)}</td><td>{fmt(t.out)}</td>
                <td className={t.ret >= 0 ? "text-up" : "text-down"}>{fmt(t.ret)}</td></tr>))}
            {res.trades.length === 0 && <tr><td colSpan={6} className="text-dim">No trades — the regime filter may have stayed off the whole window, or nothing ever cleared the eligibility bar.</td></tr>}
          </tbody></table>
        </div></>)}

      {hist.length > 0 && (
        <div className="card overflow-x-auto">
          <h2 className="font-semibold text-sm mb-2">Recent {form.market} runs</h2>
          <table className="w-full"><thead><tr>
            <th>WHEN</th><th>RET%</th><th>CAGR%</th><th>B&H%</th><th>WIN%</th><th>MAXDD%</th><th>SHARPE</th><th>TRADES</th>
          </tr></thead><tbody>
            {hist.map((r) => (
              <tr key={r.id}>
                <td className="text-dim">{String(r.ran_at).slice(0, 16).replace("T", " ")}</td>
                <td className={+r.total_return >= 0 ? "text-up" : "text-down"}>{fmt(r.total_return, 1)}</td>
                <td className={+r.cagr >= 0 ? "text-up" : "text-down"}>{fmt(r.cagr, 1)}</td>
                <td className="text-mut">{fmt(r.buy_hold, 1)}</td>
                <td>{fmt(r.win_rate, 0)}</td>
                <td className="text-down">−{fmt(r.max_drawdown, 1)}</td>
                <td>{fmt(r.sharpe, 2)}</td>
                <td>{r.n_trades}</td>
              </tr>))}
          </tbody></table>
        </div>)}
      <p className="text-dim text-xs">
        A real Nifty 500 backtest of this exact strategy (2006-2020) showed ~27% CAGR, but the
        author didn't correct for survivorship bias, and this app's cache only holds ~2 years of
        history — treat any single run here as directional, not definitive. Educational tool —
        not investment advice.
      </p>
    </div>
  );
}
