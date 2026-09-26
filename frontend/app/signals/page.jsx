"use client";
import { useEffect, useState } from "react";
import Link from "next/link";
import { api, edgeLine, fmt, gradeTone } from "../../lib/api";

// Cards arrive ranked by services/playbook.py — graded by what the rule that fired has
// actually earned in this regime, not by the engine's conviction score, which measured
// no predictive value. SKIP setups are still shown: hiding them would hide the rules
// the tracker is still scoring.
export default function Signals() {
  const [rows, setRows] = useState([]);
  const [desk, setDesk] = useState(null);
  const [mkt, setMkt] = useState("");
  const [showSkip, setShowSkip] = useState(false);
  useEffect(() => {
    api(`/api/signals${mkt ? `?market=${mkt}` : ""}`).then(setRows).catch(() => {});
  }, [mkt]);
  useEffect(() => { api("/api/signals/desk").then(setDesk).catch(() => {}); }, []);

  const shown = showSkip ? rows : rows.filter((a) => a.playbook?.grade !== "SKIP");
  const skipped = rows.length - rows.filter((a) => a.playbook?.grade !== "SKIP").length;
  const o = desk?.overall;
  const live = (desk?.rules || []).filter((r) => r.grade === "TRADE" || r.grade === "PAPER");

  return (
    <div className="space-y-4">
      <h1 className="text-xl font-bold">Swing signal desk</h1>
      {desk && (
        <div className="card text-xs space-y-2">
          <p className="text-mut">
            Regime: {Object.entries(desk.regimes).map(([m, r]) => (
              <b key={m} className="font-mono mr-3 text-txt">{m} {r || "unknown"}</b>))}
            {o && o.avg_r != null && (
              <span>System to date: <b className={`font-mono ${o.ci_high < 0 ? "text-down" : o.ci_low > 0 ? "text-up" : "text-txt"}`}>
                {edgeLine(o)}</b> across every rule</span>)}
          </p>
          <p className="text-mut">
            Live in this tape:{" "}
            {live.length === 0 ? <span className="text-dim">no rule has a measured edge — paper only</span>
              : live.map((r) => (
                <span key={`${r.regime}-${r.rule}`} className={`font-mono border rounded-full px-2 py-0.5 mr-1 ${gradeTone(r.grade)}`}>
                  {r.rule} {r.grade}</span>))}
            <Link href="/edge" className="text-brass hover:underline ml-2">full record →</Link>
          </p>
        </div>)}
      <div className="flex gap-2 items-center">
        {[["", "All"], ["IN", "India"], ["US", "United States"]].map(([v, l]) => (
          <button key={v} className={`ghost ${mkt === v ? "on" : ""}`} onClick={() => setMkt(v)}>{l}</button>))}
        {skipped > 0 && (
          <button className={`ghost ml-auto ${showSkip ? "on" : ""}`} onClick={() => setShowSkip(!showSkip)}>
            {showSkip ? "Hide" : "Show"} {skipped} SKIP</button>)}
      </div>
      <div className="grid md:grid-cols-2 gap-4">
        {shown.length === 0 && <p className="text-dim text-sm">No triggered setups right now.</p>}
        {shown.map((a) => {
          const p = a.playbook || {};
          return (
            <div className="card" key={a.symbol}>
              <div className="flex justify-between items-center">
                <Link className="font-mono font-bold hover:text-brass" href={`/charts?symbol=${a.symbol}`}>{a.symbol}</Link>
                <span className="flex items-center gap-2">
                  <span className={`text-[11px] font-mono border rounded-full px-2 py-0.5 ${gradeTone(p.grade)}`}>{p.grade}</span>
                  <span className="font-mono">{fmt(a.close)}</span>
                </span>
              </div>
              <p className="text-dim text-[11px] mt-1">{p.why}{p.regime && ` · ${p.regime}`}</p>
              {a.signals.map((s, i) => (
                <p key={i} className="text-xs text-mut py-1.5 border-b border-line">
                  <b className={s.type === "BUY" ? "text-up" : s.type === "SELL" ? "text-down" : "text-brass"}>{s.type}</b> — {s.why}
                  {s.edge && <span className="block font-mono text-[10px] text-dim">
                    {s.edge.grade} · {edgeLine(s.edge)} · {s.edge.basis}</span>}</p>))}
              {p.rule ? (
                <p className="font-mono text-xs mt-2 text-mut">
                  {p.direction === "SHORT" && <b className="text-down">SHORT · </b>}
                  {p.rule}: entry {fmt(p.entry)} · <span className="text-down">stop {fmt(p.stop)}</span> · <span className="text-up">target {fmt(p.target)}</span>{" "}
                  <Link href={`/risk?symbol=${a.symbol}&entry=${p.entry}&stop=${p.stop}&target=${p.target}`}
                    className="text-brass hover:underline">size it →</Link></p>
              ) : (
                <p className="font-mono text-xs mt-2 text-dim">watch only — no plan</p>)}
              {p.note && <p className="text-[11px] text-brass mt-1">{p.note}</p>}
            </div>);
        })}
      </div>
    </div>
  );
}
