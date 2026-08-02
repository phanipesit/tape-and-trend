-- migration_010_global_markets.sql
--
-- Adds the front-page global market board: world indices, precious metals and a
-- macro strip (WTI / DXY / VIX).
--
-- Why a new discriminator instead of reusing is_index: is_index currently means
-- "tradeable options underlying" — get_index_symbol() picks the market-regime index
-- off it for rotation, and the Options page's include_index=true picker shows exactly
-- those three. Marking Gold futures is_index=true would put GC=F in the options
-- underlying dropdown; marking it false would put it in every *stock* picker, since
-- all_symbols() only excludes is_index rows. Neither is right, so asset_class carries
-- the real distinction and is_index keeps its narrow existing meaning.
--
--   equity  existing stocks — every stock picker
--   index   ^NSEI / ^NSEBANK / ^GSPC — options underlyings, regime filter
--   global  world indices — display only, never in a picker
--   metal   precious metals — display only
--   macro   WTI / DXY / VIX — display only

ALTER TABLE symbols ADD COLUMN IF NOT EXISTS asset_class TEXT NOT NULL DEFAULT 'equity';
ALTER TABLE symbols ADD COLUMN IF NOT EXISTS region TEXT;

-- The three existing index rows keep is_index=true; only their class/region is set.
UPDATE symbols SET asset_class = 'index' WHERE is_index = true;
UPDATE symbols SET region = 'AMERICAS' WHERE symbol = '^GSPC';
UPDATE symbols SET region = 'INDIA'    WHERE symbol = '^NSEI';
-- ^NSEBANK deliberately keeps region NULL: it is an options underlying, not a
-- headline market gauge, and the board selects on region IS NOT NULL.

-- Foreign venues are neither 'IN' nor 'US'. yf_symbol() only special-cases 'IN'
-- (appending .NS/.BO), so any other value passes the ticker through unchanged —
-- which is exactly what Yahoo wants for ^FTSE, ^N225, 000001.SS and friends.
ALTER TABLE symbols DROP CONSTRAINT IF EXISTS symbols_market_check;
ALTER TABLE symbols ADD CONSTRAINT symbols_market_check
  CHECK (market IN ('IN', 'US', 'GLOBAL'));

INSERT INTO symbols (symbol, name, market, is_index, asset_class, region) VALUES
  -- world indices
  ('^IXIC',     'Nasdaq Composite', 'US',     false, 'global', 'AMERICAS'),
  ('^DJI',      'Dow Jones Ind Avg','US',     false, 'global', 'AMERICAS'),
  ('^BSESN',    'BSE SENSEX',       'IN',     false, 'global', 'INDIA'),
  ('^FTSE',     'FTSE 100',         'GLOBAL', false, 'global', 'EUROPE'),
  ('^STOXX50E', 'Euro Stoxx 50',    'GLOBAL', false, 'global', 'EUROPE'),
  ('^GDAXI',    'DAX 40',           'GLOBAL', false, 'global', 'EUROPE'),
  ('^N225',     'Nikkei 225',       'GLOBAL', false, 'global', 'APAC'),
  ('^HSI',      'Hang Seng',        'GLOBAL', false, 'global', 'APAC'),
  ('000001.SS', 'SSE Composite',    'GLOBAL', false, 'global', 'APAC'),
  -- precious metals (COMEX/NYMEX front-month futures; all USD per troy ounce, so
  -- ratios and spreads between them are dimensionally compatible)
  ('GC=F',      'Gold',             'US',     false, 'metal',  'METALS'),
  ('SI=F',      'Silver',           'US',     false, 'metal',  'METALS'),
  ('PL=F',      'Platinum',         'US',     false, 'metal',  'METALS'),
  ('PA=F',      'Palladium',        'US',     false, 'metal',  'METALS'),
  -- macro strip
  ('CL=F',      'WTI Crude',        'US',     false, 'macro',  'MACRO'),
  ('DX-Y.NYB',  'US Dollar Index',  'US',     false, 'macro',  'MACRO'),
  ('^VIX',      'CBOE Volatility',  'US',     false, 'macro',  'MACRO')
ON CONFLICT (symbol) DO UPDATE
  SET name = EXCLUDED.name, asset_class = EXCLUDED.asset_class, region = EXCLUDED.region;

CREATE INDEX IF NOT EXISTS symbols_asset_class ON symbols(asset_class);
