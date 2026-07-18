"use client";
import { useEffect, useState } from "react";
import { api } from "../../lib/api";

export default function News() {
  const [items, setItems] = useState([]);
  const [err, setErr] = useState("");
  useEffect(() => { api("/api/news").then(setItems).catch((e) => setErr(String(e))); }, []);
  return (
    <div className="space-y-4">
      <h1 className="text-xl font-bold">News</h1>
      <p className="text-mut text-sm">Per-ticker stories via yfinance (keyless) plus NewsAPI business headlines when NEWSAPI_KEY is set.</p>
      {err && <div className="card text-down text-sm">{err}</div>}
      <div className="card divide-y divide-line">
        {items.length === 0 && !err && <p className="text-dim text-sm py-2">Loading, or no stories available…</p>}
        {items.map((n, i) => (
          <a key={i} href={n.link || "#"} target="_blank" rel="noopener noreferrer" className="block py-3 hover:bg-panel2 px-2 rounded">
            <p className="font-medium text-sm">{n.title}</p>
            <p className="text-dim text-[11px] font-mono">{n.publisher || "—"}</p>
          </a>))}
      </div>
    </div>
  );
}
