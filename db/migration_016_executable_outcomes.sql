-- migration_016_executable_outcomes.sql
-- Score signal outcomes the way they could actually have been traded, and after costs.
--
-- Additive only: never edit schema.sql or a shipped migration in place.
--
-- Until now every outcome was scored from the signal bar's own close — a price that
-- only exists once the bar is final, so nobody can be filled at it — with stops filled
-- at exactly the stop even when the next open gapped through, and R reported gross of
-- costs. Re-scoring the 837 resolvable outcomes executably on 2026-09-26 moved the whole
-- system from -0.10R to -0.20R per trade; costs alone were ~0.11R a trade.
--
--   fill_entry  the next session's open — the first price a signal can be acted on
--   cost_r      round-trip statutory costs + slippage, in R, at that fill
--   r_net       r_multiple - cost_r; what /edge and the playbook now judge a rule by
--   scoring     method version. evaluate_open() re-scores any row whose version is not
--               current, so changing the method re-scores history automatically
--               instead of leaving two definitions of R mixed in one table.
--
-- entry/stop/target keep the plan as it was shown when the signal fired; r_multiple
-- becomes the gross executable R measured from fill_entry.

BEGIN;

ALTER TABLE signal_outcomes ADD COLUMN IF NOT EXISTS fill_entry NUMERIC;
ALTER TABLE signal_outcomes ADD COLUMN IF NOT EXISTS cost_r     NUMERIC;
ALTER TABLE signal_outcomes ADD COLUMN IF NOT EXISTS r_net      NUMERIC;
ALTER TABLE signal_outcomes ADD COLUMN IF NOT EXISTS scoring    TEXT;

CREATE INDEX IF NOT EXISTS idx_signal_outcomes_scoring ON signal_outcomes (scoring);

COMMIT;
