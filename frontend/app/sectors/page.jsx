"use client";
import { useEffect, useState } from "react";
import { api, fmt } from "../../lib/api";

const QUADRANTS = {
  Leading:   { cls: "text-up",    d: "strong long-term and short-term momentum — money is here" },
  Improving: { cls: "text-brass", d: "weak long-term but strong recent momentum — rotation likely arriving" },
  Weakening: { cls: "text-info",  d: "strong long-term but fading recently — rotation likely leaving" },
  Lagging:   { cls: "text-down",  d: "weak on both horizons — money has left" },
};

const Ret = ({ v }) => v == null ? <td>—</td> :
  <td className={v >= 0 ? "text-up" : "text-down"}>{v >= 0 ? "+" : ""}{fmt(v, 1)}%</td>;

export default function Sectors() {
  const [market, setMarket] = useState("IN");
  const [data, setData] = useState(null);
  useEffect(() => { setData(null); api(`/api/sectors?market=${market}`).then(setData).catch(() => {}); }, [market]);
  const rows = data?.sectors || [];

  return (
    <div className="space-y-4">
      <div className="flex items-center gap-3 flex-wrap">
        <h1 className="text-xl font-bold">Sector rotation</h1>
        <select value={market} onChange={(e) => setMarket(e.target.value)}>
          <option value="IN">India</option><option value="US">US</option></select>
        {data?.as_of && <span className="text-dim text-xs font-mono">as of {data.as_of} (cached bars)</span>}
      </div>
      <p className="text-mut text-sm">
        Equal-weight price momentum by sector — a proxy for institutional rotation (actual FII/DII sector
        flows are only in NSDL/NSE monthly reports). <b className="text-brass">Improving</b> = weak over 6
        months but strong last month: where rotation money is typically arriving.
      </p>
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3 text-xs">
        {Object.entries(QUADRANTS).map(([k, v]) => {
          const members = rows.filter((r) => r.quadrant === k);
          return (
            <div key={k} className="card">
              <p className={`font-semibold ${v.cls}`}>{k} <span className="text-dim font-normal">({members.length})</span></p>
              <p className="text-dim text-[10px] mb-1">{v.d}</p>
              {members.map((m) => <p key={m.sector} className="font-mono text-mut">{m.sector}</p>)}
              {members.length === 0 && <p className="text-dim">—</p>}
            </div>);
        })}
      </div>
      <div className="card overflow-x-auto">
        <table className="w-full"><thead><tr>
          <th>SECTOR</th><th>STOCKS</th><th>1M</th><th>3M</th><th>6M</th><th>1Y</th><th>BREADTH</th><th>VOL TREND</th><th>QUADRANT</th>
        </tr></thead><tbody>
          {rows.map((s) => (
            <tr key={s.sector}>
              <td className="font-bold">{s.sector}</td>
              <td className="text-dim">{s.n}</td>
              <Ret v={s.r_1m} /><Ret v={s.r_3m} /><Ret v={s.r_6m} /><Ret v={s.r_1y} />
              <td className={s.breadth >= 60 ? "text-up" : s.breadth <= 30 ? "text-down" : ""}>{s.breadth}%</td>
              <td className={s.vol_ratio >= 1.2 ? "text-brass" : ""}>{s.vol_ratio ? fmt(s.vol_ratio, 2) + "×" : "—"}</td>
              <td className={QUADRANTS[s.quadrant]?.cls}>{s.quadrant}</td>
            </tr>))}
          {!data && <tr><td colSpan={9} className="text-dim">Loading…</td></tr>}
          {data && rows.length === 0 && <tr><td colSpan={9} className="text-dim">No sector data — candles may still be loading.</td></tr>}
        </tbody></table>
      </div>
      <p className="text-dim text-xs">
        Breadth = % of the sector's stocks above their 200-day average. Vol trend = last month's average
        daily volume vs the prior 3 months'. Sorted by 1-month return. Educational tool — not investment advice.
      </p>
    </div>
  );
}
