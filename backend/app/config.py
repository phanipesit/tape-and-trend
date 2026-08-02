import os
from dotenv import load_dotenv
load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql+psycopg2://postgres:postgres@localhost:5432/tapetrend")
TWELVEDATA_KEY = os.getenv("TWELVEDATA_KEY", "")
NEWSAPI_KEY = os.getenv("NEWSAPI_KEY", "")
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "llama3")   # set empty to disable the local-LLM path
OLLAMA_TIMEOUT = float(os.getenv("OLLAMA_TIMEOUT", "180"))  # an 8B model on CPU is slow
OLLAMA_NUM_CTX = int(os.getenv("OLLAMA_NUM_CTX", "8192"))   # llama3's full window; Ollama defaults to 4096
CORS_ORIGINS = os.getenv("CORS_ORIGINS", "http://localhost:3000").split(",")
# The user's own clock. Every venue session is rendered in this zone as well as the
# venue's, so "when does NYSE open" is answerable without mental arithmetic. IANA name.
HOME_TZ = os.getenv("HOME_TZ", "Asia/Kolkata")
CANDLE_STALE_HOURS = 12   # refetch from yfinance if cache older than this
INTRADAY_STALE_MINUTES = 5   # intraday candles go stale far faster than daily ones
FX_STALE_MINUTES = 30     # refetch USD/INR spot rate if cached value older than this
USD_INR_FALLBACK = 83.0   # only used if a live rate has never been fetched successfully
