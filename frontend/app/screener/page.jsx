"use client";
import { useEffect, useState, useCallback, useRef } from "react";
import Link from "next/link";
import { api, fmt } from "../../lib/api";

export default function Screener() {
  const [f, setF] = useState({ max_pe: 60, min_roe: 0, max_de: 5, rsi_lo: 0, rsi_hi: 100, min_rvol: 0, above_ema50: false, market: "" });
  const [rows, setRows] = useState([]);
  const [loading, setLoading] = useState(true);
  const [err, setErr] = useState("");
  const [watched, setWatched] = useState(new Set());
  const [refreshStatus, setRefreshStatus] = useState(null); // {running, done, total, errors}
  const pollRef = useRef(null);
  const seqRef = useRef(0);
  const run = useCallback(() => {
    const p = new URLSearchParams(Object.entries(f).filter(([, v]) => v !== "" && v !== false));
    const seq = ++seqRef.current;      // ignore out-of-order responses from older requests
    setLoading(true); setErr("");
    api(`/api/screener?${p}`)
      .then((r) => { if (seq === seqRef.current) setRows(r); })
      .catch((e) => { if (seq === seqRef.current) setErr(String(e.message || e)); })
      .finally(() => { if (seq === seqRef.current) setLoading(false); });
  }, [f]);
  const loadWatched = () => api("/api/watchlist").then((r) => setWatched(new Set(r.map((q) => q.symbol)))).catch(() => {});
  useEffect(() => { run(); }, [run]);
  useEffect(() => { loadWatched(); }, []);
  useEffect(() => () => clearInterval(pollRef.current), []);
  const set = (k) => (e) => setF({ ...f, [k]: e.target.type === "checkbox" ? e.target.checked : e.target.value });

  const addToWatchlist = (symbol) =>
    api(`/api/watchlist/${symbol}`, { method: "POST" }).then(() => setWatched((w) => new Set(w).add(symbol)));

  const refreshAll = () => {
    api("/api/fundamentals/refresh-all", { method: "POST" }).then((s) => {
      setRefreshStatus({ running: true, done: 0, total: s.total || 0, errors: {} });
      clearInterval(pollRef.current);
      pollRef.current = setInterval(() => {
        api("/api/fundamentals/refresh-status").then((st) => {
          setRefreshStatus(st);
          if (!st.running) { clearInterval(pollRef.current); run(); }
        }).catch(() => clearInterval(pollRef.current));
      }, 2000);
    }).catch(() => {});
  };

  return (
    <div className="space-y-4">
      <h1 className="text-xl font-bold">Screener</h1>
      <p className="text-mut text-sm">Sorted by conviction score. RVOL = today's volume ÷ 20-day average — above 1.5 means unusual activity.</p>
      <div className="card flex flex-wrap gap-3 items-end text-xs">
        <label className="flex flex-col gap-1 text-mut">Market
          <select value={f.market} onChange={set("market")}><option value="">All</option><option value="IN">India</option><option value="US">US</option></select></label>
        <label className="flex flex-col gap-1 text-mut">Max P/E<input type="number" className="w-20" value={f.max_pe} onChange={set("max_pe")} /></label>
        <label className="flex flex-col gap-1 text-mut">Min ROE %<input type="number" className="w-20" value={f.min_roe} onChange={set("min_roe")} /></label>
        <label className="flex flex-col gap-1 text-mut">Max D/E<input type="number" step="0.1" className="w-20" value={f.max_de} onChange={set("max_de")} /></label>
        <label className="flex flex-col gap-1 text-mut">RSI ≥<input type="number" className="w-16" value={f.rsi_lo} onChange={set("rsi_lo")} /></label>
        <label className="flex flex-col gap-1 text-mut">RSI ≤<input type="number" className="w-16" value={f.rsi_hi} onChange={set("rsi_hi")} /></label>
        <label className="flex flex-col gap-1 text-mut">Min RVOL<input type="number" step="0.1" className="w-16" value={f.min_rvol} onChange={set("min_rvol")} /></label>
        <label className="flex items-center gap-2 text-mut pb-1"><input type="checkbox" checked={f.above_ema50} onChange={set("above_ema50")} />Above EMA50</label>
        <button className="ghost" disabled={refreshStatus?.running} onClick={refreshAll}>
          {refreshStatus?.running ? `↻ Refreshing… ${refreshStatus.done}/${refreshStatus.total}` : "↻ Refresh all fundamentals"}
        </button>
      </div>
      {refreshStatus && !refreshStatus.running && Object.keys(refreshStatus.errors || {}).length > 0 && (
        <div className="card text-xs text-down space-y-1">
          <p className="font-semibold">Fundamentals refresh failed for {Object.keys(refreshStatus.errors).length} symbol(s):</p>
          {Object.entries(refreshStatus.errors).map(([sym, err]) => <p key={sym}>{sym}: {err}</p>)}
        </div>
      )}
      <div className="card overflow-x-auto">
        <table className="w-full"><thead><tr>
          <th>SYMBOL</th><th>SECTOR</th><th>LAST</th><th>P/E</th><th>ROE%</th><th>D/E</th><th>RSI</th><th>RVOL</th><th>TREND</th><th>SCORE</th><th></th>
        </tr></thead><tbody>
          {rows.map((r) => (
            <tr key={r.symbol}>
              <td><Link className="font-bold hover:text-brass" href={`/charts?symbol=${r.symbol}`}>{r.symbol}</Link> <span className="text-dim text-[10px]">{r.market}</span></td>
              <td className="text-mut">{r.sector}</td><td>{fmt(r.close)}</td>
              <td>{fmt(r.pe, 1)}</td>
              <td className={r.roe >= 15 ? "text-up" : ""}>{fmt(r.roe, 1)}</td>
              <td className={r.de > 2 ? "text-down" : ""}>{fmt(r.de, 2)}</td>
              <td className={r.rsi < 32 ? "text-up" : r.rsi > 72 ? "text-down" : ""}>{fmt(r.rsi, 0)}</td>
              <td className={r.rvol >= 1.5 ? "text-brass" : ""}>{fmt(r.rvol, 2)}</td>
              <td className={r.trend === "UP" ? "text-up" : "text-down"}>{r.trend}</td>
              <td className="text-brass">{fmt(r.score, 1)}</td>
              <td className="flex gap-1 text-xs">
                <button className="ghost !px-2 !py-0.5" title={watched.has(r.symbol) ? "Already on watchlist" : "Add to watchlist"}
                  disabled={watched.has(r.symbol)} onClick={() => addToWatchlist(r.symbol)}>
                  {watched.has(r.symbol) ? "★" : "☆"}</button>
                <Link className="ghost !px-2 !py-0.5" title="Set an alert" href={`/alerts?symbol=${r.symbol}`}>🔔</Link>
                <Link className="ghost !px-2 !py-0.5" title="Backtest this" href={`/backtest?symbol=${r.symbol}`}>📊</Link>
              </td>
            </tr>))}
          {loading && rows.length === 0 && <tr><td colSpan={11} className="text-dim">Scanning the universe… (first run can take a while while candles warm up)</td></tr>}
          {err && !loading && <tr><td colSpan={11} className="text-down">Screener request failed — is the backend running on :8000? {err} <button className="ghost !px-2 !py-0.5 ml-2" onClick={run}>Retry</button></td></tr>}
          {!loading && !err && rows.length === 0 && <tr><td colSpan={11} className="text-dim">Nothing passes these filters — loosen one, or refresh fundamentals first.</td></tr>}
        </tbody></table>
      </div>
    </div>
  );
}
