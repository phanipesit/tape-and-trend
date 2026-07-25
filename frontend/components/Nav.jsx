"use client";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import { api, fmt } from "../lib/api";

const ITEMS = [
  ["/", "Dashboard"], ["/charts", "Charts"], ["/signals", "Swing signals"],
  ["/edge", "Your edge"],
  ["/screener", "Screener"], ["/sectors", "Sectors"], ["/options", "Options lab"],
  ["/daytrading", "Day trading"],
  ["/backtest", "Backtest"], ["/rotation", "Rotation"], ["/runs", "Runs"],
  ["/risk", "Risk calc"], ["/alerts", "Alerts"],
  ["/portfolio", "Portfolio"], ["/news", "News"],
];

// Polls fired alerts app-wide: badge on the Alerts nav item + a browser
// notification the first time each trigger is seen (keyed by id+triggered_at,
// so a re-armed alert notifies again on its next fire).
function useFiredAlerts() {
  const [fired, setFired] = useState([]);
  const seen = useRef(null);
  useEffect(() => {
    const poll = async () => {
      try {
        const rows = await api("/api/alerts");
        const f = rows.filter((a) => a.triggered_at);
        setFired(f);
        const keys = f.map((a) => `${a.id}:${a.triggered_at}`);
        if (seen.current === null) { seen.current = new Set(keys); return; } // don't re-announce old fires on page load
        const fresh = f.filter((a) => !seen.current.has(`${a.id}:${a.triggered_at}`));
        keys.forEach((k) => seen.current.add(k));
        if (fresh.length && typeof Notification !== "undefined" && Notification.permission === "granted") {
          fresh.forEach((a) => new Notification(`${a.symbol} alert fired`, {
            body: `${a.condition.replace("_", " ")} ${fmt(a.threshold)} — now ${fmt(a.triggered_value)}`,
          }));
        }
      } catch {}
    };
    poll();
    const t = setInterval(poll, 60000);
    return () => clearInterval(t);
  }, []);
  return fired;
}

export default function Nav() {
  const path = usePathname();
  const fired = useFiredAlerts();
  return (
    <nav className="w-44 shrink-0 border-r border-line p-3 flex flex-col gap-1 overflow-y-auto">
      {ITEMS.map(([href, label]) => (
        <Link key={href} href={href}
          className={`rounded-lg px-3 py-2 text-sm font-medium flex items-center justify-between ${
            path === href ? "bg-panel text-brass" : "text-mut hover:bg-panel hover:text-txt"}`}>
          {label}
          {href === "/alerts" && fired.length > 0 && (
            <span className="bg-brass text-bg rounded-full px-1.5 text-[10px] font-bold">{fired.length}</span>)}
        </Link>
      ))}
    </nav>
  );
}
