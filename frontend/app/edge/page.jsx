"use client";
import { useEffect, useState } from "react";
import Link from "next/link";
import { api, fmt } from "../../lib/api";

const TAGS = {
  ema_cross_up: "EMA cross ↑", ema_cross_down: "EMA cross ↓",
  rsi_pullback: "RSI pullback", rsi_overbought: "RSI overbought",
  breakout_20d: "20d breakout", breakdown_20d: "20d breakdown",
};
const OUTCOMES = {
  target_hit: ["Target ✓", "text-up"], stop_hit: ["Stopped ✗", "text-down"],
  expired: ["Expired", "text-dim"],
};
const label = (g) => TAGS[g] || g;
const rCls = (v) => (v == null ? "" : v >= 0 ? "text-up" : "text-down");
const rFmt = (v) => (v == null ? "—" : `${v >= 0 ? "+" : ""}${fmt(v, 2)}R`);

function AggTable({ title, hint, rows }) {
  if (!rows?.length) return null;
  return (
    <div className="card overflow-x-auto">
      <h2 className="font-semibold text-sm mb-2">{title} {hint && <span className="text-dim text-xs font-normal">{hint}</span>}</h2>
      <table className="w-full"><thead><tr>
        <th></th><th>DONE</th><th>OPEN</th><th>WIN%</th><th>AVG R</th><th>TOTAL R</th><th>BEST / WORST</th>
      </tr></thead><tbody>
        {rows.map((r) => (
          <tr key={r.grp}>
            <td className="text-brass">{label(r.grp)}</td>
            <td>{r.n}</td>
            <td className="text-dim">{r.open}</td>
            <td className={r.win_pct == null ? "text-dim" : r.win_pct >= 50 ? "text-up" : "text-down"}>
              {r.win_pct == null ? "—" : fmt(r.win_pct, 0) + "%"}</td>
            <td className={rCls(r.avg_r)}>{rFmt(r.avg_r)}</td>
            <td className={rCls(r.total_r)}>{rFmt(r.total_r)}</td>
            <td className="text-dim">{r.best_r == null ? "—" : `${rFmt(r.best_r)} / ${rFmt(r.worst_r)}`}</td>
          </tr>))}
      </tbody></table>
    </div>
  );
}

export default function Edge() {
  const [days, setDays] = useState(90);
  const [d, setD] = useState(null);
  const [err, setErr] = useState("");
  useEffect(() => {
    setErr("");
    api(`/api/performance?days=${days}`).then(setD).catch((e) => setErr(String(e.message || e)));
  }, [days]);

  const done = d?.recent?.filter((r) => r.outcome) || [];
  const totalR = done.reduce((s, r) => s + (Number(r.r_multiple) || 0), 0);

  return (
    <div className="space-y-4">
      <div className="flex items-center gap-3 flex-wrap">
        <h1 className="text-xl font-bold">Your edge</h1>
        <select value={days} onChange={(e) => setDays(+e.target.value)} className="text-xs">
          {[30, 90, 180, 365].map((n) => <option key={n} value={n}>last {n} days</option>)}</select>
      </div>
      <p className="text-mut text-sm">
        Every BUY/SELL rule that fires is logged with its own ATR plan and scored against what price
        actually did next — target or stop hit first, else expired after 20 bars. R is risk-normalised:
        −1R = full stop, +2R = twice the risk. Collection started 19 Jul 2026, so give it a few weeks of
        signals before trusting the percentages.
      </p>
      {err && <div className="card border-down text-down text-sm">Backend unreachable? {err}</div>}
      {d && !d.recent?.length && (
        <div className="card text-dim text-sm">
          No signals logged in this window yet. The tracker snapshots fired signals once a day in the
          background — check back after the next trading day, and see <Link href="/signals" className="text-brass hover:underline">Swing signals</Link> for
          what the engine is watching now.
        </div>)}
      <AggTable title="By setup" hint="which rules actually work" rows={d?.by_setup} />
      <div className="grid md:grid-cols-3 gap-4">
        <AggTable title="By market" rows={d?.by_market} />
        <AggTable title="By direction" rows={d?.by_direction} />
        <AggTable title="By conviction" rows={d?.by_score} />
      </div>
      {d?.recent?.length > 0 && (
        <div className="card overflow-x-auto">
          <h2 className="font-semibold text-sm mb-2">Signal log <span className="text-dim text-xs font-normal">latest 50 · {done.length} scored, {rFmt(totalR)} combined</span></h2>
          <table className="w-full"><thead><tr>
            <th>DATE</th><th>SYMBOL</th><th>SETUP</th><th>DIR</th><th>ENTRY</th><th>STOP</th><th>TARGET</th><th>OUTCOME</th><th>R</th><th>BARS</th>
          </tr></thead><tbody>
            {d.recent.map((r) => {
              const [txt, cls] = OUTCOMES[r.outcome] || ["Open", "text-brass"];
              return (
                <tr key={r.id}>
                  <td className="text-dim">{String(r.signal_date).slice(0, 10)}</td>
                  <td><Link className="font-bold hover:text-brass" href={`/charts?symbol=${r.symbol}`}>{r.symbol}</Link></td>
                  <td className="text-mut">{label(r.setup_tag)}</td>
                  <td className={r.direction === "SHORT" ? "text-down" : "text-up"}>{r.direction}</td>
                  <td>{fmt(r.entry)}</td><td>{fmt(r.stop)}</td><td>{fmt(r.target)}</td>
                  <td className={cls}>{txt}</td>
                  <td className={rCls(r.r_multiple)}>{r.r_multiple == null ? "—" : rFmt(Number(r.r_multiple))}</td>
                  <td className="text-dim">{r.bars_held ?? "—"}</td>
                </tr>);
            })}
          </tbody></table>
        </div>)}
      <p className="text-dim text-xs">Signal outcomes assume mechanical fills at the plan's levels with no slippage. Educational tool — not investment advice.</p>
    </div>
  );
}
