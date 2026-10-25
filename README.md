# EXUNU — XAUUSD & EURUSD strategies, signals and trade journal

> **Darija:** l'app daba fiha joj dossiers: `frontend/` (React, f Vercel) o `backend/` (Python FastAPI, f Render).
> Backend fih: users, trades li khditi, l'historique, win rate o ch7al mn trade, parametres dyal l'app o capital,
> o joj stratégies (Gold o EURUSD) li kaysifto signal l Telegram mni katsed la bougie. Kolchi bla flous (free tier).

```
frontend/   React 19 + Vite + Tailwind + lightweight-charts   → Vercel (free)
backend/    Python 3.12 + FastAPI + SQLAlchemy                  → Render (free) + Neon/Supabase Postgres (free)
docs/       STRATEGIES.md: the exact rules of both strategies
```

## What the backend does

| Area | Endpoints |
|---|---|
| Login | `POST /api/auth/login` (username + access code) · `GET /api/auth/me` · `POST /api/auth/logout` |
| Users (admin) | `GET/POST /api/users` · `PATCH/DELETE /api/users/{id}` |
| My capital & risk | `GET/PUT /api/me` |
| Trades taken | `GET/POST /api/trades` · `PATCH/DELETE /api/trades/{id}` · `POST /api/trades/{id}/close` · `POST /api/trades/{id}/breakeven` |
| History & win rate | `GET /api/stats` (win rate, wins/losses, P&L, current capital, profit factor, drawdown, equity curve) · `GET /api/trades?status=closed` |
| Strategy results | `GET /api/signals/performance` (every signal sent, followed candle by candle until TP/SL) |
| App parameters | `GET/PUT /api/settings` |
| Strategies & chart | `GET /api/exunu/setup` · `GET /api/exunu/candles` · `GET /api/signals` · `GET /api/backtest` |
| AI agent | `POST /api/agent/ask` · `POST /api/agent/explain-drawing` |
| Telegram (admin) | `GET/POST /api/telegram/config` · `/test` · `/dispatch-now` · `/activation/*` · `/subscribers` · `/trace` |
| Market | `GET /api/market/assets` · `/candles` · `/ticker` · `GET /api/news` · `GET /api/sentiment` |

Interactive docs: `http://localhost:8000/docs`.

Signals: at every M5 (gold) / M15 (EURUSD) candle close the scheduler runs the strategy on fresh candles and,
only for a SIGNAL (score ≥ 75, every required rule passed), sends it to the activated Telegram subscribers with
`protect_content`, a personal micro-offset and a reference code (anti copy-trading). A subscriber who taps
**🎯 دخلت الصفقة** gets the trade in their journal; its result is closed automatically with the strategy's lifecycle.

## Run locally

Backend (Python 3.12):

```bash
cd backend
python -m venv .venv
.venv/Scripts/pip install -r requirements.txt
cp .env.example .env
.venv/Scripts/uvicorn app.main:app --reload --port 8000
```

(macOS / Linux: `.venv/bin/...`.) On the first start an admin account is created; if `ADMIN_ACCESS_CODE` is empty
the generated code is printed in the console.

Frontend (Node 20+), in a second terminal:

```bash
cd frontend
npm install
npm run dev
```

Open http://localhost:3000. Vite forwards `/api` to the backend on port 8000.

Tests (strategy parity with the original TypeScript version, API, Telegram):

```bash
cd backend
.venv/Scripts/python -m pytest -q
```

Import the old app's data (users, activation codes, Telegram subscribers and settings):

```bash
cd backend
.venv/Scripts/python -m scripts.migrate_legacy ../data/db.json
```

## Deploy for free

1. **Database:** create a free Postgres on [Neon](https://neon.tech) (or Supabase) and copy its connection string.
   Render's free disk is erased on every restart, so SQLite is only for local use.
2. **Backend on Render:** New → Blueprint → this repository (`render.yaml`). Set `DATABASE_URL`, `ADMIN_ACCESS_CODE`,
   `CORS_ORIGINS` (your Vercel URL), and optionally `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`, `GEMINI_API_KEY`.
   To import the old data, run the migration once from your PC with `DATABASE_URL` pointing at Neon.
3. **Keep it awake:** free Render services sleep after 15 minutes without requests, and a sleeping server sends no
   signals. Add a free monitor on [cron-job.org](https://cron-job.org) or UptimeRobot that calls
   `https://<your-service>.onrender.com/api/health` every 10 minutes (one service running all month fits in the
   750 free hours).
4. **Frontend on Vercel:** New Project → root directory `frontend` → environment variable
   `VITE_API_URL=https://<your-service>.onrender.com` → Deploy.

Only one process may run the Telegram bot for a given token: stop any old server using the same bot.
