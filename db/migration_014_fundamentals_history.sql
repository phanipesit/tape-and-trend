-- migration_014_fundamentals_history.sql
-- Multi-year annual statements, for the quality screen.
--
-- Additive only: never edit schema.sql or a shipped migration in place.
-- After adding a table here, add its name to TABLES in backend/app/main.py so the
-- startup check catches a migration that was never run.
--
-- The `symbols` table already carries pe/roe/de/rev_growth/mcap/div_yield, but those
-- are a single current snapshot. Every criterion in the quality screen is multi-year --
-- average ROE, cumulative free cash flow, share-count change -- so a snapshot cannot
-- answer any of them. Hence a second, year-grained table rather than more columns.
--
-- EVERY COLUMN IS NULLABLE, AND THAT IS THE POINT. yfinance omits Gross Profit, EBIT
-- and Operating Income entirely for banks, and reports grossMargins as 0.0 -- a missing
-- value dressed as a real one. Storing 0 would fail HDFCBANK on "gross margin < 15%"
-- for a metric banks do not report. NULL means "not reported"; the screen skips those
-- criteria rather than judging on them. Same rule as the NSE option chain's unquoted
-- strikes: a zero is a blank, not a measurement.

BEGIN;

CREATE TABLE IF NOT EXISTS fundamentals_history (
    symbol            TEXT    NOT NULL,
    fiscal_year       INT     NOT NULL,
    revenue           NUMERIC,
    gross_profit      NUMERIC,
    net_income        NUMERIC,
    ebit              NUMERIC,
    interest_expense  NUMERIC,
    operating_cf      NUMERIC,
    capex             NUMERIC,
    free_cf           NUMERIC,
    shares            NUMERIC,
    equity            NUMERIC,
    fetched_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (symbol, fiscal_year)
);

-- The screen always reads a whole symbol's history at once, newest first.
CREATE INDEX IF NOT EXISTS fundamentals_history_symbol
    ON fundamentals_history (symbol, fiscal_year DESC);

COMMIT;
