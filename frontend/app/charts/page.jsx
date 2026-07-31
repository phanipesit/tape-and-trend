"use client";
import { Suspense, useEffect, useState } from "react";
import { useSearchParams } from "next/navigation";
import TVChart from "../../components/TVChart";
import Md from "../../components/Markdown";
import { api, aiCredit, fmt } from "../../lib/api";

function ChartsInner() {
  const sp = useSearchParams();
  const [symbol, setSymbol] = useState(sp.get("symbol") || "RELIANCE");
  const [syms, setSyms] = useState([]);
  const [a, setA] = useState(null);
  const [f, setF] = useState(null);
  const [ai, setAi] = useState(null);
  const [aiBusy, setAiBusy] = useState(false);

  useEffect(() => { api("/api/symbols").then(setSyms).catch(() => {}); }, []);
  useEffect(() => {
    setA(null); setF(null); setAi(null);
    api(`/api/signals/${symbol}`).then(setA).catch(() => {});
    api("/api/symbols").then((all) => setF(all.find((x) => x.symbol === symbol))).catch(() => {});
  }, [symbol]);

  const runAi = () => {
    setAiBusy(true); setAi(null);
    api(`/api/ai/analyze/${symbol}`)
      .then(setAi)
      .catch((e) => setAi({ error: String(e.message || e) }))
      .finally(() => setAiBusy(false));
  };

  const market = syms.find((x) => x.symbol === symbol)?.market || "IN";

  return (
    <div className="space-y-4">
      <div className="flex items-center gap-3 flex-wrap">
        <h1 className="text-xl font-bold">Charts</h1>
        <select value={symbol} onChange={(e) => setSymbol(e.target.value)}>
          {syms.map((s) => <option key={s.symbol} value={s.symbol}>{s.symbol} · {s.market}</option>)}
        </select>
        <button className="ghost" onClick={() => api(`/api/fundamentals/${symbol}/refresh`, { method: "POST" })
          .then(() => location.reload())
          .catch((e) => alert(`Fundamentals refresh failed: ${e.message}`))}>
          ↻ Refresh fundamentals</button>
      </div>
      <TVChart symbol={symbol} market={market} />
      <div className="grid md:grid-cols-3 gap-4">
        <div className="card text-sm">
          <h3 className="font-semibold mb-2">Fundamentals (yfinance)</h3>
          {f ? <table className="w-full">{[
            ["P/E", f.pe], ["ROE %", f.roe], ["Debt/Equity", f.de],
            ["Rev growth %", f.rev_growth], ["Div yield %", f.div_yield]].map(([k, v]) => (
            <tbody key={k}><tr><td className="text-mut">{k}</td><td className="text-right">{fmt(v)}</td></tr></tbody>))}
          </table> : <p className="text-dim">Loading…</p>}
        </div>
        <div className="card text-sm">
          <h3 className="font-semibold mb-2">Swing plan (ATR-based)</h3>
          {a ? <table className="w-full"><tbody>
            <tr><td className="text-mut">Entry</td><td className="text-right">{fmt(a.entry)}</td></tr>
            <tr><td className="text-mut">Stop 1.5×ATR</td><td className="text-right text-down">{fmt(a.stop)}</td></tr>
            <tr><td className="text-mut">Target 3×ATR</td><td className="text-right text-up">{fmt(a.target)}</td></tr>
            <tr><td className="text-mut">Trend / RSI</td><td className="text-right">{a.trend} · {a.rsi}</td></tr>
          </tbody></table> : <p className="text-dim">Loading…</p>}
        </div>
        <div className="card text-sm">
          <h3 className="font-semibold mb-2">Active signals</h3>
          {a?.signals?.length ? a.signals.map((s, i) => (
            <p key={i} className="py-1 border-b border-line text-mut text-xs">
              <b className={s.type === "BUY" ? "text-up" : s.type === "SELL" ? "text-down" : "text-brass"}>{s.type}</b> — {s.why}</p>))
            : <p className="text-dim">None on the latest bar.</p>}
        </div>
      </div>
      <div className="card text-sm">
        <div className="flex items-center justify-between mb-1">
          <h3 className="font-semibold">✨ AI stock analysis</h3>
          <button className="btn !py-1.5" onClick={runAi} disabled={aiBusy}>
            {aiBusy ? "Analysing…" : ai ? "↻ Re-analyse" : `Analyse ${symbol}`}</button>
        </div>
        {!ai && !aiBusy && <p className="text-dim">One-click read of the chart, signals, fundamentals and news for {symbol}.</p>}
        {aiBusy && <p className="text-dim">Reading candles, indicators, fundamentals and headlines…</p>}
        {ai?.error && <p className="text-down">Analysis failed — is the backend running? {ai.error}</p>}
        {ai?.analysis && (<>
          <p className="text-[10px] text-dim uppercase tracking-wide mb-1">
            {aiCredit(ai)}
            {ai.note ? ` · ${ai.note}` : ""}</p>
          <Md text={ai.analysis} />
        </>)}
      </div>
    </div>
  );
}
export default function Charts() {
  return <Suspense><ChartsInner /></Suspense>;
}
