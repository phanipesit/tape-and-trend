-- migration_006_signal_outcomes.sql
-- Forward-tracking of the swing engine's fired signals: each BUY/SELL rule that
-- fires is logged once per bar with its own ATR plan, then a daily job scores it
-- (stop or target hit first, else expired after 20 bars) so /edge can show which
-- setups actually have an edge. outcome NULL = still open.

CREATE TABLE IF NOT EXISTS signal_outcomes (
    id          BIGSERIAL PRIMARY KEY,
    symbol      TEXT NOT NULL REFERENCES symbols(symbol) ON DELETE CASCADE,
    signal_date DATE NOT NULL,              -- date of the bar that fired the rule
    setup_tag   TEXT NOT NULL,              -- stable rule id from services/signals.py
    sig_type    TEXT NOT NULL CHECK (sig_type IN ('BUY','SELL')),
    direction   TEXT NOT NULL CHECK (direction IN ('LONG','SHORT')),
    entry       NUMERIC NOT NULL,
    stop        NUMERIC NOT NULL,
    target      NUMERIC NOT NULL,
    atr         NUMERIC,
    score       NUMERIC,                    -- engine conviction score at fire time
    market      TEXT,                       -- IN | US, denormalised for grouping
    outcome     TEXT CHECK (outcome IN ('target_hit','stop_hit','expired')),
    exit_price  NUMERIC,
    exit_date   DATE,
    bars_held   INT,
    r_multiple  NUMERIC,                    -- signed; -1 = full stop, +2 = 2x risk
    created_at  TIMESTAMPTZ DEFAULT now(),
    UNIQUE (symbol, signal_date, setup_tag)
);

CREATE INDEX IF NOT EXISTS idx_signal_outcomes_open
    ON signal_outcomes(signal_date) WHERE outcome IS NULL;
CREATE INDEX IF NOT EXISTS idx_signal_outcomes_setup
    ON signal_outcomes(setup_tag, signal_date);
