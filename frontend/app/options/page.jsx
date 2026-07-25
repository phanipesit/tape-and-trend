"use client";
import { useEffect, useState, useCallback } from "react";
import { LineChart, Line, XAxis, YAxis, Tooltip, ReferenceLine, ResponsiveContainer } from "recharts";
import Md from "../../components/Markdown";
import { api, fmt } from "../../lib/api";

const r5 = (x) => Math.round(x / 5) * 5;
const STRATS = {
  longcall: { n: "Long call", d: "Bullish. Risk limited to premium; unlimited upside.",
    mk: (S) => [{ type: "call", k: r5(S * 1.02), qty: 1, prem: +(S * 0.03).toFixed(2) }] },
  longput: { n: "Long put", d: "Bearish. Risk limited to premium; profits as price falls.",
    mk: (S) => [{ type: "put", k: r5(S * 0.98), qty: 1, prem: +(S * 0.03).toFixed(2) }] },
  covcall: { n: "Covered call (synthetic)", d: "Own stock (deep call), sell a call above. Income, capped upside.",
    mk: (S) => [{ type: "call", k: r5(S * 0.8), qty: 1, prem: +(S * 0.21).toFixed(2) },
                { type: "call", k: r5(S * 1.05), qty: -1, prem: +(S * 0.02).toFixed(2) }] },
  bullspread: { n: "Bull call spread", d: "Moderately bullish. Cheaper than a call; risk and reward both capped.",
    mk: (S) => [{ type: "call", k: r5(S), qty: 1, prem: +(S * 0.035).toFixed(2) },
                { type: "call", k: r5(S * 1.06), qty: -1, prem: +(S * 0.015).toFixed(2) }] },
  straddle: { n: "Long straddle", d: "Big move expected, direction unknown. Loses if price stays put.",
    mk: (S) => [{ type: "call", k: r5(S), qty: 1, prem: +(S * 0.03).toFixed(2) },
                { type: "put", k: r5(S), qty: 1, prem: +(S * 0.03).toFixed(2) }] },
  strangle: { n: "Long strangle", d: "Cheaper straddle with wider break-evens.",
    mk: (S) => [{ type: "call", k: r5(S * 1.04), qty: 1, prem: +(S * 0.018).toFixed(2) },
                { type: "put", k: r5(S * 0.96), qty: 1, prem: +(S * 0.018).toFixed(2) }] },
  condor: { n: "Iron condor", d: "Range-bound view. Keep premium if price stays between the short strikes.",
    mk: (S) => [{ type: "put", k: r5(S * 0.9), qty: 1, prem: +(S * 0.008).toFixed(2) },
                { type: "put", k: r5(S * 0.95), qty: -1, prem: +(S * 0.018).toFixed(2) },
                { type: "call", k: r5(S * 1.05), qty: -1, prem: +(S * 0.018).toFixed(2) },
                { type: "call", k: r5(S * 1.1), qty: 1, prem: +(S * 0.008).toFixed(2) }] },
};
const payoffAt = (S, legs) => legs.reduce((p, L) => {
  const iv = L.type === "call" ? Math.max(S - L.k, 0) : Math.max(L.k - S, 0);
  return p + L.qty * (iv - L.prem);
}, 0);

