-- Tape & Trend schema  ·  run:  psql -d tapetrend -f db/schema.sql
CREATE TABLE IF NOT EXISTS symbols (
  symbol      TEXT PRIMARY KEY,
  name        TEXT NOT NULL,
  market      TEXT NOT NULL CHECK (market IN ('IN','US')),
  sector      TEXT,
  pe NUMERIC, roe NUMERIC, de NUMERIC, rev_growth NUMERIC,
  mcap NUMERIC, div_yield NUMERIC,
  fundamentals_at TIMESTAMPTZ
);

CREATE TABLE IF NOT EXISTS ohlcv (
  symbol TEXT REFERENCES symbols(symbol),
  d      DATE NOT NULL,
  o NUMERIC, h NUMERIC, l NUMERIC, c NUMERIC, v BIGINT,
  PRIMARY KEY (symbol, d)
);
CREATE INDEX IF NOT EXISTS ohlcv_sym_d ON ohlcv(symbol, d DESC);

CREATE TABLE IF NOT EXISTS watchlist (
  symbol TEXT PRIMARY KEY REFERENCES symbols(symbol),
  added_at TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE IF NOT EXISTS portfolio_tx (
  id BIGSERIAL PRIMARY KEY,
  symbol TEXT REFERENCES symbols(symbol),
  side TEXT CHECK (side IN ('BUY','SELL')),
  qty NUMERIC NOT NULL CHECK (qty > 0),
  price NUMERIC NOT NULL,
  traded_at TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE IF NOT EXISTS backtest_runs (
  id BIGSERIAL PRIMARY KEY,
  symbol TEXT, strategy TEXT, params JSONB,
  total_return NUMERIC, cagr NUMERIC, win_rate NUMERIC,
  max_drawdown NUMERIC, sharpe NUMERIC, trades INT, buy_hold NUMERIC,
  ran_at TIMESTAMPTZ DEFAULT now()
);

INSERT INTO symbols (symbol,name,market,sector) VALUES
 ('AAPL','Apple','US','Technology'),('MSFT','Microsoft','US','Technology'),
 ('NVDA','NVIDIA','US','Semiconductors'),('GOOGL','Alphabet','US','Technology'),
 ('AMZN','Amazon','US','Consumer'),('META','Meta','US','Technology'),
 ('TSLA','Tesla','US','Auto'),('JPM','JPMorgan','US','Banking'),
 ('XOM','Exxon Mobil','US','Energy'),('UNH','UnitedHealth','US','Healthcare'),
 ('RELIANCE','Reliance Industries','IN','Conglomerate'),('TCS','Tata Consultancy','IN','IT Services'),
 ('HDFCBANK','HDFC Bank','IN','Banking'),('INFY','Infosys','IN','IT Services'),
 ('ICICIBANK','ICICI Bank','IN','Banking'),('SBIN','State Bank of India','IN','Banking'),
 ('ITC','ITC','IN','FMCG'),('LT','Larsen & Toubro','IN','Infrastructure'),
 ('BHARTIARTL','Bharti Airtel','IN','Telecom'),('TATAMOTORS','Tata Motors','IN','Auto')
ON CONFLICT (symbol) DO NOTHING;

INSERT INTO watchlist (symbol) VALUES
 ('RELIANCE'),('TCS'),('HDFCBANK'),('AAPL'),('NVDA'),('TSLA')
ON CONFLICT DO NOTHING;
