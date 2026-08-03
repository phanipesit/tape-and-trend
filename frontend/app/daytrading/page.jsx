"use client";
import { useEffect, useState } from "react";
import Link from "next/link";
import IntradayChart from "../../components/IntradayChart";
import { api, fmt } from "../../lib/api";

const INTERVALS = ["1m", "5m", "15m"];

export default function DayTrading() {
  const [syms, setSyms] = useState([]);
  const [symbol, setSymbol] = useState("RELIANCE");
  const [interval, setIntervalStr] = useState("5m");
  const [a, setA] = useState(null);
  const [err, setErr] = useState("");

  useEffect(() => { api("/api/symbols?include_index=true").then(setSyms).catch(() => {}); }, []);
  useEffect(() => {
    setA(null); setErr("");
    const load = () => api(`/api/intraday/signals/${symbol}?interval=${interval}`)
      .then(setA).catch((e) => setErr(String(e.message || e)));
    load();
    const t = setInterval(load, 60000);
    return () => clearInterval(t);
  }, [symbol, interval]);

  return (
    <div className="space-y-4">
      <div className="flex items-center gap-3 flex-wrap">
        <h1 className="text-xl font-bold">Day trading</h1>
        <select value={symbol} onChange={(e) => setSymbol(e.target.value)}>
          <optgroup label="Indices">
            {syms.filter((s) => s.symbol.startsWith("^")).map((s) =>
              <option key={s.symbol} value={s.symbol}>{s.name}</option>)}</optgroup>
          <optgroup label="Stocks">
            {syms.filter((s) => !s.symbol.startsWith("^")).map((s) =>
              <option key={s.symbol} value={s.symbol}>{s.symbol} · {s.market}</option>)}</optgroup>
        </select>
        <select value={interval} onChange={(e) => setIntervalStr(e.target.value)}>
          {INTERVALS.map((iv) => <option key={iv} value={iv}>{iv} bars</option>)}
        </select>
      </div>
      <p className="text-mut text-sm">
        VWAP, opening-range breakout and fast EMA/RSI — tools for intraday moves, not the
        swing-timeframe indicators used elsewhere in this app. Refreshes every 60s while
        this page is open. The chart is drawn from our own cached bars, so it shows exactly
        what the signals below are computed from — for a full TradingView chart, see{" "}
        <Link href={`/charts?symbol=${symbol}`} className="text-brass hover:underline">Charts</Link>.
      </p>
      <IntradayChart symbol={symbol} interval={interval} />

      {err && <div className="card border-down text-down text-sm">Backend unreachable — is uvicorn running on :8000? {err}</div>}
      {a?.error && <div className="card text-down text-sm">{a.error}</div>}
      {/* A dead feed used to be invisible here: the last good bar kept being scored and
          rendered as if live. Never hide this behind a subtle tint. */}
      {a?.stale && (
        <div className="card border-down text-down text-sm">
          ⚠ Stale feed — the last bar is {fmt(a.bar_age_minutes, 0)} minutes old while the
          market is open. Everything below is computed from that bar and is <b>not</b> a
          live read. Check the data feed for {a.symbol} before acting on it.
        </div>)}
      {a && !a.error && (
        <div className="grid md:grid-cols-3 gap-4">
          <div className="card text-sm">
            <h3 className="font-semibold mb-2">Intraday levels{" "}
              <span className="text-dim text-xs font-normal font-mono">
                {a.bar_age_minutes == null ? "" :
                  `last bar ${fmt(a.bar_age_minutes, 0)}m ago`}
                {a.venue_open === false && " · market shut"}</span></h3>
            <table className="w-full"><tbody>
              <tr><td className="text-mut">VWAP</td><td className="text-right">{a.vwap == null ? "— (no volume data)" : fmt(a.vwap)}</td></tr>
              <tr><td className="text-mut">Opening range high</td><td className="text-right">{fmt(a.or_hi)}</td></tr>
              <tr><td className="text-mut">Opening range low</td><td className="text-right">{fmt(a.or_lo)}</td></tr>
              <tr><td className="text-mut">EMA9 / EMA20</td><td className="text-right">{fmt(a.ema9)} / {fmt(a.ema20)}</td></tr>
              <tr><td className="text-mut">RSI(7)</td><td className="text-right">{fmt(a.rsi7, 0)}</td></tr>
              <tr><td className="text-mut">RVOL</td><td className="text-right">{fmt(a.rvol, 2)}×</td></tr>
            </tbody></table>
          </div>
          <div className="card text-sm">
            <h3 className="font-semibold mb-2">Intraday plan (ATR-based)</h3>
            <table className="w-full"><tbody>
              <tr><td className="text-mut">Entry</td><td className="text-right">{fmt(a.entry)}</td></tr>
              <tr><td className="text-mut">Stop 1×ATR</td><td className="text-right text-down">{fmt(a.stop)}</td></tr>
              <tr><td className="text-mut">Target 2×ATR</td><td className="text-right text-up">{fmt(a.target)}</td></tr>
              <tr><td className="text-mut">Direction · score</td><td className="text-right">{a.direction} · {fmt(a.score, 1)}</td></tr>
            </tbody></table>
          </div>
          <div className="card text-sm">
            <h3 className="font-semibold mb-2">Active signals</h3>
            {a.signals?.length ? a.signals.map((s, i) => (
              <p key={i} className="py-1 border-b border-line text-mut text-xs">
                <b className={s.type === "BUY" ? "text-up" : s.type === "SELL" ? "text-down" : "text-brass"}>{s.type}</b> — {s.why}</p>))
              : <p className="text-dim">None on the latest bar.</p>}
          </div>
        </div>)}
      <p className="text-dim text-xs">Index symbols report no intraday volume from Yahoo, so VWAP and volume-gated signals won't fire for them. Educational tool — not investment advice.</p>
    </div>
  );
}
