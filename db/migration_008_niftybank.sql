-- migration_008_niftybank.sql
-- Bank Nifty as a second index underlying for the Options strategy lab, alongside
-- ^NSEI (added in migration_007 for the rotation regime filter). Same pattern:
-- is_index=true so it's cached like any stock but hidden from ordinary stock
-- pickers by default (all_symbols(include_index=True) to see it).
INSERT INTO symbols (symbol, name, market, is_index) VALUES
 ('^NSEBANK', 'Nifty Bank Index', 'IN', true)
ON CONFLICT (symbol) DO NOTHING;
