-- migration_012_signal_regime.sql
-- Market regime at the moment each signal fired.
--
-- Additive only: never edit schema.sql or a shipped migration in place.
-- After adding a table here, add its name to TABLES in backend/app/main.py so the
-- startup check catches a migration that was never run.
--
-- Why: the swing engine's short rules (breakdown_20d, rsi_overbought) measured
-- reliably negative over 2 years, and the leading explanation is that both were
-- shorting into a rising tape. Without regime on the row that stays an argument
-- rather than a measurement. RISK_ON/RISK_OFF is the index's own close against its
-- 200-day SMA on the signal date -- the same test rotation.py uses for its market
-- filter, so the two agree by construction.
--
-- Nullable on purpose: a signal on a symbol whose market index has under 200 bars
-- cached has no defensible regime, and NULL says that rather than guessing.

BEGIN;

ALTER TABLE signal_outcomes ADD COLUMN IF NOT EXISTS regime TEXT
    CHECK (regime IN ('RISK_ON', 'RISK_OFF'));

CREATE INDEX IF NOT EXISTS signal_outcomes_regime ON signal_outcomes (regime);

COMMIT;
