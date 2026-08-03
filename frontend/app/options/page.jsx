"use client";
import { useEffect, useState, useCallback } from "react";
import { LineChart, Line, XAxis, YAxis, Tooltip, ReferenceLine, ResponsiveContainer } from "recharts";
import Md from "../../components/Markdown";
import { api, aiCredit, fmt } from "../../lib/api";

const r5 = (x) => Math.round(x / 5) * 5;
// Strikes only — premiums come from the backend's Black-Scholes model (/api/options/price),
// priced off the underlying's own realized volatility and the chosen days to expiry.
const STRATS = {
  longcall: { n: "Long call", d: "Bullish. Risk limited to premium; unlimited upside.",
    mk: (S) => [{ type: "call", k: r5(S * 1.02), qty: 1 }] },
  longput: { n: "Long put", d: "Bearish. Risk limited to premium; profits as price falls.",
    mk: (S) => [{ type: "put", k: r5(S * 0.98), qty: 1 }] },
  covcall: { n: "Covered call (synthetic)", d: "Own stock (deep call), sell a call above. Income, capped upside.",
    mk: (S) => [{ type: "call", k: r5(S * 0.8), qty: 1 }, { type: "call", k: r5(S * 1.05), qty: -1 }] },
  bullspread: { n: "Bull call spread", d: "Moderately bullish. Cheaper than a call; risk and reward both capped.",
    mk: (S) => [{ type: "call", k: r5(S), qty: 1 }, { type: "call", k: r5(S * 1.06), qty: -1 }] },
  straddle: { n: "Long straddle", d: "Big move expected, direction unknown. Loses if price stays put.",
    mk: (S) => [{ type: "call", k: r5(S), qty: 1 }, { type: "put", k: r5(S), qty: 1 }] },
  strangle: { n: "Long strangle", d: "Cheaper straddle with wider break-evens.",
    mk: (S) => [{ type: "call", k: r5(S * 1.04), qty: 1 }, { type: "put", k: r5(S * 0.96), qty: 1 }] },
  condor: { n: "Iron condor", d: "Range-bound view. Keep premium if price stays between the short strikes.",
    mk: (S) => [{ type: "put", k: r5(S * 0.9), qty: 1 }, { type: "put", k: r5(S * 0.95), qty: -1 },
                { type: "call", k: r5(S * 1.05), qty: -1 }, { type: "call", k: r5(S * 1.1), qty: 1 }] },
};
const EXPIRIES = [7, 14, 30, 45, 60, 90];

const payoffAt = (S, legs) => legs.reduce((p, L) => {
  const iv = L.type === "call" ? Math.max(S - L.k, 0) : Math.max(L.k - S, 0);
  return p + L.qty * (iv - L.prem);
}, 0);

