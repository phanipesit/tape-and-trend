"use client";
import { useEffect, useMemo, useRef, useState } from "react";
import Link from "next/link";
import { api, fmt } from "../../lib/api";
import { squarify, tileColor } from "../../lib/treemap";

const MARKETS = [["IN", "India"], ["US", "US"], ["", "Both"]];
const SIZES = [["turnover_share", "Turnover"], ["mcap_share", "Market cap"]];

const pctCls = (p) => (p > 0 ? "text-up" : p < 0 ? "text-down" : "text-mut");
const sign = (p) => (p > 0 ? "+" : "");

// A tile only gets a label it has room for — otherwise 8 characters of ticker
// overflow a 30px box and the board turns to mush.
function Tile({ t }) {
  const big = t.w > 96 && t.h > 62;
  const mid = t.w > 62 && t.h > 40;
  return (
    <Link href={`/charts?symbol=${t.symbol}`}
      title={`${t.symbol} · ${t.name}\n${t.sector}\nlast ${fmt(t.last)} · ${sign(t.pct)}${fmt(t.pct)}%\n${(t.share * 100).toFixed(2)}% of ${t.market} ${t.sizeLabel.toLowerCase()}`}
      className="absolute overflow-hidden border border-bg/70 hover:border-brass hover:z-10 transition-colors"
      style={{ left: t.x, top: t.y, width: t.w, height: t.h, background: tileColor(t.pct) }}>
      <div className="p-1 leading-tight">
        {mid && <div className="font-mono font-bold text-[11px] text-txt">{t.symbol}</div>}
        {big && <div className="text-[10px] text-txt/70 truncate">{t.name}</div>}
        {big && <div className="font-mono text-[10px] text-txt/80">{fmt(t.last)}</div>}
        {mid && (
          <div className="font-mono text-[10px] text-txt">
            {sign(t.pct)}{fmt(t.pct)}%</div>)}
      </div>
    </Link>
  );
}

function Breadth({ rows }) {
  const up = rows.filter((r) => r.pct > 0).length;
  const down = rows.filter((r) => r.pct < 0).length;
  const flat = rows.length - up - down;
  const best = rows.reduce((a, b) => (!a || b.pct > a.pct ? b : a), null);
  const worst = rows.reduce((a, b) => (!a || b.pct < a.pct ? b : a), null);
  const cell = "border border-line rounded p-2";
  return (
    <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-2 text-xs">
      <div className={cell}><div className="text-dim text-[10px]">ADVANCERS</div>
        <div className="text-up font-mono text-base">{up}</div></div>
      <div className={cell}><div className="text-dim text-[10px]">DECLINERS</div>
        <div className="text-down font-mono text-base">{down}</div></div>
      <div className={cell}><div className="text-dim text-[10px]">UNCHANGED</div>
        <div className="text-mut font-mono text-base">{flat}</div></div>
      <div className={cell}><div className="text-dim text-[10px]">A/D RATIO</div>
        <div className="font-mono text-base text-txt">{down ? fmt(up / down) : up ? "∞" : "—"}</div></div>
      <div className={cell}><div className="text-dim text-[10px]">TOP GAINER</div>
        <div className="font-mono text-up">{best ? `${best.symbol} ${sign(best.pct)}${fmt(best.pct)}%` : "—"}</div></div>
      <div className={cell}><div className="text-dim text-[10px]">TOP LOSER</div>
        <div className="font-mono text-down">{worst ? `${worst.symbol} ${fmt(worst.pct)}%` : "—"}</div></div>
    </div>
  );
}

