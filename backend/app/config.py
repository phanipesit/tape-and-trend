import os
from dotenv import load_dotenv
load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql+psycopg2://postgres:postgres@localhost:5432/tapetrend")
TWELVEDATA_KEY = os.getenv("TWELVEDATA_KEY", "")
NEWSAPI_KEY = os.getenv("NEWSAPI_KEY", "")
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
CORS_ORIGINS = os.getenv("CORS_ORIGINS", "http://localhost:3000").split(",")
CANDLE_STALE_HOURS = 12   # refetch from yfinance if cache older than this
FX_STALE_MINUTES = 30     # refetch USD/INR spot rate if cached value older than this
USD_INR_FALLBACK = 83.0   # only used if a live rate has never been fetched successfully
