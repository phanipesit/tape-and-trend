"use client";
import { useEffect, useState } from "react";
import Link from "next/link";
import { api, fmt } from "../../lib/api";

const pct = (v, dp = 1) => (v == null ? "—" : `${v > 0 ? "+" : ""}${fmt(v * 100, dp)}%`);
const cls = (v) => (v == null ? "text-dim" : v > 0 ? "text-up" : v < 0 ? "text-down" : "text-mut");

// Breadth is what separates "the theme is moving" from "two names are moving".
function Breadth({ v }) {
  if (v == null) return <span className="text-dim">—</span>;
  return (
    <span className="inline-flex items-center gap-1.5">
      <span className="w-12 h-1.5 bg-line rounded overflow-hidden inline-block">
        <span className="h-full bg-brass block" style={{ width: `${v * 100}%` }} />
      </span>
      <span className="text-dim">{fmt(v * 100, 0)}%</span>
    </span>);
}

function Theme({ t, open, onToggle }) {
  return (
    <>
      <tr className="cursor-pointer hover:bg-panel2" onClick={onToggle}>
        <td className="font-mono">
          <span className="text-dim mr-1">{open ? "▾" : "▸"}</span>
          <span className={t.theme.includes("AI") ? "text-brass font-bold" : ""}>{t.theme}</span>
        </td>
        <td className="text-right text-dim">{t.n}</td>
        <td className="text-right font-mono text-mut">{pct(t.cagr_3y)}</td>
        <td className="text-right font-mono">{pct(t.growth_1y)}</td>
        <td className={`text-right font-mono font-bold ${cls(t.accel)}`}>{pct(t.accel)}</td>
        <td className="text-center"><Breadth v={t.breadth} /></td>
        <td className={`text-right font-mono ${cls(t.margin_change)}`}>{pct(t.margin_change, 2)}</td>
      </tr>
      {open && (
        <tr><td colSpan={7} className="bg-panel2 px-4 py-2">
          <table className="w-full text-[11px]"><tbody>
            {t.members.map((m) => (
              <tr key={m.symbol}>
                <td className="font-mono w-28">
                  <Link href={`/charts?symbol=${m.symbol}`}
                    className="hover:text-brass">{m.symbol}</Link></td>
                <td className="text-mut w-52 truncate">{m.name}</td>
                <td className="text-right font-mono w-20 text-mut">{pct(m.cagr_3y)}</td>
                <td className="text-right font-mono w-20">{pct(m.growth_1y)}</td>
                <td className={`text-right font-mono w-20 ${cls(m.accel)}`}>{pct(m.accel)}</td>
                <td className={`text-right font-mono w-20 ${cls(m.margin_change)}`}>
                  {pct(m.margin_change, 2)}</td>
                <td className="text-dim pl-3">FY{m.latest_year}</td>
              </tr>))}
          </tbody></table>
        </td></tr>)}
    </>
  );
}

export default function Themes() {
  const [d, setD] = useState(null);
  const [err, setErr] = useState("");
  const [market, setMarket] = useState("");
  const [open, setOpen] = useState(null);

  useEffect(() => {
    setD(null); setErr("");
    api(`/api/themes${market ? `?market=${market}` : ""}`)
      .then(setD).catch((e) => setErr(String(e.message || e)));
  }, [market]);

  const tab = (on) => `px-2.5 py-1 rounded text-xs font-mono border ${
    on ? "border-brass text-brass bg-panel2" : "border-line text-mut hover:text-txt"}`;

  return (
    <div className="space-y-4">
      <div>
        <h1 className="text-xl font-bold">Theme tracker</h1>
        <p className="text-mut text-sm">
          Revenue <b>acceleration</b> — each company&apos;s latest year against its own
          3-year trend. A business compounding 20% for a decade is a good business but not
          news; one jumping to 33% against a 20% trend is a change in the world showing up
          in the accounts.
        </p>
      </div>

      <div className="card border-line2 text-xs text-mut">
        <b className="text-txt">On time, not early.</b> This is the same revenue line every
        institution reads the same day — it is not privileged information. What it does is
        show diffusion landing in the accounts before the market has finished repricing it,
        which is observable; predicting the repricing is not.
        <br /><br />
        <b className="text-txt">No expectancy here either.</b> Scoring whether these
        inflections predict returns needs years of price history against a database holding
        two. Like <Link href="/quality" className="text-brass hover:underline">Quality</Link>,
        this describes what businesses are doing, not what their shares will do. Margin
        direction sits beside growth on purpose: revenue accelerating while margins fall is
        a company <i>buying</i> growth, which a headline number alone cannot distinguish.
      </div>

      {err && <div className="card border-down text-down text-sm">{err}</div>}

      <div className="card flex flex-wrap gap-2 items-center">
        {[["", "All"], ["IN", "India"], ["US", "US"]].map(([k, label]) => (
          <button key={k || "all"} className={tab(market === k)}
            onClick={() => setMarket(k)}>{label}</button>))}
        <span className="text-dim text-[11px] ml-auto">
          {d ? `${d.companies} companies · themes need ${d.min_members}+ members` : ""}
          {" · click a theme for its constituents"}
        </span>
      </div>

      {!d && !err && <div className="card text-dim text-sm">Loading…</div>}

      {d?.themes?.length > 0 && (
        <div className="card text-xs">
          <table className="w-full"><thead><tr>
            <th className="text-left">THEME</th><th className="text-right">N</th>
            <th className="text-right">3Y CAGR</th><th className="text-right">LATEST</th>
            <th className="text-right" title="Latest year minus the 3-year trend">ACCEL</th>
            <th className="text-center" title="Share of members accelerating — is the whole theme moving, or two names?">BREADTH</th>
            <th className="text-right" title="Net margin now vs 3 years ago">MARGIN</th>
          </tr></thead>
          <tbody>{d.themes.map((t) => (
            <Theme key={t.theme} t={t} open={open === t.theme}
              onToggle={() => setOpen(open === t.theme ? null : t.theme)} />))}
          </tbody></table>
        </div>)}

      {d?.themes?.length === 0 && (
        <div className="card text-dim text-sm">
          No statements cached — run <code>POST /api/quality/refresh-all</code> first.
        </div>)}

      <p className="text-dim text-xs">
        Medians throughout, so one company tripling its revenue cannot carry a theme —
        which is why breadth is shown separately. The AI theme is orthogonal to sector:
        a semiconductor company appears in both, exactly as on the heatmap.
      </p>
    </div>
  );
}
