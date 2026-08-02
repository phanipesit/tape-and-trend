"use client";
import { useEffect, useState } from "react";
import { api, fmt } from "../lib/api";

const pctCls = (p) => (p > 0 ? "text-up" : p < 0 ? "text-down" : "text-mut");
const sign = (p) => (p > 0 ? "+" : "");

const STATE_STYLE = {
  OPEN: "text-up border-up",
  LUNCH: "text-brass border-brass",
  CLOSED: "text-dim border-line2",
  WEEKEND: "text-dim border-line2",
};
const REGIME_STYLE = {
  "RISK-ON": "border-up text-up",
  "RISK-OFF": "border-down text-down",
  MIXED: "border-brass text-brass",
};
const VOL_STYLE = { calm: "text-up", elevated: "text-brass", stressed: "text-down" };

// 33540 -> "9h 19m"; short waits stay in minutes so an imminent open reads clearly.
function countdown(secs) {
  if (secs == null) return null;
  const h = Math.floor(secs / 3600);
  const m = Math.floor((secs % 3600) / 60);
  return h > 0 ? `${h}h ${m}m` : `${m}m`;
}

function Row({ r }) {
  return (
    <tr>
      <td className="font-mono">{r.symbol.replace(/^\^/, "")}</td>
      <td className="text-mut truncate max-w-[9rem]" title={r.name}>{r.name}</td>
      <td className="text-right font-mono">{fmt(r.last)}</td>
      <td className={`text-right font-mono ${pctCls(r.pct)}`}>{sign(r.pct)}{fmt(r.pct)}%</td>
      <td className="text-right font-mono text-dim">
        {r.performance_pct?.["1m"] != null
          ? `${sign(r.performance_pct["1m"])}${fmt(r.performance_pct["1m"], 1)}%` : "—"}</td>
      <td className="text-center">
        {r.above_sma200 == null
          ? <span className="text-dim" title="Needs 200 sessions of history">—</span>
          : <span className={r.above_sma200 ? "text-up" : "text-down"}
                  title={`${r.above_sma200 ? "Above" : "Below"} its 200-day average`}>
              {r.above_sma200 ? "▲" : "▼"}</span>}
      </td>
    </tr>
  );
}

