-- Migration 004: create the missing `alerts` table
-- Run in SQL Shell:   \c tapetrend
--                     \i C:/Users/phani/tape-and-trend/db/migration_004_alerts_table.sql
--
-- backend/app/routers/alerts.py and services/alerts_check.py have referenced this
-- table since it was first added, but the migration meant to create it
-- (see UPDATE-INSTRUCTIONS.md's "Update 1") was never actually applied — its
-- filename (migration_002.sql) got reused for the unrelated AI-stocks universe
-- migration instead. Every alert check has been silently failing with
-- "relation alerts does not exist" ever since.

CREATE TABLE IF NOT EXISTS alerts (
  id              BIGSERIAL PRIMARY KEY,
  symbol          TEXT REFERENCES symbols(symbol),
  condition       TEXT NOT NULL CHECK (condition IN ('price_above','price_below','rsi_above','rsi_below')),
  threshold       NUMERIC NOT NULL,
  is_active       BOOLEAN NOT NULL DEFAULT true,
  triggered_at    TIMESTAMPTZ,
  triggered_value NUMERIC,
  created_at      TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX IF NOT EXISTS alerts_pending_idx ON alerts(symbol) WHERE is_active AND triggered_at IS NULL;
