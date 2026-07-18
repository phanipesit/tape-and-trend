"use client";
import { useEffect, useState } from "react";
import { api, fmt } from "../../lib/api";

export default function Risk() {
  const [syms, setSyms] = useState([]);
  const [f, setF] = useState({ account: 500000, riskPct: 1, entry: "", stop: "", target: "" });
  const [loadSym, setLoadSym] = useState("RELIANCE");
  useEffect(() => { api("/api/symbols").then(setSyms).catch(() => {}); }, []);

  const loadPlan = async () => {
    try {
      const a = await api(`/api/signals/${loadSym}`);
      setF({ ...f, entry: a.entry.toFixed(2), stop: a.stop.toFixed(2), target: a.target.toFixed(2) });
    } catch (e) { alert(e); }
  };
  const set = (k) => (e) => setF({ ...f, [k]: e.target.value });

  const acct = +f.account || 0, riskAmt = acct * (+f.riskPct || 0) / 100;
  const entry = +f.entry, stop = +f.stop, target = +f.target;
  const perShare = entry && stop ? entry - stop : 0;
  const valid = entry > 0 && stop > 0 && perShare > 0;
  const qty = valid ? Math.floor(riskAmt / perShare) : 0;
  const posValue = qty * entry;
  const rr = valid && target > entry ? (target - entry) / perShare : null;
  const pctOfAcct = acct ? (posValue / acct) * 100 : 0;

  return (
    <div className="space-y-4 max-w-3xl">
      <h1 className="text-xl font-bold">Position size & risk calculator</h1>
      <p className="text-mut text-sm">Risk a fixed % of your account per trade. Size comes from the distance to your stop — never from conviction.</p>
      <div className="card space-y-3 text-xs">
        <div className="flex flex-wrap gap-3 items-end">
          <label className="flex flex-col gap-1 text-mut">Account size<input className="w-32" type="number" value={f.account} onChange={set("account")} /></label>
          <label className="flex flex-col gap-1 text-mut">Risk per trade %<input className="w-24" type="number" step="0.25" value={f.riskPct} onChange={set("riskPct")} /></label>
          <span className="text-mut pb-2">→ risking <b className="text-brass font-mono">{fmt(riskAmt, 0)}</b> on this trade</span>
        </div>
        <div className="flex flex-wrap gap-3 items-end border-t border-line pt-3">
          <label className="flex flex-col gap-1 text-mut">Entry<input className="w-28" type="number" step="0.05" value={f.entry} onChange={set("entry")} /></label>
          <label className="flex flex-col gap-1 text-mut">Stop loss<input className="w-28" type="number" step="0.05" value={f.stop} onChange={set("stop")} /></label>
          <label className="flex flex-col gap-1 text-mut">Target<input className="w-28" type="number" step="0.05" value={f.target} onChange={set("target")} /></label>
          <select value={loadSym} onChange={(e) => setLoadSym(e.target.value)}>
            {syms.map((s) => <option key={s.symbol}>{s.symbol}</option>)}</select>
          <button className="ghost" onClick={loadPlan}>Load ATR plan</button>
        </div>
      </div>
      {valid ? (
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
          {[["Shares to buy", qty.toLocaleString("en-IN"), "text-brass"],
            ["Position value", fmt(posValue, 0), ""],
            ["% of account", fmt(pctOfAcct, 1) + "%", pctOfAcct > 25 ? "text-down" : ""],
            ["Risk : Reward", rr ? "1 : " + fmt(rr, 2) : "—", rr && rr >= 2 ? "text-up" : rr ? "text-down" : ""],
            ["Risk per share", fmt(perShare), ""],
            ["Max loss (at stop)", "−" + fmt(qty * perShare, 0), "text-down"],
            ["Gain at target", target > entry ? "+" + fmt(qty * (target - entry), 0) : "—", "text-up"],
          ].map(([k, v, cls]) => (
            <div key={k} className="card">
              <p className="text-[10px] text-dim uppercase tracking-wide">{k}</p>
              <p className={`font-mono text-lg font-semibold ${cls}`}>{v}</p>
            </div>))}
        </div>
      ) : (
        <div className="card text-mut text-sm">Enter an entry and a stop below it (or load a symbol's ATR plan) to see position size.</div>
      )}
      <p className="text-dim text-xs">Rules of thumb: risk ≤ 1–2% per trade, take setups with R:R ≥ 2, and be cautious when one position exceeds ~25% of the account. Educational tool — not investment advice.</p>
    </div>
  );
}
