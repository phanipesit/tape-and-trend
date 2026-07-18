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

export const tvSymbol = (s) => {
  const NSE = ["RELIANCE","TCS","HDFCBANK","INFY","ICICIBANK","SBIN","ITC","LT","BHARTIARTL","TATAMOTORS"];
  const NASDAQ = ["AAPL","MSFT","NVDA","GOOGL","AMZN","META","TSLA"];
  if (NSE.includes(s)) return `NSE:${s}`;
  if (NASDAQ.includes(s)) return `NASDAQ:${s}`;
  return `NYSE:${s}`;
};
export const fmt = (n, dp = 2) =>
  n == null ? "—" : Number(n).toLocaleString("en-IN", { maximumFractionDigits: dp, minimumFractionDigits: dp });
