"use client";
import Link from "next/link";
import { usePathname } from "next/navigation";

const ITEMS = [
  ["/", "Dashboard"], ["/charts", "Charts"], ["/signals", "Swing signals"],
  ["/screener", "Screener"], ["/options", "Options lab"],
  ["/backtest", "Backtest"], ["/runs", "Runs"],
  ["/risk", "Risk calc"], ["/alerts", "Alerts"],
  ["/portfolio", "Portfolio"], ["/news", "News"],
];

export default function Nav() {
  const path = usePathname();
  return (
    <nav className="w-44 shrink-0 border-r border-line p-3 flex flex-col gap-1 overflow-y-auto">
      {ITEMS.map(([href, label]) => (
        <Link key={href} href={href}
          className={`rounded-lg px-3 py-2 text-sm font-medium ${
            path === href ? "bg-panel text-brass" : "text-mut hover:bg-panel hover:text-txt"}`}>
          {label}
        </Link>
      ))}
    </nav>
  );
}
