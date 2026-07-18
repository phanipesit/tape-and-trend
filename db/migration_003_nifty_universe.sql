-- Migration 003: full NIFTY 50 + NIFTY NEXT 50 universe
-- Run in SQL Shell:   \c tapetrend
--                     \i C:/Users/phani/tape-and-trend/db/migration_003_nifty_universe.sql
--
-- Constituent lists cross-checked against NSE/Wikipedia/broker sources, 2026-07.
-- Index composition is reviewed and rebalanced by NSE semi-annually (Mar/Sep) —
-- re-check constituents periodically; this is a point-in-time snapshot, not a feed.

-- ---- repair two tickers that changed after this project's data was first seeded ----
-- LTIM  -> LTM   LTIMindtree changed its NSE trading symbol, effective 2026-02-27.
-- TATAMOTORS -> TMPV/TMCV   Tata Motors demerged into Passenger Vehicles (TMPV,
--   the continuing entity) and a newly-listed Commercial Vehicles arm (TMCV) in
--   Oct/Nov 2025; the combined TATAMOTORS ticker no longer trades.
-- Insert the new symbols first (so ohlcv's FK has somewhere to point), repoint
-- cached candle history, then drop the dead rows.
INSERT INTO symbols (symbol,name,market,sector) VALUES
 ('LTM','LTIMindtree','IN','IT Services'),
 ('TMPV','Tata Motors Passenger Vehicles','IN','Auto (4-wheeler)'),
 ('TMCV','Tata Motors Commercial Vehicles','IN','Auto (commercial)')
ON CONFLICT (symbol) DO NOTHING;

UPDATE ohlcv SET symbol='LTM' WHERE symbol='LTIM';
UPDATE ohlcv SET symbol='TMPV' WHERE symbol='TATAMOTORS';

DELETE FROM symbols WHERE symbol IN ('LTIM','TATAMOTORS');

-- ---- NIFTY 50 ----
INSERT INTO symbols (symbol,name,market,sector) VALUES
 ('ADANIENT','Adani Enterprises','IN','Diversified'),
 ('ADANIPORTS','Adani Ports & SEZ','IN','Ports/Logistics'),
 ('APOLLOHOSP','Apollo Hospitals','IN','Healthcare'),
 ('ASIANPAINT','Asian Paints','IN','Consumer/Paints'),
 ('AXISBANK','Axis Bank','IN','Banking'),
 ('BAJAJ-AUTO','Bajaj Auto','IN','Auto (2-wheeler)'),
 ('BAJFINANCE','Bajaj Finance','IN','NBFC'),
 ('BAJAJFINSV','Bajaj Finserv','IN','Financial Services'),
 ('BEL','Bharat Electronics','IN','Defense/Electronics'),
 ('BHARTIARTL','Bharti Airtel','IN','Telecom'),
 ('CIPLA','Cipla','IN','Pharmaceuticals'),
 ('COALINDIA','Coal India','IN','Mining/Energy'),
 ('DRREDDY','Dr. Reddy''s Laboratories','IN','Pharmaceuticals'),
 ('EICHERMOT','Eicher Motors','IN','Auto (2-wheeler)'),
 ('ETERNAL','Eternal (Zomato)','IN','Consumer Internet'),
 ('GRASIM','Grasim Industries','IN','Cement/Diversified'),
 ('HCLTECH','HCLTech','IN','IT Services'),
 ('HDFCBANK','HDFC Bank','IN','Banking'),
 ('HDFCLIFE','HDFC Life Insurance','IN','Insurance'),
 ('HINDALCO','Hindalco Industries','IN','Metals & Mining'),
 ('HINDUNILVR','Hindustan Unilever','IN','FMCG'),
 ('ICICIBANK','ICICI Bank','IN','Banking'),
 ('INDIGO','InterGlobe Aviation (IndiGo)','IN','Airlines'),
 ('INFY','Infosys','IN','IT Services'),
 ('ITC','ITC','IN','FMCG'),
 ('JIOFIN','Jio Financial Services','IN','Financial Services'),
 ('JSWSTEEL','JSW Steel','IN','Metals & Mining'),
 ('KOTAKBANK','Kotak Mahindra Bank','IN','Banking'),
 ('LT','Larsen & Toubro','IN','Infrastructure'),
 ('M&M','Mahindra & Mahindra','IN','Auto (4-wheeler)'),
 ('MARUTI','Maruti Suzuki','IN','Auto (4-wheeler)'),
 ('MAXHEALTH','Max Healthcare','IN','Healthcare'),
 ('NESTLEIND','Nestle India','IN','FMCG'),
 ('NTPC','NTPC','IN','Power Generation'),
 ('ONGC','Oil & Natural Gas Corp','IN','Oil & Gas'),
 ('POWERGRID','Power Grid Corp','IN','Power Transmission'),
 ('RELIANCE','Reliance Industries','IN','Conglomerate'),
 ('SBILIFE','SBI Life Insurance','IN','Insurance'),
 ('SHRIRAMFIN','Shriram Finance','IN','NBFC'),
 ('SBIN','State Bank of India','IN','Banking'),
 ('SUNPHARMA','Sun Pharmaceutical','IN','Pharmaceuticals'),
 ('TCS','Tata Consultancy Services','IN','IT Services'),
 ('TATACONSUM','Tata Consumer Products','IN','FMCG'),
 ('TMPV','Tata Motors Passenger Vehicles','IN','Auto (4-wheeler)'),
 ('TATASTEEL','Tata Steel','IN','Metals & Mining'),
 ('TECHM','Tech Mahindra','IN','IT Services'),
 ('TITAN','Titan Company','IN','Consumer Durables/Jewellery'),
 ('TRENT','Trent','IN','Retail'),
 ('ULTRACEMCO','UltraTech Cement','IN','Cement'),
 ('WIPRO','Wipro','IN','IT Services')
ON CONFLICT (symbol) DO NOTHING;

-- ---- NIFTY NEXT 50 ----
INSERT INTO symbols (symbol,name,market,sector) VALUES
 ('ABB','ABB India','IN','Capital Goods'),
 ('ADANIENSOL','Adani Energy Solutions','IN','Power Transmission'),
 ('ADANIGREEN','Adani Green Energy','IN','Renewable Energy'),
 ('ADANIPOWER','Adani Power','IN','Power Generation'),
 ('AMBUJACEM','Ambuja Cements','IN','Cement'),
 ('BAJAJHLDNG','Bajaj Holdings & Investment','IN','Financial Holding'),
 ('BANKBARODA','Bank of Baroda','IN','Banking'),
 ('BPCL','Bharat Petroleum','IN','Oil & Gas'),
 ('BRITANNIA','Britannia Industries','IN','FMCG'),
 ('BOSCHLTD','Bosch','IN','Auto Components'),
 ('CANBK','Canara Bank','IN','Banking'),
 ('CGPOWER','CG Power & Industrial Solutions','IN','Electricals'),
 ('CHOLAFIN','Cholamandalam Investment','IN','NBFC'),
 ('CUMMINSIND','Cummins India','IN','Industrial Engines'),
 ('DIVISLAB','Divi''s Laboratories','IN','Pharmaceuticals'),
 ('DLF','DLF','IN','Real Estate'),
 ('DMART','Avenue Supermarts (DMart)','IN','Retail'),
 ('GAIL','GAIL India','IN','Oil & Gas'),
 ('GODREJCP','Godrej Consumer Products','IN','FMCG'),
 ('HDFCAMC','HDFC Asset Management','IN','Asset Management'),
 ('HAL','Hindustan Aeronautics','IN','Defense/Aerospace'),
 ('HINDZINC','Hindustan Zinc','IN','Metals & Mining'),
 ('HYUNDAI','Hyundai Motor India','IN','Auto (4-wheeler)'),
 ('INDHOTEL','Indian Hotels Company','IN','Hospitality'),
 ('IOC','Indian Oil Corp','IN','Oil & Gas'),
 ('IRFC','Indian Railway Finance Corp','IN','Financial Services'),
 ('JINDALSTEL','Jindal Steel & Power','IN','Metals & Mining'),
 ('LODHA','Macrotech Developers (Lodha)','IN','Real Estate'),
 ('LTM','LTIMindtree','IN','IT Services'),
 ('MAZDOCK','Mazagon Dock Shipbuilders','IN','Defense/Shipbuilding'),
 ('MUTHOOTFIN','Muthoot Finance','IN','NBFC'),
 ('PIDILITIND','Pidilite Industries','IN','Chemicals'),
 ('PFC','Power Finance Corp','IN','Financial Services'),
 ('PNB','Punjab National Bank','IN','Banking'),
 ('RECLTD','REC Limited','IN','Financial Services'),
 ('MOTHERSON','Samvardhana Motherson International','IN','Auto Components'),
 ('SHREECEM','Shree Cement','IN','Cement'),
 ('SIEMENS','Siemens','IN','Capital Goods'),
 ('ENRIN','Siemens Energy India','IN','Power Equipment'),
 ('SOLARINDS','Solar Industries India','IN','Chemicals/Defense'),
 ('TATACAP','Tata Capital','IN','NBFC'),
 ('TMCV','Tata Motors Commercial Vehicles','IN','Auto (commercial)'),
 ('TATAPOWER','Tata Power','IN','Power'),
 ('TORNTPHARM','Torrent Pharmaceuticals','IN','Pharmaceuticals'),
 ('TVSMOTOR','TVS Motor Company','IN','Auto (2-wheeler)'),
 ('UNIONBANK','Union Bank of India','IN','Banking'),
 ('UNITDSPR','United Spirits','IN','Beverages'),
 ('VBL','Varun Beverages','IN','Beverages'),
 ('VEDL','Vedanta','IN','Metals & Mining'),
 ('ZYDUSLIFE','Zydus Lifesciences','IN','Pharmaceuticals')
ON CONFLICT (symbol) DO NOTHING;
