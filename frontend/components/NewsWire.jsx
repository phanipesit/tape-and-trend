"use client";
import { useEffect, useState } from "react";
import Link from "next/link";
import { api, ago } from "../lib/api";

// Dashboard news column. The backend blends NewsAPI business headlines (when
// NEWSAPI_KEY is set) with per-ticker stories for the watchlist and returns them
// deduped, newest first — this just renders that order.
export default function NewsWire({ limit = 12 }) {
  const [items, setItems] = useState(null);
  const [err, setErr] = useState("");

  useEffect(() => {
    const load = () => api(`/api/news?limit=${limit}`)
      .then((r) => { setItems(r); setErr(""); })
      .catch((e) => setErr(String(e.message || e)));
    load();
    // Headlines move far slower than quotes, and each poll costs ~4 upstream
    // fetches — 5 min, not the 1 min the price panels use.
    const t = setInterval(load, 300000);
    return () => clearInterval(t);
  }, [limit]);

  return (
    <div className="card flex flex-col">
      <h2 className="font-semibold mb-2">News wire{" "}
        <span className="text-dim text-xs font-normal">newest first · headlines + watchlist tickers</span>
      </h2>
      {err && <p className="text-down text-sm py-2">Feed unavailable — {err}</p>}
      {!items && !err && <p className="text-dim text-sm py-2">Loading stories…</p>}
      {items?.length === 0 && (
        <p className="text-dim text-sm py-2">
          No stories right now. Per-ticker news needs symbols on the watchlist;
          broad business headlines need NEWSAPI_KEY in <code>backend/.env</code>.
        </p>)}

      <div className="divide-y divide-line overflow-y-auto max-h-[24rem] -mx-2">
        {items?.map((n, i) => (
          <a key={n.link || i} href={n.link || "#"} target="_blank" rel="noopener noreferrer"
            className="block px-2 py-2 hover:bg-panel2 rounded">
            <p className="text-sm leading-snug">{n.title}</p>
            <p className="text-dim text-[11px] font-mono mt-1">
              {n.symbol && <><span className="text-brass">{n.symbol}</span> · </>}
              {n.publisher || "—"} · {ago(n.published)}
            </p>
          </a>))}
      </div>

      {items?.length > 0 && (
        <Link href="/news" className="ghost inline-block mt-3 self-start">Full news page →</Link>)}
    </div>
  );
}
