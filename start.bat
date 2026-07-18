@echo off
start "Backend" cmd /k "cd /d C:\Users\phani\tape-and-trend\backend && .venv\Scripts\activate && uvicorn app.main:app --reload"
timeout /t 3 >nul
start "Frontend" cmd /k "cd /d C:\Users\phani\tape-and-trend\frontend && npm run dev"
timeout /t 5 >nul
start http://localhost:3000