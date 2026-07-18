# Update 1 — Journal, Risk Calc, Alerts, RVOL, Today's Focus

## What's new
1. Portfolio → trade journal: setup tag + notes per trade, closed-trade table,
   stats (win rate, avg win/loss, expectancy, best/worst)
2. New "Risk calc" page: position sizing from account risk %, R:R, max loss —
   can auto-load any symbol's ATR entry/stop/target
3. New "Alerts" page: price/RSI above/below alerts, auto-checked every 5 min
   by the backend, fired alerts banner on the Dashboard, re-arm + delete
4. Screener: RVOL column + Min-RVOL filter, sorted by conviction score
5. Dashboard: "Today's focus" — top 3 setups by score, with size-it shortcut

## How to install (5 minutes)

### 1. Stop both servers
Press Ctrl+C in the uvicorn window and the npm window.

### 2. Run the database migration
Open SQL Shell (psql), Enter x4, password, then:
    \c tapetrend
    \i C:/Users/phani/tape-and-trend/db/migration_002.sql
Expect: ALTER TABLE, ALTER TABLE, CREATE TABLE.

### 3. Copy the files over
Copy the `backend` and `frontend` folders from this zip INTO
C:\Users\phani\tape-and-trend\  and choose "Replace the files" when asked.
(Files changed: 4 backend, 5 frontend, 2 new pages. Nothing else touched —
your .env is safe.)

### 4. Restart
Window 1:  cd C:\Users\phani\tape-and-trend\backend
           .venv\Scripts\activate
           uvicorn app.main:app --reload
Window 2:  cd C:\Users\phani\tape-and-trend\frontend
           npm run dev

### 5. Try it
- http://localhost:3000/risk    → load RELIANCE's ATR plan, see share count
- http://localhost:3000/alerts  → create "RELIANCE price_above 1400", Check now
- Portfolio → add a BUY with a setup + note, then a SELL → journal + stats appear
- Screener → new RVOL column; Dashboard → Today's focus card
