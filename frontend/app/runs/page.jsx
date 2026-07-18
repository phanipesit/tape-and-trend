"use client";
import { useEffect, useState } from "react";
import { api, fmt } from "../../lib/api";

const COLS = [
  ["ran_at", "WHEN"], ["symbol", "SYMBOL"], ["strategy", "STRATEGY"], ["params", "PARAMS"],
  ["total_return", "RET%"], ["cagr", "CAGR%"], ["buy_hold", "B&H%"],
  ["win_rate", "WIN%"], ["max_drawdown", "MAXDD%"], ["sharpe", "SHARPE"], ["trades", "TRADES"],
];

export default function Runs() {
  const [rows, setRows] = useState([]);
  const [sort, setSort] = useState({ k: "ran_at", dir: -1 });
  const load = () => api("/api/backtest/history?limit=200").then(setRows).catch(() => {});
  useEffect(() => { load(); }, []);

  const sorted = [...rows].sort((a, b) => {
    const x = a[sort.k], y = b[sort.k];
    if (x == null) return 1; if (y == null) return -1;
    return (x > y ? 1 : x < y ? -1 : 0) * sort.dir;
  });
  const clickSort = (k) => setSort((s) => ({ k, dir: s.k === k ? -s.dir : -1 }));
  const best = (k, dir = 1) => {
    const v = rows.map((r) => r[k]).filter((x) => x != null);
    return v.length ? (dir > 0 ? Math.max(...v) : Math.min(...v)) : null;
  };
  const bestSharpe = best("sharpe"), bestRet = best("total_return");

  return (
    <div className="space-y-4">
      <h1 className="text-xl font-bold">Backtest runs</h1>
      <p className="text-mut text-sm">Every backtest you've ever run, straight from Postgres. Click a column header to sort; gold highlights the best Sharpe and return. Beats-buy-&-hold rows show a ✓.</p>
      <div className="card overflow-x-auto">
        <table className="w-full"><thead><tr>
          {COLS.map(([k, l]) => (
            <th key={k} className="cursor-pointer select-none hover:text-brass" onClick={() => clickSort(k)}>
              {l}{sort.k === k ? (sort.dir === -1 ? " ↓" : " ↑") : ""}</th>))}
          <th></th>
        </tr></thead><tbody>
          {sorted.map((r) => (
            <tr key={r.id}>
              <td className="text-dim">{String(r.ran_at).slice(0, 16).replace("T", " ")}</td>
              <td className="font-bold">{r.symbol}</td>
              <td className="text-mut">{r.strategy}</td>
              <td className="text-dim text-[11px] max-w-[180px] truncate">{typeof r.params === "string" ? r.params : JSON.stringify(r.params)}</td>
              <td className={`${+r.total_return >= 0 ? "text-up" : "text-down"} ${+r.total_return === bestRet ? "text-brass font-bold" : ""}`}>
                {fmt(r.total_return, 1)}{+r.total_return > +r.buy_hold ? " ✓" : ""}</td>
              <td className={+r.cagr >= 0 ? "text-up" : "text-down"}>{fmt(r.cagr, 1)}</td>
              <td className="text-mut">{fmt(r.buy_hold, 1)}</td>
              <td>{fmt(r.win_rate, 0)}</td>
              <td className="text-down">−{fmt(r.max_drawdown, 1)}</td>
              <td className={+r.sharpe === bestSharpe ? "text-brass font-bold" : ""}>{fmt(r.sharpe, 2)}</td>
              <td>{r.trades}</td>
              <td><button className="ghost !px-2 !py-0.5" onClick={() => api(`/api/backtest/history/${r.id}`, { method: "DELETE" }).then(load)}>✕</button></td>
            </tr>))}
          {rows.length === 0 && <tr><td colSpan={12} className="text-dim">No runs yet — go to Backtest, run a few strategies, then compare them here.</td></tr>}
        </tbody></table>
      </div>
      <p className="text-dim text-xs">Careful with cherry-picking: a strategy that wins on one stock's history may just be fitted to that history. Prefer strategies that beat buy & hold across several symbols with tolerable drawdown.</p>
    </div>
  );
}