export default function Options() {
  const [syms, setSyms] = useState([]);
  const [sym, setSym] = useState("RELIANCE");
  const [spot, setSpot] = useState(null);
  const [strat, setStrat] = useState("longcall");
  const [days, setDays] = useState(30);
  const [legs, setLegs] = useState(null);
  const [model, setModel] = useState(null);   // vol + position Greeks from the last pricing call
  const [pricing, setPricing] = useState(false);
  const [priceErr, setPriceErr] = useState(null);
  const [ai, setAi] = useState(null);
  const [aiBusy, setAiBusy] = useState(false);

  // Ask the backend for theoretical premiums + Greeks for these strikes at this expiry.
  // Manual premium edits are deliberately overwritten — that's what "Re-price" means.
  const priceLegs = useCallback((raw, d) => {
    if (!raw?.length) return;
    setPricing(true); setPriceErr(null);
    api("/api/options/price", { method: "POST", body: {
      symbol: sym, days: d,
      legs: raw.map((L) => ({ type: L.type, strike: L.k, qty: L.qty })),
    } })
      .then((res) => {
        setLegs(res.legs.map((L) => ({ type: L.type, k: L.strike, qty: L.qty, prem: L.premium,
                                       delta: L.delta, theta: L.theta, vega: L.vega,
                                       volPct: L.vol_pct, volSrc: L.vol_source,
                                       marketLtp: L.market_ltp })));
        setModel({ vol_pct: res.vol_pct, position: res.position, net_premium: res.net_premium,
                   volSource: res.vol_source, legsImplied: res.legs_implied,
                   legsTotal: res.legs_total, chain: res.chain,
                   expiryMismatch: res.expiry_mismatch });
      })
      .catch((e) => { setPriceErr(String(e.message || e)); setLegs(raw.map((L) => ({ ...L, prem: 0 }))); })
      .finally(() => setPricing(false));
  }, [sym]);

  useEffect(() => { api("/api/symbols?include_index=true").then(setSyms).catch(() => {}); }, []);
  useEffect(() => {
    setSpot(null); setLegs(null); setModel(null); setAi(null);
    api(`/api/quote/${sym}`).then((q) => setSpot(q.price)).catch(() => {});
  }, [sym]);
  // Rebuild + re-price whenever the underlying, strategy, or expiry changes.
  useEffect(() => {
    if (spot) priceLegs(STRATS[strat].mk(spot), days);
    setAi(null);
  }, [spot, strat, days, priceLegs]);

  const setLeg = (i, k) => (e) =>
    setLegs(legs.map((L, j) => (j === i ? { ...L, [k]: +e.target.value } : L)));

  const compute = useCallback(() => {
    if (!spot || !legs || legs.some((L) => L.prem == null)) return null;
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
      days_to_expiry: days,
      vol_pct: model?.vol_pct ?? null,
      greeks: model?.position ?? null,
    } })
      .then(setAi)
      .catch((e) => setAi({ error: String(e.message || e) }))
      .finally(() => setAiBusy(false));
  };

  return (
    <div className="space-y-4">
      <h1 className="text-xl font-bold">Options strategy lab</h1>
      <p className="text-mut text-sm">
        Expiry payoff for preset strategies, Black-Scholes priced. Volatility is{" "}
        <b>live implied vol from NSE&apos;s option chain</b> where that strike is quoted —
        per leg, so a skew survives — and falls back to {sym}&apos;s realized volatility
        where it isn&apos;t. Strikes and premiums stay editable, so paste your broker&apos;s
        real quotes before judging any trade.
      </p>
      <div className="flex gap-3 flex-wrap items-center text-xs">
        <select value={sym} onChange={(e) => setSym(e.target.value)}>
          <optgroup label="Indices">
            {syms.filter((s) => s.symbol.startsWith("^")).map((s) =>
              <option key={s.symbol} value={s.symbol}>{s.name}</option>)}</optgroup>
          <optgroup label="Stocks">
            {syms.filter((s) => !s.symbol.startsWith("^")).map((s) =>
              <option key={s.symbol} value={s.symbol}>{s.symbol}</option>)}</optgroup>
        </select>
        <select value={strat} onChange={(e) => setStrat(e.target.value)}>
          {Object.entries(STRATS).map(([k, v]) => <option key={k} value={k}>{v.n}</option>)}</select>
        <select value={days} onChange={(e) => setDays(+e.target.value)}>
          {EXPIRIES.map((d) => <option key={d} value={d}>{d} days to expiry</option>)}</select>
        <span className="text-mut font-mono">spot {spot ? fmt(spot) : "…"}</span>
        {model && (
          <span className="font-mono" title={
            model.volSource === "implied" ? `Live NSE implied vol, expiry ${model.chain?.expiry}`
            : model.volSource === "mixed" ? `${model.legsImplied}/${model.legsTotal} legs on live IV, the rest on realized vol`
            : "No NSE chain for this symbol — realized vol from cached candles"}>
            <span className={model.volSource === "realized" ? "text-mut" : "text-up"}>
              {model.volSource === "implied" ? "IV" : model.volSource === "mixed"
                ? `IV ${model.legsImplied}/${model.legsTotal}` : "realized"}</span>
            <span className="text-brass"> {model.vol_pct}%</span>
          </span>)}
        <button className="ghost" onClick={() => spot && priceLegs(legs || STRATS[strat].mk(spot), days)}
                disabled={pricing || !spot}>
          {pricing ? "Pricing…" : "↻ Re-price"}</button>
      </div>
      {priceErr && <p className="text-down text-xs">Pricing failed — is the backend running? {priceErr}</p>}
      {/* IV borrowed from a contract expiring at a very different time describes a
          different thing than the one being modelled. Say so rather than quietly use it. */}
      {model?.expiryMismatch && (
        <p className="text-brass text-xs">
          ⚠ Implied vol is from the {model.chain.expiry} chain ({model.chain.expiry_days}d),
          but you are modelling {days}d. Vol is not flat across expiries — treat these
          premiums as indicative and re-check against your broker.
        </p>)}
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
            <table className="w-full"><thead><tr>
              <th>LEG</th><th>STRIKE</th><th>PREMIUM</th><th title="Volatility used for this leg">VOL</th>
              <th title="NSE's last traded price for this strike — the check on the model">NSE LTP</th>
              <th>DELTA</th><th>QTY</th></tr></thead><tbody>
              {legs.map((L, i) => (
                <tr key={i}>
                  <td className={L.qty > 0 ? "text-up" : "text-down"}>{L.qty > 0 ? "Long" : "Short"} {L.type}</td>
                  <td><input className="w-20" type="number" value={L.k} onChange={setLeg(i, "k")} /></td>
                  <td><input className="w-20" type="number" step="0.05" value={L.prem} onChange={setLeg(i, "prem")} /></td>
                  {/* Per-leg vol is the point of the IV feed: an at-the-money number
                      applied to a wing is what priced wings at zero before. */}
                  <td className={`font-mono ${L.volSrc === "implied" ? "text-up" : "text-mut"}`}
                      title={L.volSrc === "implied" ? "Live NSE implied vol for this strike"
                                                    : "Realized vol — this strike isn't quoted"}>
                    {L.volPct == null ? "—" : `${L.volPct}%`}</td>
                  <td className="font-mono text-brass">{L.marketLtp == null ? "—" : fmt(L.marketLtp)}</td>
                  <td className="text-mut font-mono">{L.delta != null ? L.delta.toFixed(2) : "—"}</td>
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
            {model?.position && (
              <table className="w-full"><tbody>
                <tr><td className="text-mut" colSpan={2}>
                  <span className="text-[10px] uppercase tracking-wide text-dim">Position Greeks</span></td></tr>
                <tr><td className="text-mut">Delta <span className="text-dim">per ₹1 move</span></td>
                  <td className="text-right font-mono">{model.position.delta.toFixed(3)}</td></tr>
                <tr><td className="text-mut">Theta <span className="text-dim">per day</span></td>
                  <td className={`text-right font-mono ${model.position.theta < 0 ? "text-down" : "text-up"}`}>
                    {model.position.theta.toFixed(3)}</td></tr>
                <tr><td className="text-mut">Vega <span className="text-dim">per 1% vol</span></td>
                  <td className="text-right font-mono">{model.position.vega.toFixed(3)}</td></tr>
                <tr><td className="text-mut">Gamma</td>
                  <td className="text-right font-mono">{model.position.gamma.toFixed(4)}</td></tr>
              </tbody></table>)}
          </div>
        </div>)}
      {R && legs && (
        <div className="card text-sm">
          <div className="flex items-center justify-between mb-1">
            <h3 className="font-semibold">✨ AI strategy analysis</h3>
            <button className="btn !py-1.5" onClick={runAi} disabled={aiBusy}>
              {aiBusy ? "Analysing…" : ai ? "↻ Re-analyse" : `Analyse this ${STRATS[strat].n.toLowerCase()}`}</button>
          </div>
          {!ai && !aiBusy && <p className="text-dim">Reads {sym}&apos;s trend/signals alongside this strategy&apos;s legs, Greeks and break-evens — does the setup make sense given the current technical picture?</p>}
          {aiBusy && <p className="text-dim">Reading candles, signals and the strategy&apos;s legs…</p>}
          {ai?.error && <p className="text-down">Analysis failed — is the backend running? {ai.error}</p>}
          {ai?.analysis && (<>
            <p className="text-[10px] text-dim uppercase tracking-wide mb-1">
              {aiCredit(ai)}
              {ai.note ? ` · ${ai.note}` : ""}</p>
            <Md text={ai.analysis} />
          </>)}
        </div>)}
      <p className="text-dim text-xs">Per-share payoff at expiry, ignoring lot sizes, margin, and time value before expiry.
        Black-Scholes assumes constant volatility and European exercise, and realized volatility is not implied volatility —
        real quotes will differ. Options carry substantial risk — educational tool, not investment advice.</p>
    </div>
  );
}
