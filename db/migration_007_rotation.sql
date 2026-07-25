-- migration_007_rotation.sql
--
-- Support for the momentum-rotation backtest (services/rotation.py): ranks a whole
-- market universe by momentum and rotates a basket of the top N, gated by a broad
-- market index above its own 200-day average.
--
-- 1) Index-level price data is needed for that regime filter, but no index symbol
--    is cached today. is_index marks a symbol row as a benchmark index rather than
--    a tradable stock: it's cached/refreshed through the exact same ohlcv pipeline
--    as everything else, but data.all_symbols() excludes it by default so it never
--    shows up in stock-picker dropdowns (watchlist, screener, portfolio, alerts).
ALTER TABLE symbols ADD COLUMN IF NOT EXISTS is_index BOOLEAN NOT NULL DEFAULT false;

INSERT INTO symbols (symbol, name, market, is_index) VALUES
 ('^NSEI', 'Nifty 50 Index', 'IN', true),
 ('^GSPC', 'S&P 500 Index', 'US', true)
ON CONFLICT (symbol) DO NOTHING;

-- 2) Run summaries, one row per backtest — mirrors backtest_runs but keyed by
--    market (a whole universe) instead of a single symbol. strategy defaults to
--    'momentum_rotation' so a future second portfolio-level strategy can share
--    this table rather than needing its own.
CREATE TABLE IF NOT EXISTS rotation_runs (
  id BIGSERIAL PRIMARY KEY,
  market TEXT NOT NULL CHECK (market IN ('IN','US')),
  strategy TEXT NOT NULL DEFAULT 'momentum_rotation',
  params JSONB,
  total_return NUMERIC, cagr NUMERIC, win_rate NUMERIC,
  max_drawdown NUMERIC, sharpe NUMERIC, n_trades INT, buy_hold NUMERIC,
  ran_at TIMESTAMPTZ DEFAULT now()
);
