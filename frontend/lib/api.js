const BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

export async function api(path, opts = {}) {
  const res = await fetch(`${BASE}${path}`, {
    headers: { "Content-Type": "application/json" },
    ...opts,
    body: opts.body ? JSON.stringify(opts.body) : undefined,
  });
  if (!res.ok) throw new Error(`${res.status} ${await res.text()}`);
  return res.json();
}

// TradingView symbol mapping — the one hardcoded list is this index map, since our
// ^-prefixed index tickers are Yahoo's convention (data.py's yf_symbol), not
// TradingView's — TradingView needs its own symbol regardless of exchange/market.
const TV_INDEX_MAP = { "^NSEI": "NSE:NIFTY", "^NSEBANK": "NSE:BANKNIFTY", "^GSPC": "TVC:SPX" };

// US: bare symbol (TradingView resolves NYSE/NASDAQ itself).
// India: BSE:<symbol> by default (free widgets serve BSE reliably; prices ≈ NSE) —
// but BSE only carries Daily/Weekly/Monthly on the free tier, no intraday. Callers
// that need minute-level charting (the day-trading page) pass exchange="NSE" instead,
// which does carry intraday data for free.
export const tvSymbol = (s, market, exchange = "BSE") =>
  TV_INDEX_MAP[s] || (market === "IN" ? `${exchange}:${s}` : s);

// Attribution line for an /api/ai/* response — the backend tries Claude, then a local
// model via Ollama, then its own rules, and reports which one actually ran as `source`.
export const aiCredit = (ai) =>
  ai.source === "claude" ? `Powered by Claude (${ai.model})`
  : ai.source === "ollama" ? `Local ${ai.model} via Ollama`
  : "Rule-based analysis — set ANTHROPIC_API_KEY in backend/.env, or run Ollama locally, for an AI narrative";

// "3h ago" from an ISO-8601 UTC string — services/news.py normalises every source
// (epoch seconds, Zulu, offset strings) to that one shape so this can stay dumb.
export const ago = (iso) => {
  if (!iso) return "—";
  const secs = (Date.now() - new Date(iso).getTime()) / 1000;
  if (Number.isNaN(secs)) return "—";
  if (secs < 60) return "just now";
  const m = Math.floor(secs / 60);
  if (m < 60) return `${m}m ago`;
  const h = Math.floor(m / 60);
  if (h < 24) return `${h}h ago`;
  return `${Math.floor(h / 24)}d ago`;
};

export const fmt = (n, dp = 2) =>
  n == null ? "—" : Number(n).toLocaleString("en-IN", { maximumFractionDigits: dp, minimumFractionDigits: dp });
