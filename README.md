# LiquidityDissection — gold & forex signals

A signals app for gold and 28 forex pairs. Every minute it reads the market with the **FX Alex G Set & Forget** strategy
(2 agents: strategy & confirmation, then stop loss / take profit / lot), sends each trade to Telegram, to phones (web push)
and into the app, and follows it to its TP or SL. **It never places an order. Not financial advice.**

```text
backend/    FastAPI API + the strategy (Python)       → Vercel project ia-app-tawny  (https://ia-app-tawny.vercel.app)
frontend/   React 19 + Vite + Tailwind web app        → Vercel project ia-app-co94   (https://liquiditydissection.app)
smc/        backtest tool and strategy reports
docs/       APP_STRUCTURE.md (the whole app), TRADINGVIEW.md
```

- **The whole app, file by file, and the path of a trade from the market to the notification:** [docs/APP_STRUCTURE.md](docs/APP_STRUCTURE.md)
- **Deploying:** [DEPLOY_VERCEL.md](DEPLOY_VERCEL.md)
- **Strategy results and history:** [smc/FXAG_V2_REPORT.md](smc/FXAG_V2_REPORT.md), [smc/CHANGELOG.md](smc/CHANGELOG.md)

## Run it locally

```bash
cd backend
python -m venv .venv && .venv/Scripts/pip install -r requirements.txt
.venv/Scripts/python -m uvicorn app.main:app --port 8000      # SQLite in backend/data/exunu.db

cd ../frontend
npm install && npm run dev -- --port 3000
```

Or start the `api` and `web` entries of `.claude/launch.json`.

## Check it

```bash
cd backend && .venv/Scripts/python -m pytest -q                 # backend tests
cd frontend && node node_modules/typescript/bin/tsc --noEmit -p .   # frontend type check
```
