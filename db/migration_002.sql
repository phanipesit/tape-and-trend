-- Update 3a: AI-focused universe expansion
-- Run in SQL Shell:   \c tapetrend
--                     \i C:/Users/phani/tape-and-trend/db/migration_003_ai_stocks.sql

-- ---- US: AI chips, infra and software ----
INSERT INTO symbols (symbol,name,market,sector) VALUES
 ('AMD','Advanced Micro Devices','US','Semiconductors'),
 ('AVGO','Broadcom','US','Semiconductors'),
 ('TSM','Taiwan Semiconductor (ADR)','US','Semiconductors'),
 ('MRVL','Marvell Technology','US','Semiconductors'),
 ('ARM','Arm Holdings (ADR)','US','Semiconductors'),
 ('PLTR','Palantir Technologies','US','AI Software'),
 ('ORCL','Oracle','US','Cloud/AI Infra'),
 ('VRT','Vertiv (AI datacenter)','US','AI Infrastructure')
ON CONFLICT (symbol) DO NOTHING;

-- ---- India: AI / engineering-R&D exposed ----
INSERT INTO symbols (symbol,name,market,sector) VALUES
 ('TATAELXSI','Tata Elxsi','IN','AI/Design Engineering'),
 ('KPITTECH','KPIT Technologies','IN','AI/Auto Software'),
 ('PERSISTENT','Persistent Systems','IN','IT/AI Services'),
 ('LTIM','LTIMindtree','IN','IT/AI Services'),
 ('HAPPSTMNDS','Happiest Minds','IN','Digital/AI Services'),
 ('CYIENT','Cyient','IN','Engineering R&D'),
 ('OFSS','Oracle Financial Services','IN','Fintech Software')
ON CONFLICT (symbol) DO NOTHING;

-- ---- Put the AI names on the watchlist (NVDA is already there) ----
INSERT INTO watchlist (symbol) VALUES
 ('AMD'),('PLTR'),('TSM'),('AVGO'),
 ('TATAELXSI'),('KPITTECH'),('PERSISTENT')
ON CONFLICT DO NOTHING;