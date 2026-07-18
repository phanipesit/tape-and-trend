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

// TradingView symbol mapping — no hardcoded lists.
// US: bare symbol (TradingView resolves NYSE/NASDAQ itself).
// India: BSE:<symbol> (free widgets serve BSE reliably; prices ≈ NSE).
export const tvSymbol = (s, market) => (market === "IN" ? `BSE:${s}` : s);

export const fmt = (n, dp = 2) =>
  n == null ? "—" : Number(n).toLocaleString("en-IN", { maximumFractionDigits: dp, minimumFractionDigits: dp });
