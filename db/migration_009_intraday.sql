-- migration_009_intraday.sql
-- Intraday candle cache for the day-trading indicator/signal page. Separate from the
-- daily-grained `ohlcv` table (different primary key shape — timestamp, not date,
-- since there are many bars per trading session). `interval` is part of the key: 1m/5m/
-- 15m bars for the same symbol land on overlapping timestamps but represent different
-- bar durations, so they must not collide.
CREATE TABLE IF NOT EXISTS intraday_ohlcv (
  symbol TEXT REFERENCES symbols(symbol),
  interval TEXT NOT NULL,
  ts TIMESTAMPTZ NOT NULL,
  o NUMERIC, h NUMERIC, l NUMERIC, c NUMERIC, v BIGINT,
  PRIMARY KEY (symbol, interval, ts)
);
CREATE INDEX IF NOT EXISTS intraday_ohlcv_sym_int_ts ON intraday_ohlcv(symbol, interval, ts DESC);
