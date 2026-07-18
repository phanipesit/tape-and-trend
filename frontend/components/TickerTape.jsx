"use client";
import { useEffect, useRef } from "react";
import { tvSymbol } from "../lib/api";

// [symbol, market] pairs — includes the AI names
const SYMS = [
  ["NVDA", "US"], ["AMD", "US"], ["PLTR", "US"], ["TSM", "US"], ["AVGO", "US"],
  ["AAPL", "US"], ["MSFT", "US"], ["TSLA", "US"],
  ["RELIANCE", "IN"], ["TCS", "IN"], ["HDFCBANK", "IN"], ["INFY", "IN"],
  ["TATAELXSI", "IN"], ["KPITTECH", "IN"], ["PERSISTENT", "IN"],
];

export default function TickerTape() {
  const ref = useRef(null);
  useEffect(() => {
    if (!ref.current || ref.current.dataset.loaded) return;
    ref.current.dataset.loaded = "1";
    const s = document.createElement("script");
    s.src = "https://s3.tradingview.com/external-embedding/embed-widget-ticker-tape.js";
    s.async = true;
    s.innerHTML = JSON.stringify({
      symbols: SYMS.map(([x, m]) => ({ proName: tvSymbol(x, m), title: x })),
      colorTheme: "dark", isTransparent: true, displayMode: "adaptive", locale: "en",
    });
    ref.current.appendChild(s);
  }, []);
  return <div ref={ref} className="tradingview-widget-container border-b border-line" />;
}
