"use client";
import { useEffect, useState } from "react";
import {
  Bar, CartesianGrid, ComposedChart, Line, ReferenceLine, ResponsiveContainer,
  Tooltip, XAxis, YAxis,
} from "recharts";
import { api, fmt } from "../lib/api";

// Drawn from our own cached bars rather than a TradingView widget. Two reasons, both
// found the hard way: the free widget is not entitled to NSE data, so every Indian
// symbol rendered "this symbol doesn't exist" while the signals below computed fine;
// and pointing it at BSE instead meant the chart and the analysis were reading
// different exchanges. These are the exact bars intraday_signals.analyse reasons over.

const hhmm = (ts) =>
  new Date(ts.replace(" ", "T")).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });

function TipBox({ active, payload, label }) {
  if (!active || !payload?.length) return null;
  const d = payload[0].payload;
  const row = (k, v, cls = "") =>
    v == null ? null : <div key={k}><span className="text-dim">{k}</span> <span className={cls}>{fmt(v)}</span></div>;
  return (
    <div className="bg-panel border border-line2 rounded px-2 py-1 text-[11px] font-mono">
      <div className="text-mut mb-1">{hhmm(label)}</div>
      {row("O", d.o)}{row("H", d.h)}{row("L", d.l)}{row("C", d.c, "text-txt")}
      {row("VWAP", d.vwap, "text-brass")}
      {row("EMA9", d.ema9, "text-info")}{row("EMA20", d.ema20, "text-mut")}
      <div><span className="text-dim">VOL</span> {d.v?.toLocaleString("en-IN")}</div>
    </div>
  );
}

export default function IntradayChart({ symbol, interval = "5m", height = 380 }) {
  const [d, setD] = useState(null);
  const [err, setErr] = useState("");

  useEffect(() => {
    setD(null); setErr("");
    const load = () => api(`/api/intraday/candles/${encodeURIComponent(symbol)}?interval=${interval}`)
      .then(setD).catch((e) => setErr(String(e.message || e)));
    load();
    const t = setInterval(load, 60000);
    return () => clearInterval(t);
  }, [symbol, interval]);

  if (err) return <div className="card border-down text-down text-sm">Chart unavailable — {err}</div>;
  if (!d) return <div className="card text-dim text-sm" style={{ height }}>Loading {interval} bars…</div>;

  // 120 bars spans more than one session. The step between them is a real overnight
  // gap, not an intraday move, and VWAP restarts there — mark it so neither is misread.
  const sessionStarts = d.candles
    .filter((c, i) => i > 0 && c.ts.slice(0, 10) !== d.candles[i - 1].ts.slice(0, 10))
    .map((c) => c.ts);

  const closes = d.candles.map((c) => c.c);
  const lo = Math.min(...closes, d.or_lo ?? Infinity);
  const hi = Math.max(...closes, d.or_hi ?? -Infinity);
  const pad = (hi - lo) * 0.08 || 1;
  const noVwap = d.candles.every((c) => c.vwap == null);

  return (
    <div className="card">
      <div className="flex flex-wrap items-baseline gap-x-4 gap-y-1 mb-2 text-xs">
        <b className="text-sm font-mono">{d.symbol}</b>
        <span className="text-dim">{d.bars} × {d.interval} bars · our cached feed</span>
        <span className="text-brass">▬ VWAP</span>
        <span className="text-info">▬ EMA9</span>
        <span className="text-mut">▬ EMA20</span>
        <span className="text-dim">┅ opening range</span>
      </div>
      <ResponsiveContainer width="100%" height={height}>
        <ComposedChart data={d.candles} margin={{ top: 4, right: 8, left: 0, bottom: 0 }}>
          <CartesianGrid stroke="#1E2634" vertical={false} />
          <XAxis dataKey="ts" tickFormatter={hhmm} tick={{ fill: "#5A6478", fontSize: 10 }}
                 minTickGap={44} stroke="#2A3448" />
          <YAxis yAxisId="p" domain={[lo - pad, hi + pad]} tick={{ fill: "#5A6478", fontSize: 10 }}
                 width={62} stroke="#2A3448" tickFormatter={(v) => fmt(v, 0)} />
          {/* Volume shares the plot but gets its own hidden scale, squashed into the
              lower quarter so it reads as context and never competes with price. */}
          <YAxis yAxisId="v" hide domain={[0, (max) => max * 4]} />
          <Tooltip content={<TipBox />} cursor={{ stroke: "#5A6478", strokeWidth: 1 }} />
          <Bar yAxisId="v" dataKey="v" fill="#2A3448" isAnimationActive={false} />
          {sessionStarts.map((ts) => (
            <ReferenceLine key={ts} yAxisId="p" x={ts} stroke="#2A3448" strokeWidth={1}
              label={{ value: "new session", fill: "#5A6478", fontSize: 9, position: "insideTopLeft" }} />))}
          {d.or_hi != null && (
            <ReferenceLine yAxisId="p" y={d.or_hi} stroke="#5A6478" strokeDasharray="3 3" />)}
          {d.or_lo != null && (
            <ReferenceLine yAxisId="p" y={d.or_lo} stroke="#5A6478" strokeDasharray="3 3" />)}
          <Line yAxisId="p" dataKey="c" stroke="#E8ECF4" dot={false} strokeWidth={1.6} isAnimationActive={false} />
          {!noVwap && (
            <Line yAxisId="p" dataKey="vwap" stroke="#F5B942" dot={false} strokeWidth={1.2} isAnimationActive={false} />)}
          <Line yAxisId="p" dataKey="ema9" stroke="#4DA3FF" dot={false} strokeWidth={1} isAnimationActive={false} />
          <Line yAxisId="p" dataKey="ema20" stroke="#8A94A6" dot={false} strokeWidth={1} isAnimationActive={false} />
        </ComposedChart>
      </ResponsiveContainer>
      {noVwap && (
        <p className="text-dim text-[11px] mt-1">
          No VWAP line: Yahoo reports zero intraday volume for index symbols, so it is
          undefined here and volume-gated rules cannot fire. Expected, not a fault.
        </p>)}
    </div>
  );
}
