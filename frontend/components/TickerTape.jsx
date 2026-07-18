"use client";
import { useEffect, useRef } from "react";
import { tvSymbol } from "../lib/api";

const SYMS = ["RELIANCE","TCS","HDFCBANK","NVDA","AAPL","TSLA","INFY","MSFT"];

export default function TickerTape() {
  const ref = useRef(null);
  useEffect(() => {
    if (!ref.current || ref.current.dataset.loaded) return;
    ref.current.dataset.loaded = "1";
    const s = document.createElement("script");
    s.src = "https://s3.tradingview.com/external-embedding/embed-widget-ticker-tape.js";
    s.async = true;
    s.innerHTML = JSON.stringify({
      symbols: SYMS.map((x) => ({ proName: tvSymbol(x), title: x })),
      colorTheme: "dark", isTransparent: true, displayMode: "adaptive", locale: "en",
    });
    ref.current.appendChild(s);
  }, []);
  return <div ref={ref} className="tradingview-widget-container border-b border-line" />;
}