export default function Heatmap() {
  const [market, setMarket] = useState("IN");
  const [bucket, setBucket] = useState("ALL");
  const [sizeKey, setSizeKey] = useState("turnover_share");
  const [search, setSearch] = useState("");
  const [board, setBoard] = useState(null);
  const [err, setErr] = useState("");
  const [width, setWidth] = useState(0);
  const boxRef = useRef(null);

  useEffect(() => {
    setBoard(null);
    api(`/api/heatmap${market ? `?market=${market}` : ""}`)
      .then((b) => { setBoard(b); setErr(""); })
      .catch((e) => setErr(String(e.message || e)));
  }, [market]);

  // Tiles are absolutely positioned, so the layout needs a real pixel width.
  useEffect(() => {
    const el = boxRef.current;
    if (!el) return;
    const ro = new ResizeObserver(([e]) => setWidth(e.contentRect.width));
    ro.observe(el);
    return () => ro.disconnect();
  }, [board]);

  const rows = useMemo(() => {
    if (!board) return [];
    const s = search.trim().toUpperCase();
    return board.rows.filter((r) =>
      (bucket === "ALL" || (bucket === "AI" ? r.ai : r.group === bucket)) &&
      (!s || r.symbol.includes(s) || (r.name || "").toUpperCase().includes(s)));
  }, [board, bucket, search]);

  const height = 560;
  const sizeLabel = SIZES.find(([k]) => k === sizeKey)[1];
  const tiles = useMemo(() => {
    if (!width || !rows.length) return [];
    // Re-normalise within the filtered set — a tile should read as its share of
    // what's on screen, not of a universe the user just filtered away.
    const total = rows.reduce((s, r) => s + (r[sizeKey] || 0), 0);
    if (!total) return [];
    return squarify(rows.map((r) => ({ ...r, value: r[sizeKey], share: r[sizeKey] / total, sizeLabel })),
      width, height);
  }, [rows, width, sizeKey, height, sizeLabel]);

  const tabCls = (on) =>
    `px-2.5 py-1 rounded text-xs font-mono border ${
      on ? "border-brass text-brass bg-panel2" : "border-line text-mut hover:text-txt"}`;

  return (
    <div className="space-y-4">
      <div>
        <h1 className="text-xl font-bold">Market heatmap</h1>
        <p className="text-mut text-sm">
          Tile area is share of traded value, colour is the day's move — intensity saturates at ±3%.
          Click any tile for its chart.
        </p>
      </div>

      {err && <div className="card border-down text-down text-sm">Heatmap unavailable — {err}</div>}

      <div className="card space-y-3">
        <div className="flex flex-wrap gap-2 items-center">
          {MARKETS.map(([k, label]) => (
            <button key={k || "all"} className={tabCls(market === k)} onClick={() => setMarket(k)}>{label}</button>))}
          <span className="text-line2">|</span>
          {SIZES.map(([k, label]) => (
            <button key={k} className={tabCls(sizeKey === k)} onClick={() => setSizeKey(k)}>{label}</button>))}
          <input className="w-40 ml-auto !text-xs" placeholder="search ticker or name"
            value={search} onChange={(e) => setSearch(e.target.value)} />
          <span className="text-dim text-[11px] font-mono">
            {board?.as_of ? `close of ${board.as_of}` : ""}</span>
        </div>

        <div className="flex flex-wrap gap-1.5">
          <button className={tabCls(bucket === "ALL")} onClick={() => setBucket("ALL")}>
            ALL <span className="text-dim">{board?.rows.length ?? ""}</span></button>
          <button className={tabCls(bucket === "AI")} onClick={() => setBucket("AI")}
            title="Explicit AI labels plus semiconductors. Excludes plain 'Technology' — the hyperscalers would dominate every tile.">
            AI <span className="text-dim">{board?.ai_count ?? ""}</span></button>
          {board?.groups.map((g) => (
            <button key={g.group} className={tabCls(bucket === g.group)} onClick={() => setBucket(g.group)}>
              {g.group.toUpperCase()} <span className="text-dim">{g.n}</span></button>))}
        </div>
      </div>

      {board && rows.length > 0 && <Breadth rows={rows} />}

      <div className="card">
        <div ref={boxRef} className="relative w-full" style={{ height }}>
          {!board && !err && <p className="text-dim text-sm">Loading heatmap…</p>}
          {board && rows.length === 0 && (
            <p className="text-dim text-sm">Nothing matches that filter.</p>)}
          {tiles.map((t) => <Tile key={t.symbol} t={t} />)}
        </div>
      </div>

      <p className="text-dim text-xs">
        Sizes are each stock's share of <b>its own market's</b> total, never the raw figure —
        Indian and US values are in different currencies, so a rupee market cap next to a dollar
        one would draw Reliance three times NVIDIA's tile. On “Both” with no filter that gives
        each market half the canvas; inside a filter the split instead shows how much of each
        market's activity the theme accounts for — which is why the AI names swamp the US side
        and barely register on the Indian one.
        {board?.missing?.length > 0 && ` No cached candles yet for ${board.missing.join(", ")}.`}
      </p>
      <p className="text-dim text-xs">
        Prices are the last cached daily close, not live ticks. Educational tool — not investment advice.
      </p>
    </div>
  );
}
