"use client";
import { useEffect, useState } from "react";
import { api, fmt } from "../lib/api";

// Yield moves are basis points, never percent — services/bonds.py computes them, this
// only renders. Everything shown is a conclusion from the backend, not derived here.
const bpCls = (b) => (b > 0 ? "text-up" : b < 0 ? "text-down" : "text-mut");
const bp = (b) => (b == null ? "—" : `${b > 0 ? "+" : ""}${fmt(b, b % 1 ? 1 : 0)}`);
const SHAPE = { normal: "text-up", flat: "text-brass", inverted: "text-down" };

function Curve({ title, m }) {
  if (!m) return (
    <div className="text-dim">{title}: nothing cached yet — hit ↻.</div>);
  // FBIL's public archive trails by about a week; say so rather than let an old curve
  // read as today's.
  const late = m.lag_days > 3;
  return (
    <div>
      <div className="flex justify-between items-baseline mb-1">
        <span className="font-semibold text-sm">{title}</span>
        <span className={`font-mono text-[10px] ${late ? "text-brass" : "text-dim"}`}
              title={late ? "Source publishes with a delay" : undefined}>
          as of {m.as_of}{late && ` · ${m.lag_days}d old`}</span>
      </div>
      <table className="w-full">
        <thead><tr>
          <th className="text-left">TENOR</th><th className="text-right">YIELD</th>
          <th className="text-right">1D bp</th><th className="text-right">1M bp</th>
        </tr></thead>
        <tbody>
          {m.points.map((p) => (
            <tr key={p.tenor}>
              <td className="font-mono text-mut">{p.label}</td>
              <td className="text-right font-mono">{p.yield == null ? "—" : `${fmt(p.yield)}%`}</td>
              <td className={`text-right font-mono ${bpCls(p.chg_bp)}`}>{bp(p.chg_bp)}</td>
              <td className={`text-right font-mono ${bpCls(p.chg_1m_bp)}`}>{bp(p.chg_1m_bp)}</td>
            </tr>))}
          <tr className="border-t border-line">
            <td className="text-dim pt-1" colSpan={2}>10Y − 3M</td>
            <td className="text-right font-mono pt-1" colSpan={2}>
              {bp(m.slope_10y_3m_bp)}bp <span className={SHAPE[m.curve] || "text-dim"}>{m.curve || ""}</span></td>
          </tr>
        </tbody>
      </table>
      <p className="text-dim text-[10px] mt-1">{m.source}</p>
    </div>
  );
}

export default function Bonds() {
  const [b, setB] = useState(null);
  const [err, setErr] = useState("");
  const [busy, setBusy] = useState(false);

  const load = () => api("/api/bonds").then((r) => { setB(r); setErr(""); })
    .catch((e) => setErr(String(e.message || e)));
  // Curves move once a day; no polling.
  useEffect(() => { load(); }, []);

  const refresh = () => {
    setBusy(true);
    api("/api/bonds/refresh", { method: "POST" }).then(load)
      .catch((e) => setErr(String(e.message || e))).finally(() => setBusy(false));
  };

  if (err) return <div className="card border-down text-down text-sm">Bond yields unavailable — {err}</div>;
  if (!b) return <div className="card text-dim text-sm">Loading bond yields…</div>;

  return (
    <div className="card text-xs">
      <div className="flex flex-wrap items-center gap-3 mb-3">
        <h3 className="font-semibold text-sm">Government bonds</h3>
        <span className="text-mut">{b.verdict}.</span>
        {b.spread_10y_bp != null && (
          <span className="font-mono text-brass" title={`Both 10Y yields on ${b.spread_as_of}`}>
            IN−US 10Y {bp(b.spread_10y_bp)}bp</span>)}
        <button className="ghost !py-0.5 !px-2 ml-auto" onClick={refresh} disabled={busy}>
          {busy ? "refreshing…" : "↻"}</button>
      </div>
      <div className="grid md:grid-cols-2 gap-6">
        <Curve title="India G-Sec" m={b.IN} />
        <Curve title="US Treasury" m={b.US} />
      </div>
    </div>
  );
}
