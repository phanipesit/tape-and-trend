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
# While a venue is OPEN today's daily bar is still forming — its close moves every tick,
# so "we already have today's bar" is not freshness. Callers that want an intra-session
# price pass live=True to get_candles and get this window instead. Opt-in on purpose:
# applying it everywhere would turn the screener's ~124-symbol sweep into 124 live fetches.
SESSION_CANDLE_STALE_MINUTES = int(os.getenv("SESSION_CANDLE_STALE_MINUTES", "10"))
INTRADAY_STALE_MINUTES = 5   # intraday candles go stale far faster than daily ones
FX_STALE_MINUTES = 30     # refetch USD/INR spot rate if cached value older than this
# NSE's chain endpoint is undocumented and rate-limited, and IV does not move fast enough
# to be worth hammering it — 15 min keeps a strategy re-price cheap while staying current.
NSE_CHAIN_STALE_MINUTES = int(os.getenv("NSE_CHAIN_STALE_MINUTES", "15"))
USD_INR_FALLBACK = 83.0   # only used if a live rate has never been fetched successfully
