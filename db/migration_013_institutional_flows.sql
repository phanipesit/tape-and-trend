-- migration_013_institutional_flows.sql
-- Daily FII/DII cash-market flows from NSE.
--
-- Additive only: never edit schema.sql or a shipped migration in place.
-- After adding a table here, add its name to TABLES in backend/app/main.py so the
-- startup check catches a migration that was never run.
--
-- This table is the *only* record of history. NSE's /api/fiidiiTradeReact returns the
-- latest trading day and nothing else — `from`/`to` params are accepted and ignored,
-- and the historical path 503s (probed 2026-08-15). So unlike ohlcv or signal_outcomes,
-- there is no backfill available: whatever is not captured on the day is gone. That is
-- why capture is wired into the daily scheduled task rather than fetched on demand.
--
-- Values are rupee crores, as NSE publishes them and as Indian flow reporting quotes
-- them. Not converted, because every external source you would cross-check against
-- uses crores.

BEGIN;

CREATE TABLE IF NOT EXISTS institutional_flows (
    flow_date   DATE    NOT NULL,
    category    TEXT    NOT NULL CHECK (category IN ('FII', 'DII')),
    buy_cr      NUMERIC NOT NULL,
    sell_cr     NUMERIC NOT NULL,
    net_cr      NUMERIC NOT NULL,
    fetched_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (flow_date, category)
);

CREATE INDEX IF NOT EXISTS institutional_flows_date ON institutional_flows (flow_date DESC);

COMMIT;
