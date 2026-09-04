"use client";
import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { api, fmt } from "../../lib/api";

const VERDICT = {
  passes: ["passes", "border-up text-up"],
  review: ["review", "border-brass text-brass"],
  excluded: ["excluded", "border-down text-down"],
  "no data": ["no data", "border-line2 text-dim"],
};
const STATUS = {
  pass: "text-up", fail: "text-down", exempt: "text-brass",
  skipped: "text-dim",
};

// Ratios read as percentages; cash figures are absolute rupees and would be unreadable
// at full precision, so they are abbreviated.
function value(c) {
  if (c.value == null) return "—";
  if (Math.abs(c.value) >= 1e7) return `${(c.value / 1e7).toFixed(0)}cr`;
  if (c.n === 3 || c.n === 5) return `${fmt(c.value)}×`;
  return `${fmt(c.value * 100, 1)}%`;
}

function Row({ r, open, onToggle }) {
  const [label, cls] = VERDICT[r.verdict] || VERDICT["no data"];
  return (
    <>
      <tr className="cursor-pointer hover:bg-panel2" onClick={onToggle}>
        <td className="font-mono font-bold">
          <span className="text-dim mr-1">{open ? "▾" : "▸"}</span>{r.symbol}</td>
        <td className="text-mut truncate max-w-[13rem]">{r.name}</td>
        <td className="text-dim text-[11px]">{r.sector_group}</td>
        <td className="text-center">
          <span className={`text-[10px] font-mono border rounded-full px-2 py-0.5 ${cls}`}>
            {label}</span></td>
        <td className="text-right font-mono">{r.passed}/{r.scored}</td>
        <td className="text-right font-mono text-dim">{r.years}y</td>
        <td className="text-center">
          {r.confidence === "low" && (
            <span className="text-brass text-[10px] cursor-help"
              title="Judged on fewer than 5 tests, or under 4 years of statements">thin</span>)}
        </td>
      </tr>
      {open && (
        <tr><td colSpan={7} className="bg-panel2 px-4 py-3">
          <table className="w-full text-[11px]">
            <tbody>
              {r.checks.map((c) => (
                <tr key={c.n}>
                  <td className="text-dim w-6">{c.n}</td>
                  <td className="text-mut w-56">{c.name}</td>
                  <td className="font-mono text-right w-24">{value(c)}</td>
                  <td className={`w-20 pl-3 font-mono ${STATUS[c.status]}`}>{c.status}</td>
                  <td className="text-dim">{c.why}</td>
                </tr>))}
            </tbody>
          </table>
          {r.exemptions.length > 0 && (
            <p className="text-brass text-[11px] mt-2">
              {r.exemptions.map((e) => `Exemption ${e.rule}: ${e.why}`).join(" · ")}</p>)}
          <Link href={`/charts?symbol=${r.symbol}`}
            className="text-brass text-[11px] hover:underline">chart →</Link>
        </td></tr>)}
    </>
  );
}

export default function Quality() {
  const [d, setD] = useState(null);
  const [err, setErr] = useState("");
  const [market, setMarket] = useState("IN");
  const [filter, setFilter] = useState("");
  const [open, setOpen] = useState(null);

  useEffect(() => {
    setD(null); setErr("");
    api(`/api/quality${market ? `?market=${market}` : ""}`)
      .then(setD).catch((e) => setErr(String(e.message || e)));
  }, [market]);

  const rows = useMemo(() => {
    if (!d) return [];
    return filter ? d.results.filter((r) => r.verdict === filter) : d.results;
  }, [d, filter]);

  const counts = useMemo(() => {
    const c = { passes: 0, review: 0, excluded: 0 };
    d?.results.forEach((r) => { c[r.verdict] = (c[r.verdict] || 0) + 1; });
    return c;
  }, [d]);

  const tab = (on) => `px-2.5 py-1 rounded text-xs font-mono border ${
    on ? "border-brass text-brass bg-panel2" : "border-line text-mut hover:text-txt"}`;

  return (
    <div className="space-y-4">
      <div>
        <h1 className="text-xl font-bold">Quality screen</h1>
        <p className="text-mut text-sm">
          Seven accounting tests that <b>exclude</b> companies rather than predict prices —
          capital efficiency, cash generation, solvency, pricing power, earnings quality,
          resilience and dilution. Adapted from{" "}
          <a href="https://github.com/xbtlin/ai-berkshire" target="_blank"
             rel="noopener noreferrer" className="text-brass hover:underline">ai-berkshire</a>{" "}
          (MIT). A missing input is skipped, never counted as a failure.
        </p>
      </div>

      {/* This page reports no expectancy, unlike /edge, and the reason is not an
          oversight — say so where it will actually be read. */}
      <div className="card border-line2 text-xs text-mut">
        <b className="text-txt">What this is not.</b> Every other measurement in this app
        carries an expectancy and a confidence interval, because swing outcomes resolve in
        10–20 bars. Quality investing resolves over years, and this database holds two — so
        there is no honest way to score it here. “Passes seven quality tests” is a
        defensible statement about a company&apos;s accounts. It is not a prediction, and
        nothing on this page has been shown to beat holding an index.
      </div>

      {err && <div className="card border-down text-down text-sm">{err}</div>}

      <div className="card flex flex-wrap gap-2 items-center">
        {[["IN", "India"], ["US", "US"], ["", "All"]].map(([k, label]) => (
          <button key={k || "all"} className={tab(market === k)}
            onClick={() => setMarket(k)}>{label}</button>))}
        <span className="text-line2">|</span>
        <button className={tab(!filter)} onClick={() => setFilter("")}>
          all <span className="text-dim">{d?.results.length ?? ""}</span></button>
        {["passes", "review", "excluded"].map((v) => (
          <button key={v} className={tab(filter === v)} onClick={() => setFilter(v)}>
            {v} <span className="text-dim">{counts[v] || 0}</span></button>))}
        <span className="text-dim text-[11px] ml-auto">click a row for the seven checks</span>
      </div>

      {!d && !err && <div className="card text-dim text-sm">Screening…</div>}
      {d && rows.length === 0 && (
        <div className="card text-dim text-sm">
          Nothing cached for this market yet — statements are fetched explicitly via
          <code className="mx-1">POST /api/quality/refresh-all</code>, since annual
          reports change four times a year.
        </div>)}

      {rows.length > 0 && (
        <div className="card text-xs">
          <table className="w-full"><thead><tr>
            <th className="text-left">SYMBOL</th><th className="text-left">NAME</th>
            <th className="text-left">SECTOR</th><th className="text-center">VERDICT</th>
            <th className="text-right">PASSED</th><th className="text-right">YEARS</th>
            <th className="text-center">DATA</th>
          </tr></thead>
          <tbody>{rows.map((r) => (
            <Row key={r.symbol} r={r} open={open === r.symbol}
                 onToggle={() => setOpen(open === r.symbol ? null : r.symbol)} />))}
          </tbody></table>
        </div>)}

      <p className="text-dim text-xs">
        Two deviations from the source, both forced by the data. Average ROE is over ~5
        years, not 10 — free yfinance goes no further back for Indian listings. And banks
        are exempted from the margin tests as well as interest coverage: yfinance reports
        their gross margin as 0.0, which is a blank rather than a measurement, and taken
        literally it excludes HDFC Bank for a metric banks do not report.
      </p>
    </div>
  );
}