export default function Options() {
  const [syms, setSyms] = useState([]);
  const [sym, setSym] = useState("RELIANCE");
  const [spot, setSpot] = useState(null);
  const [strat, setStrat] = useState("longcall");
  const [legs, setLegs] = useState(null);
  const [ai, setAi] = useState(null);
  const [aiBusy, setAiBusy] = useState(false);

  useEffect(() => { api("/api/symbols?include_index=true").then(setSyms).catch(() => {}); }, []);
  useEffect(() => {
    setSpot(null); setLegs(null); setAi(null);
    api(`/api/quote/${sym}`).then((q) => setSpot(q.price)).catch(() => {});
  }, [sym]);
  useEffect(() => { if (spot && !legs) setLegs(STRATS[strat].mk(spot)); }, [spot, strat, legs]);

  const setLeg = (i, k) => (e) => {
    const v = +e.target.value; const nl = legs.map((L, j) => (j === i ? { ...L, [k]: v } : L));
    setLegs(nl);
  };
  const compute = useCallback(() => {
    if (!spot || !legs) return null;
    const ks = legs.map((l) => l.k);
    const lo = Math.min(spot, ...ks) * 0.8, hi = Math.max(spot, ...ks) * 1.2;
    const pts = [];
    for (let i = 0; i <= 200; i++) {
      const S = lo + ((hi - lo) * i) / 200;
      pts.push({ S: +S.toFixed(2), p: +payoffAt(S, legs).toFixed(2) });
    }
    const bes = [];
    for (let i = 1; i < pts.length; i++)
      if ((pts[i - 1].p < 0 && pts[i].p >= 0) || (pts[i - 1].p > 0 && pts[i].p <= 0)) bes.push(pts[i].S);
    const maxP = Math.max(...pts.map((x) => x.p)), maxL = Math.min(...pts.map((x) => x.p));
    return { pts, bes, maxP, maxL, lo, hi };
  }, [spot, legs]);
  const R = compute();

  const runAi = () => {
    if (!spot || !legs || !R) return;
    setAiBusy(true); setAi(null);
    const netPremium = -legs.reduce((s, L) => s + L.qty * L.prem, 0);
    api("/api/ai/analyze-options", { method: "POST", body: {
      symbol: sym, strategy_name: STRATS[strat].n, strategy_desc: STRATS[strat].d,
      legs: legs.map((L) => ({ type: L.type, strike: L.k, qty: L.qty, premium: L.prem })),
      net_premium: netPremium,
      max_profit: R.maxP > spot * 0.5 ? "Unlimited ↑" : fmt(R.maxP),
      max_loss: R.maxL < -spot * 0.5 ? "Large ↓" : fmt(R.maxL),
      breakevens: R.bes,
    } })
      .then(setAi)
      .catch((e) => setAi({ error: String(e.message || e) }))
      .finally(() => setAiBusy(false));
  };

  return (
    <div className="space-y-4">
      <h1 className="text-xl font-bold">Options strategy lab</h1>
      <p className="text-mut text-sm">Expiry payoff for preset strategies. Premiums are rough placeholders — type in real option-chain quotes from your broker before judging any trade.</p>
      <div className="flex gap-3 flex-wrap items-center text-xs">
        <select value={sym} onChange={(e) => setSym(e.target.value)}>
          <optgroup label="Indices">
            {syms.filter((s) => s.symbol.startsWith("^")).map((s) =>
              <option key={s.symbol} value={s.symbol}>{s.name}</option>)}</optgroup>
          <optgroup label="Stocks">
            {syms.filter((s) => !s.symbol.startsWith("^")).map((s) =>
              <option key={s.symbol} value={s.symbol}>{s.symbol}</option>)}</optgroup>
        </select>
        <select value={strat} onChange={(e) => { setStrat(e.target.value); setLegs(spot ? STRATS[e.target.value].mk(spot) : null); setAi(null); }}>
          {Object.entries(STRATS).map(([k, v]) => <option key={k} value={k}>{v.n}</option>)}</select>
        <span className="text-mut font-mono">spot {spot ? fmt(spot) : "…"}</span>
        <button className="ghost" onClick={() => { setLegs(spot ? STRATS[strat].mk(spot) : null); setAi(null); }}>Reset legs</button>
      </div>
      {R && legs && (
        <div className="grid lg:grid-cols-3 gap-4">
          <div className="card lg:col-span-2 h-96">
            <ResponsiveContainer width="100%" height="100%">
              <LineChart data={R.pts}>
                <XAxis dataKey="S" stroke="#5A6478" fontSize={11} tickFormatter={(v) => fmt(v, 0)} minTickGap={40} />
                <YAxis stroke="#5A6478" fontSize={11} width={70} tickFormatter={(v) => fmt(v, 0)} />
                <Tooltip contentStyle={{ background: "#121722", border: "1px solid #2A3448" }}
                  formatter={(v) => [fmt(v), "P&L at expiry"]} labelFormatter={(l) => "Price " + fmt(l)} />
                <ReferenceLine y={0} stroke="#2A3448" />
                <ReferenceLine x={R.pts.reduce((b, x) => Math.abs(x.S - spot) < Math.abs(b - spot) ? x.S : b, R.pts[0].S)}
                  stroke="#4DA3FF" strokeDasharray="4 4" label={{ value: "spot", fill: "#4DA3FF", fontSize: 10 }} />
                <Line type="monotone" dataKey="p" stroke="#F5B942" dot={false} strokeWidth={2} />
              </LineChart>
            </ResponsiveContainer>
          </div>
          <div className="card text-xs space-y-3">
            <div><b className="text-sm">{STRATS[strat].n}</b>
              <p className="text-mut mt-1">{STRATS[strat].d}</p></div>
            <table className="w-full"><thead><tr><th>LEG</th><th>STRIKE</th><th>PREMIUM</th><th>QTY</th></tr></thead><tbody>
              {legs.map((L, i) => (
                <tr key={i}>
                  <td className={L.qty > 0 ? "text-up" : "text-down"}>{L.qty > 0 ? "Long" : "Short"} {L.type}</td>
                  <td><input className="w-20" type="number" value={L.k} onChange={setLeg(i, "k")} /></td>
                  <td><input className="w-20" type="number" step="0.05" value={L.prem} onChange={setLeg(i, "prem")} /></td>
                  <td>{L.qty > 0 ? "+" : ""}{L.qty}</td>
                </tr>))}
            </tbody></table>
            <table className="w-full"><tbody>
              <tr><td className="text-mut">Max profit</td>
                <td className="text-right text-up font-mono">{R.maxP > spot * 0.5 ? "Unlimited ↑" : fmt(R.maxP)}</td></tr>
              <tr><td className="text-mut">Max loss</td>
                <td className="text-right text-down font-mono">{R.maxL < -spot * 0.5 ? "Large ↓" : fmt(R.maxL)}</td></tr>
              <tr><td className="text-mut">Break-even(s)</td>
                <td className="text-right text-brass font-mono">{R.bes.map((b) => fmt(b, 0)).join(" · ") || "—"}</td></tr>
              <tr><td className="text-mut">Net premium</td>
                <td className="text-right font-mono">{fmt(-legs.reduce((s, L) => s + L.qty * L.prem, 0))}</td></tr>
            </tbody></table>
          </div>
        </div>)}
      {R && legs && (
        <div className="card text-sm">
          <div className="flex items-center justify-between mb-1">
            <h3 className="font-semibold">✨ AI strategy analysis</h3>
            <button className="btn !py-1.5" onClick={runAi} disabled={aiBusy}>
              {aiBusy ? "Analysing…" : ai ? "↻ Re-analyse" : `Analyse this ${STRATS[strat].n.toLowerCase()}`}</button>
          </div>
          {!ai && !aiBusy && <p className="text-dim">Reads {sym}'s trend/signals alongside this strategy's legs and break-evens — does the setup make sense given the current technical picture?</p>}
          {aiBusy && <p className="text-dim">Reading candles, signals and the strategy's legs…</p>}
          {ai?.error && <p className="text-down">Analysis failed — is the backend running? {ai.error}</p>}
          {ai?.analysis && (<>
            <p className="text-[10px] text-dim uppercase tracking-wide mb-1">
              {ai.source === "claude" ? `Powered by Claude (${ai.model})` : "Rule-based analysis — add ANTHROPIC_API_KEY in backend/.env for Claude"}
              {ai.note ? ` · ${ai.note}` : ""}</p>
            <Md text={ai.analysis} />
          </>)}
        </div>)}
      <p className="text-dim text-xs">Per-share payoff at expiry, ignoring lot sizes, margin, and time value before expiry. Options carry substantial risk — educational tool, not investment advice.</p>
    </div>
  );
}
