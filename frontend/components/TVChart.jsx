"use client";
import { useEffect, useRef } from "react";
import { tvSymbol } from "../lib/api";

export default function TVChart({ symbol = "RELIANCE", market = "IN" }) {
  const ref = useRef(null);
  const wrapRef = useRef(null);

  useEffect(() => {
    if (!ref.current) return;
    ref.current.innerHTML = "";
    const s = document.createElement("script");
    s.src = "https://s3.tradingview.com/external-embedding/embed-widget-advanced-chart.js";
    s.async = true;
    s.innerHTML = JSON.stringify({
      symbol: tvSymbol(symbol, market), theme: "dark", interval: "D", style: "1",
      locale: "en", autosize: true, withdateranges: true, allow_symbol_change: true,
      studies: ["STD;EMA", "STD;RSI", "STD;MACD"],
    });
    ref.current.appendChild(s);
  }, [symbol, market]);

  const toggleFull = () => {
    if (!document.fullscreenElement) wrapRef.current?.requestFullscreen?.();
    else document.exitFullscreen?.();
  };

  return (
    <div ref={wrapRef} className="relative card !p-0 overflow-hidden bg-bg"
         style={{ height: "75vh", minHeight: 520 }}>
      <button onClick={toggleFull}
        className="absolute top-2 right-14 z-10 ghost !py-1 !px-2 text-xs bg-panel/90"
        title="Toggle fullscreen (Esc to exit)">⛶ Fullscreen</button>
      <div ref={ref} className="tv-fill h-full w-full" />
    </div>
  );
}