export default function GlobalMarkets() {
  const [board, setBoard] = useState(null);
  const [venues, setVenues] = useState([]);
  const [err, setErr] = useState("");
  const [busy, setBusy] = useState(false);

  const load = () => {
    api("/api/markets/board").then(setBoard).catch((e) => setErr(String(e.message || e)));
    api("/api/markets/venues").then(setVenues).catch(() => {});
  };
  useEffect(() => { load(); const t = setInterval(load, 60000); return () => clearInterval(t); }, []);

  const refresh = () => {
    setBusy(true);
    api("/api/markets/refresh", { method: "POST" }).then(load)
      .catch((e) => setErr(String(e.message || e))).finally(() => setBusy(false));
  };

  if (err) return <div className="card border-down text-down text-sm">Global board unavailable — {err}</div>;
  if (!board) return <div className="card text-dim text-sm">Loading global markets…</div>;

  const t = board.trend;
  const homeTz = venues[0]?.home_tz?.split("/").pop() || "local";

  return (
    <div className="space-y-3">
      {/* ---- the one-line read ---- */}
      <div className="card">
        <div className="flex flex-wrap items-center gap-3">
          <span className={`text-xs font-mono border rounded-full px-2.5 py-1 ${REGIME_STYLE[t.regime]}`}>
            {t.regime}</span>
          <span className="text-sm">{t.verdict}.</span>
          <span className="text-dim text-xs font-mono ml-auto">
            close of {board.as_of}
            <button className="ghost !py-0.5 !px-2 ml-2" onClick={refresh} disabled={busy}>
              {busy ? "refreshing…" : "↻"}</button>
          </span>
        </div>
        <div className="flex flex-wrap gap-x-6 gap-y-1 mt-2 text-xs font-mono">
          <span className="text-mut">{t.indices_up}<span className="text-dim">/{t.indices_total} up</span></span>
          <span className="text-mut">{t.above_sma200}<span className="text-dim">/{t.scored} above 200DMA</span></span>
          {t.vix != null && (
            <span className={VOL_STYLE[t.volatility]}>VIX {fmt(t.vix, 1)}
              <span className="text-dim"> · {t.volatility}</span></span>)}
          {t.gold_silver_ratio != null && (
            <span className="text-mut">gold/silver <span className="text-brass">{t.gold_silver_ratio}</span></span>)}
          {t.best && <span className="text-up">↑ {t.best.name} {sign(t.best.pct)}{fmt(t.best.pct)}%</span>}
          {t.worst && <span className="text-down">↓ {t.worst.name} {sign(t.worst.pct)}{fmt(t.worst.pct)}%</span>}
        </div>
      </div>

      <div className="grid lg:grid-cols-3 gap-3">
        {/* ---- indices by region ---- */}
        <div className="card lg:col-span-2 text-xs">
          <h3 className="font-semibold mb-2 text-sm">World indices</h3>
          <table className="w-full">
            <thead><tr>
              <th className="text-left">IDX</th><th className="text-left">NAME</th>
              <th className="text-right">LAST</th><th className="text-right">CHG%</th>
              <th className="text-right">1M</th><th className="text-center">200D</th>
            </tr></thead>
            {board.regions.map((g) => (
              <tbody key={g.region}>
                <tr><td colSpan={6} className="pt-2 text-[10px] tracking-wide text-dim">{g.region}</td></tr>
                {g.rows.map((r) => <Row key={r.symbol} r={r} />)}
              </tbody>))}
          </table>
        </div>

        {/* ---- metals + macro ---- */}
        <div className="card text-xs space-y-3">
          <div>
            <h3 className="font-semibold mb-2 text-sm">Precious metals
              <span className="text-dim font-normal text-[10px] ml-1">USD/oz · front-month futures</span></h3>
            <table className="w-full"><tbody>
              {board.metals.map((r) => (
                <tr key={r.symbol}>
                  <td className="text-mut">{r.name}</td>
                  <td className="text-right font-mono">{fmt(r.last)}</td>
                  <td className={`text-right font-mono ${pctCls(r.pct)}`}>
                    {sign(r.pct)}{fmt(r.pct)}%</td>
                </tr>))}
              {t.gold_silver_ratio != null && (
                <tr className="border-t border-line">
                  <td className="text-dim pt-1">Gold/silver ratio</td>
                  <td colSpan={2} className="text-right font-mono text-brass pt-1">
                    {t.gold_silver_ratio}</td>
                </tr>)}
            </tbody></table>
          </div>
          <div>
            <h3 className="font-semibold mb-2 text-sm">Macro</h3>
            <table className="w-full"><tbody>
              {board.macro.map((r) => (
                <tr key={r.symbol}>
                  <td className="text-mut">{r.name}</td>
                  <td className="text-right font-mono">{fmt(r.last)}</td>
                  <td className={`text-right font-mono ${pctCls(r.pct)}`}>
                    {sign(r.pct)}{fmt(r.pct)}%</td>
                </tr>))}
            </tbody></table>
          </div>
        </div>
      </div>

      {/* ---- session clock, in the user's own timezone ---- */}
      <div className="card text-xs">
        <h3 className="font-semibold mb-2 text-sm">Market sessions
          <span className="text-dim font-normal text-[10px] ml-1">all times {homeTz}</span></h3>
        <div className="grid sm:grid-cols-2 lg:grid-cols-4 gap-2">
          {venues.map((v) => (
            <div key={v.code} className="border border-line rounded p-2">
              <div className="flex items-center justify-between">
                <span className="font-mono">{v.code}</span>
                <span className={`text-[10px] font-mono border rounded-full px-1.5 ${STATE_STYLE[v.state]}`}>
                  {v.state}</span>
              </div>
              <div className="text-dim mt-1 font-mono">{v.session_home}</div>
              <div className="text-mut font-mono">
                {v.state === "OPEN"
                  ? <>closes {v.closes_at_home} <span className="text-dim">· in {countdown(v.closes_in_seconds)}</span></>
                  : <>opens {v.opens_at_home} <span className="text-dim">· in {countdown(v.opens_in_seconds)}</span></>}
              </div>
            </div>))}
        </div>
        <p className="text-dim text-[10px] mt-2">
          No holiday calendar is applied — a venue shut for a public holiday still shows its
          normal session here. Local venue time and DST are handled correctly.
        </p>
      </div>

      {board.missing?.length > 0 && (
        <p className="text-dim text-[11px]">
          No cached history yet for {board.missing.join(", ")} — hit ↻ to load it.</p>)}
    </div>
  );
}
