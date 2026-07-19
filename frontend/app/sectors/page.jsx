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

// Leading first when sorting by quadrant descending
const QUADRANT_RANK = { Leading: 3, Improving: 2, Weakening: 1, Lagging: 0 };

const COLS = [
  ["sector", "SECTOR"], ["n", "STOCKS"], ["r_1m", "1M"], ["r_3m", "3M"],
  ["r_6m", "6M"], ["r_1y", "1Y"], ["breadth", "BREADTH"],
  ["vol_ratio", "VOL TREND"], ["quadrant", "QUADRANT"],
];

export default function Sectors() {
  const [market, setMarket] = useState("IN");
  const [data, setData] = useState(null);
  const [sort, setSort] = useState({ key: "r_1m", desc: true });
  useEffect(() => { setData(null); api(`/api/sectors?market=${market}`).then(setData).catch(() => {}); }, [market]);

  const sortBy = (key) => setSort((s) =>
    ({ key, desc: s.key === key ? !s.desc : key !== "sector" }));

  const sortVal = (r) => sort.key === "quadrant" ? QUADRANT_RANK[r.quadrant] : r[sort.key];
  const rows = [...(data?.sectors || [])].sort((a, b) => {
    const va = sortVal(a), vb = sortVal(b);
    if (va == null) return 1;              // nulls always last
    if (vb == null) return -1;
    const cmp = typeof va === "string" ? va.localeCompare(vb) : va - vb;
    return sort.desc ? -cmp : cmp;
  });

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
          {COLS.map(([key, label]) => (
            <th key={key} className="cursor-pointer select-none hover:text-brass" onClick={() => sortBy(key)}>
              {label}{sort.key === key ? (sort.desc ? " ▼" : " ▲") : ""}
            </th>))}
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
        daily volume vs the prior 3 months'. Click a column header to sort. Educational tool — not investment advice.
      </p>
    </div>
  );
}
