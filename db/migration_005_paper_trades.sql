-- migration_005_paper_trades.sql
--
-- 1) Journal columns that the code has referenced since the portfolio/journal UI
--    shipped but that never made it into a migration (the "migration_002"
--    journal/risk changes described in UPDATE-INSTRUCTIONS.md were never shipped —
--    see "Known inconsistency" in CLAUDE.md). Without them every
--    POST /api/portfolio/tx failed with UndefinedColumn, so adding trades was
--    broken and portfolio_tx stayed empty.
ALTER TABLE portfolio_tx ADD COLUMN IF NOT EXISTS setup TEXT DEFAULT '';
ALTER TABLE portfolio_tx ADD COLUMN IF NOT EXISTS notes TEXT DEFAULT '';

-- 2) Paper-trading ("practice") mode: transactions flagged is_paper=true are kept
--    fully separate from real ones — positions, journal, and stats are computed
--    per mode, toggled from the portfolio page.
ALTER TABLE portfolio_tx ADD COLUMN IF NOT EXISTS is_paper BOOLEAN NOT NULL DEFAULT false;
