from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from .config import CORS_ORIGINS
from .routers import quotes, candles, screener, signals, backtest, portfolio, news

app = FastAPI(title="Tape & Trend API", version="1.0")
app.add_middleware(CORSMiddleware, allow_origins=CORS_ORIGINS,
                   allow_methods=["*"], allow_headers=["*"])

for r in (quotes, candles, screener, signals, backtest, portfolio, news):
    app.include_router(r.router)

@app.get("/")
def root():
    return {"ok": True, "docs": "/docs"}
