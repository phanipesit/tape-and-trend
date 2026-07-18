import "./globals.css";
import Nav from "../components/Nav";
import TickerTape from "../components/TickerTape";

export const metadata = { title: "Tape & Trend", description: "IN + US trading dashboard" };

export default function RootLayout({ children }) {
  return (
    <html lang="en">
      <body className="h-screen flex flex-col">
        <TickerTape />
        <header className="flex items-center gap-4 px-4 py-2.5 border-b border-line">
          <span className="font-mono font-semibold tracking-wider">TAPE<span className="text-brass">&</span>TREND</span>
          <span className="text-[11px] text-dim font-mono">FastAPI · PostgreSQL · TradingView</span>
        </header>
        <div className="flex flex-1 min-h-0">
          <Nav />
          <main className="flex-1 overflow-y-auto p-5">{children}</main>
        </div>
      </body>
    </html>
  );
}
