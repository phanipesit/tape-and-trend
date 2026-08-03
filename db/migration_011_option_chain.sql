-- migration_011_option_chain.sql
-- Cached NSE option chain: implied volatility per strike, per expiry.
--
-- Additive only: never edit schema.sql or a shipped migration in place.
-- After adding a table here, add its name to TABLES in backend/app/main.py so the
-- startup check catches a migration that was never run.
--
-- Why a table rather than an in-process cache: NSE's endpoint is undocumented,
-- rate-limited and needs a cookie warm-up per session, so a restart must not cost
-- another round of scraping. Same reasoning as ohlcv / intraday_ohlcv.
--
-- `opt_type` rather than `right`: RIGHT is a reserved SQL word and would need
-- quoting at every call site.

BEGIN;

CREATE TABLE IF NOT EXISTS option_chain (
    symbol      TEXT        NOT NULL,          -- our symbol (^NSEI), not NSE's (NIFTY)
    expiry      DATE        NOT NULL,
    strike      NUMERIC     NOT NULL,
    opt_type    TEXT        NOT NULL CHECK (opt_type IN ('CE', 'PE')),
    iv          NUMERIC,                       -- percent, as NSE publishes it; NULL when unquoted
    ltp         NUMERIC,
    oi          BIGINT,
    volume      BIGINT,
    spot        NUMERIC,                       -- underlyingValue at capture
    fetched_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (symbol, expiry, strike, opt_type)
);

-- The hot query is "nearest strike for this symbol+expiry".
CREATE INDEX IF NOT EXISTS option_chain_lookup
    ON option_chain (symbol, expiry, strike);

COMMIT;
