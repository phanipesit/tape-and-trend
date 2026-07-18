"use client";
import { useEffect, useRef } from "react";
import { tvSymbol } from "../lib/api";

export default function TVChart({ symbol = "RELIANCE", height = 480 }) {
  const ref = useRef(null);
  useEffect(() => {
    if (!ref.current) return;
    ref.current.innerHTML = "";
    const s = document.createElement("script");
    s.src = "https://s3.tradingview.com/external-embedding/embed-widget-advanced-chart.js";
    s.async = true;
    s.innerHTML = JSON.stringify({
      symbol: tvSymbol(symbol), theme: "dark", interval: "D", style: "1",
      locale: "en", autosize: true, withdateranges: true, allow_symbol_change: true,
      studies: ["STD;EMA", "STD;RSI", "STD;MACD"],
    });
    ref.current.appendChild(s);
  }, [symbol]);
  return <div ref={ref} style={{ height }} className="tradingview-widget-container card !p-0 overflow-hidden" />;
}
