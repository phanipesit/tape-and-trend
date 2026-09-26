-- migration_015_bond_yields.sql
-- Government bond yields for the dashboard: India's G-Sec par curve and US Treasuries.
--
-- Additive only: never edit schema.sql or a shipped migration in place.
-- After adding a table here, add its name to TABLES in backend/app/main.py so the
-- startup check catches a migration that was never run.
--
-- The two markets arrive by different routes, which is why only one gets a table:
--
--   US  Yahoo carries ^IRX/^FVX/^TNX/^TYX, so Treasuries are ordinary `symbols` rows
--       cached in `ohlcv` through data.py like every other board symbol. The "price"
--       column simply holds the yield in percent.
--   IN  Yahoo has no India yield under any ticker (probed 2026-09-26). The benchmark is
--       FBIL's G-Sec par yield curve, published daily as an xlsx, 3M to 40Y in
--       quarter-year steps. It is a curve per date, not an OHLC bar, so it gets its own
--       table rather than being forced into ohlcv as 200 fake symbols.
--
-- yield_pct is the semi-annual YTM FBIL quotes first and Indian bond desks quote; the
-- annualised column is kept because it is free and some comparisons want it.

BEGIN;

CREATE TABLE IF NOT EXISTS bond_yields (
    country       TEXT    NOT NULL,             -- 'IN' today; keyed so a second source fits
    curve_date    DATE    NOT NULL,
    tenor_years   NUMERIC NOT NULL,
    yield_pct     NUMERIC NOT NULL,             -- semi-annual YTM, % p.a.
    yield_annual  NUMERIC,                      -- annualised YTM, % p.a.
    source        TEXT    NOT NULL,
    fetched_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (country, curve_date, tenor_years)
);

CREATE INDEX IF NOT EXISTS bond_yields_latest ON bond_yields (country, curve_date DESC);

-- US Treasuries: display-only, like metals. asset_class='bond' keeps them out of every
-- stock picker (all_symbols() admits only equity/index) and out of the world-indices
-- table (markets.board() selects its classes explicitly).
INSERT INTO symbols (symbol, name, market, is_index, asset_class, region) VALUES
  ('^IRX', 'US 13-week T-bill', 'US', false, 'bond', 'BONDS'),
  ('^FVX', 'US 5-year Treasury', 'US', false, 'bond', 'BONDS'),
  ('^TNX', 'US 10-year Treasury', 'US', false, 'bond', 'BONDS'),
  ('^TYX', 'US 30-year Treasury', 'US', false, 'bond', 'BONDS')
ON CONFLICT (symbol) DO UPDATE
  SET name = EXCLUDED.name, asset_class = EXCLUDED.asset_class, region = EXCLUDED.region;

COMMIT;
