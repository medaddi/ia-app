# LiquidityDissection — Private Trading Desk

Gold and forex signals from **4 autonomous pair agents**, each with its own deterministic strategy and its own chart, a
Multi-Agent Risk Coordinator over them, and delivery to the web app, the phone (Web Push) and Telegram, each with the
lot for the trader's own risk.

- **4 instruments, 4 agents:** XAU/USD, EUR/USD, GBP/USD, AUD/CHF (rules in [docs/STRATEGIES.md](docs/STRATEGIES.md))
- **Isolated per-chart rendering:** each agent emits its own `AgentChartOverlayState` (zones, lines, markers, trade projection)
- **Risk coordinator:** 1 % per trade, correlated USD exposure capped across EUR/USD, GBP/USD and gold, news blackout ±30 min
- **Accounts managed by the admin**; Telegram works only for a linked, approved account

```
frontend/   React 19 · Vite · Tailwind CSS 4 · lightweight-charts · motion       → Vercel project (root: frontend)
backend/    Python 3.12 · FastAPI · SQLAlchemy · Pillow · pywebpush              → Vercel project (root: backend)
docs/       STRATEGIES.md — the exact rules of the 4 agents and the risk coordinator
```

---

## Contents

1. [How the app works](#how-the-app-works)
2. [Strategies](#strategies)
3. [The agents and the risk coordinator](#the-agents-and-the-risk-coordinator)
4. [Notifications](#notifications)
5. [Telegram bot](#telegram-bot)
6. [Accounts and roles](#accounts-and-roles)
7. [The web app, page by page](#the-web-app-page-by-page)
8. [Run locally](#run-locally)
9. [Configuration](#configuration)
10. [Deploy](#deploy)
11. [API reference](#api-reference)
12. [Project structure](#project-structure)
13. [Troubleshooting](#troubleshooting)

---

## How the app works

```
 candle closes ──► the pair's agent runs on fresh candles ──► SIGNAL? ──► risk coordinator approves (1 % / 0.5 % / block)
                                                                      │
                          ┌───────────────────────────────────────────┼─────────────────────────────┐
                          ▼                                           ▼                             ▼
                 Telegram (linked accounts,                 Web Push (phones,             Web app (chart, setup
                 personal lot, protected)                   browsers)                     panel, dashboard)
                          │
                          ▼
     while the trade runs: the agent's trade projection on its chart + follow-up notices (filled · +1R · near SL · news)
                          │
                          ▼
     the trade ends: TP hit · SL hit · breakeven · closed early · cancelled — sent once, with what to do
```

1. **Candle close.** Each strategy is evaluated the moment its decision candle closes (H1 plans at the H1 close, inside
   their hours when they have some; GBP/USD at the H4 close). On Vercel an external pinger calls
   `/api/cron/tick` every minute; on an always-on server an in-process scheduler does the same.
2. **Signal.** A trade is only considered when every required rule passes (score ≥ 75), the market is open and no high-impact news is within 30 minutes.
3. **Agents.** Market analysis, strategy and risk & execution must all agree (3/3); any one of them can block.
4. **Delivery.** Each linked account gets the trade with the lot computed from **its own** risk (stop, spread and
   slippage included, rounded down to 0.01). Telegram messages are protected (no forwarding) and carry a personal
   reference code that traces leaks.
5. **Follow-up.** While the trade runs, agent 4 (trade management) watches it and one-time notices go out: order
   filled, +1R, near the stop, news ahead, exit soon (the strategy's own exit forming), order about to expire.
6. **Result.** When the trade ends, the result in R and what to do are sent once; the track record, win rate and
   the per-pair performance update automatically.

## Strategies

| Pair | Agent | Timeframes (UTC+1) | Setup | Order |
|---|---|---|---|---|
| XAU/USD | **XAUUSD_Sovereign_SMC_Agent** | M15 pools · M5 execution · London 08:00–11:00, NY 13:30–16:30 | Asian / London / PDH-PDL pool swept 8–65 pips and closed back inside within 3 M5 candles, M5 MSS, displacement ≥ 25 pips with FVG ≥ 6 pips or OB | LIMIT at FVG ∩ OTE (61.8–78.6 %) · SL sweep ± $0.50 (25–65 pips) · TP1 1.5R / session 50 % (≥ 1.3R, 50 % + BE+2) · TP2 opposite pool or 3R |
| EUR/USD | **EURUSD_AsianSweep_FVG_Agent** | M15 Asian range · M5 · London 08:00–11:00, NY 13:30–16:00 | Asian range 12–45 pips swept by 1–20 pips, M5 MSS with FVG ≥ 2.5 pips | LIMIT at the FVG ce_50 (12 bars) · SL sweep ± 3 pips (6–18) · BE at Asia 50 % / 1R · TP2 other side of Asia (≥ 2R) |
| GBP/USD | **GBPUSD_LondonJudas_SMT_Agent** | D1 / M15 levels · M5 · 08:00–10:30, reads EUR/USD | PDH / PDL / Asian level fakeout 4–30 pips with SMT vs EUR/USD, M5 MSS with a 3-candle displacement ≥ 1.5 ATR | LIMIT at OB_Mean (90 min) · SL ± 4 pips (15–28) · TP 3R · BE at 1.5R |
| AUD/CHF | **AUDCHF_MeanReversion_Range_Agent** | H4 range (ADX < 28) · H1 trigger | RSI(14) divergence in the 60-bar H4 supply / demand zone + H1 engulfing ≥ 0.7 ATR | MARKET · SL 1.2 ATR beyond (20–35 pips) · TP1 equilibrium (50 % + BE) · TP2 opposite zone |

Past trades are replayed with the same code (`app/agents/engine.py`), so each pair's TP / SL / break-even record is
measured, not estimated. Full rules: [docs/STRATEGIES.md](docs/STRATEGIES.md).

## The agents and the risk coordinator

Each pair agent (`backend/app/agents/`) is a state machine — `IDLE → ARMED → LIQUIDITY_SWEPT → MSS_CONFIRMED →
PENDING_ORDER → IN_TRADE → COOLDOWN` — and owns its chart: it emits its `AgentChartOverlayState`
(`GET /api/agents/overlay?symbol=`, also in every strategy result as `overlay`) and the chart renders only that
(`frontend/src/chart-overlays/agentOverlayPrimitive.ts`). The terminal shows one pair or a **4-chart split screen**,
each pane subscribed to its own agent.

The **Multi-Agent Risk Coordinator** (`backend/app/core/risk_guard.py`) approves every order: rules re-checked, live data,
limit still valid, spread guard, news blackout ±30 min (pending limits cut 30 min before red news), **correlated USD
exposure** across EUR/USD, GBP/USD and XAU/USD (0 unprotected same-direction trades → 1 %, 1 → 0.5 % with halved lots,
2 → blocked until one reaches TP1 / break-even), at most 4 open orders, 2 trades per pair a day and a −2.5 % daily lock.

## Notifications

| Channel | New trade | Follow-up while running | Result |
|---|---|---|---|
| **Telegram** | `🟢 BUY \| XAU/USD` · Entry · TP · SL · your lot, tap-to-copy | Filled · +1R · Near SL · News in N min · Exit soon · Cancel the order | TP hit / SL hit / breakeven / closed early / cancelled, with what to do |
| **Web Push** (phone, desktop) | `🟢 XAU/USD (BUY)` · `Entry \| LOT \| TP \| SL` | Same notices | Same |
| **In the app** | Browser notification while open, live trade bar | "Gestion du trade" card | Track record, dashboard |

- Web Push keys (VAPID) are generated once and stored in the database; nothing to configure.
- **iPhone / iPad:** web notifications only exist once the app is added to the home screen (iOS 16.4+).
- Every notice is sent **once** per trade, even with several workers or ticks (claimed in the database first).

## Telegram bot

### Linking an account

The bot only works for an **approved app account**. There are no activation codes.

1. In the app: sidebar **Lier Telegram** (or *Mon compte → Bot Telegram → Ouvrir le bot*).
2. In Telegram: press **Start**. The bot answers with an invitation button (one use, 15 minutes).
3. The button opens the app: log in, check the screen *"Lier Telegram à votre compte ?"* and tap **Accepter**.
4. The bot confirms and works with that account: access, risk and lot.

Rules: **one Telegram per account and one account per Telegram.** Unlinking (sidebar **Déconnecter**, *Mon compte*,
or the admin), disabling or deleting the account cuts the bot at once. The bot is not a chat: it only reads commands.

### Commands

| Command | What it does |
|---|---|
| `/start` | Welcome; not linked → the invitation to link the account |
| `/connect` | The invitation link (or which account this Telegram is linked to) |
| `/signal` | Every pair right now; then, for each running trade, its **chart** and its **follow-up card** |
| `/pairs` | The pair commands: `/gold`, `/eurusd`, `/gbpusd`, `/usdcad`, `/nzdusd`, `/eurchf`, `/nzdcad`, `/audcad`, `/audchf` |
| `/gold`, `/eurusd`, … | One pair in detail: price, trend, status, its trade or what it waits for |
| `/chart` | Pick a pair → `/chart_gold`, `/chart_eurusd`, … send the chart picture |
| `/open` | Trades running now, each followed by its chart and follow-up card |
| `/news` | Next high-impact news for the app's currencies |
| `/market` | Market hours and the current session |
| `/history` | Last 10 signals and their result |
| `/stats` | Win rate and results (30 days and all time), per pair |
| `/status` | My account, signals on / paused, my risk |
| `/risk 80` · `/risk 1%` | My risk per trade in $ or % of my capital (also changes the app account) |
| `/capital 5000` | My capital, for a risk in % |
| `/stop` · `/resume` | Pause / receive the signals again |
| `/rules` | How the strategies work |
| `/myid` | This chat's id |
| `/help` | All commands, grouped, each with what it does |

The chart picture is drawn on **15-minute candles** with the setup on it (the strategy's levels and zones, the signal
arrow, the trade's entry / stop / target zones) and a side panel: the plan (entry, stop, target, R:R, R now) and
**why the trade was taken** (the strategy's rules, ticked), or what the strategy is waiting for.

The `/` menu and the bot's description are kept up to date automatically from the code (on the next tick).

## Accounts and roles

- **Admin** creates accounts, or approves / refuses self sign-ups (a new account waits on a *pending* page until
  approved). The admin sees each user's stats, Telegram link, last login, and can unlink, disable or delete.
- **Trader** sets a risk per trade (fixed $ or % of capital) and a daily loss limit, records the lots taken, and gets
  a personal P&L, win rate, equity curve and calendar.
- **Sessions last 60 minutes** (`SESSION_MINUTES`), then the app asks to log in again.
- Passwords must be strong: 10+ characters, upper and lower case, a digit, a symbol, no spaces, not built on the
  username. The sign-up form checks them live.

## The web app, page by page

| Page | What is on it |
|---|---|
| **Intro** | The logo animation, at least 4 s, while the dashboard loads underneath |
| **Tableau de bord** | Today's P&L and loss limit, market clock with the next news, running trades as live bars, KPIs, live analysis of every pair, history (curve, winning days, month) |
| **Graphique en direct** | Draggable pair bar with flags, chart (M15 → D1, layers), the 4 agents, the setup panel: live trade bar, *Gestion du trade*, **your lot**, reachable targets |
| **Résultats des signaux** | Every signal sent, followed to its TP or SL |
| **Performance des paires** | Pick a pair: its strategy's TP / SL / BE record and closed trades |
| **Actualités & calendrier** | High-impact news and the sentiment radar |
| **Mon compte & trades** | Risk, capital, daily loss limit, Telegram link, my trades |
| **Utilisateurs** (admin) | Accounts, approvals, Telegram links |
| **Bot Telegram** (admin) | Bot token, delivery options, linked accounts, recent deliveries |

## Run locally

Requirements: **Python 3.12**, **Node 20+**.

### Backend

```bash
cd backend
python -m venv .venv
.venv/Scripts/pip install -r requirements.txt        # macOS / Linux: .venv/bin/pip
cp .env.example .env
.venv/Scripts/uvicorn app.main:app --reload --port 8000
```

On the first start, with an empty database, the admin account is created from `ADMIN_USERNAME` /
`ADMIN_ACCESS_CODE`. Interactive API docs: http://localhost:8000/docs.

### Frontend

```bash
cd frontend
npm install
npm run dev
```

Open http://localhost:3000. Vite forwards `/api` to the backend on port 8000.

### Everyday commands

| Task | Command |
|---|---|
| Backend tests | `cd backend && .venv/Scripts/python -m pytest -q` |
| Frontend type check | `cd frontend && npm run lint` |
| Frontend production build | `cd frontend && npm run build` |
| Preview the build | `cd frontend && npm run preview` |
| Import the old app's users and settings (its activation codes are no longer used) | `cd backend && .venv/Scripts/python -m scripts.migrate_legacy ../data/db.json` |

Only **one process** may poll a given Telegram bot token: stop any other server using the same bot.

## Configuration

Backend environment variables (`backend/.env` locally, the host's dashboard in production):

| Variable | Required | Purpose |
|---|---|---|
| `DATABASE_URL` | production | PostgreSQL URL (Neon / Supabase, pooled). Empty = SQLite in `backend/data/` (local only). `POSTGRES_URL` and the Vercel Neon names are accepted too |
| `ADMIN_USERNAME` | — | First admin's username (default `admin`) |
| `ADMIN_ACCESS_CODE` | **yes** | First admin's password on an empty database. Use a strong one and change it after the first login |
| `ADMIN_RESET` | — | `true` for one deploy resets the admin's password to `ADMIN_ACCESS_CODE`; remove it afterwards |
| `SESSION_MINUTES` | — | Login duration (default `60`) |
| `CORS_ORIGINS` | yes | The app's address(es), comma separated, e.g. `https://liquiditydissection.app` (the app's domain and `*.vercel.app` are always allowed) |
| `PUBLIC_APP_URL` | — | The app's address, opened by the bot's invitation button (default: the first `https://` entry of `CORS_ORIGINS`, else `https://liquiditydissection.app`) |
| `CRON_SECRET` | serverless | Protects `/api/cron/tick` (long random value) |
| `SCHEDULER_ENABLED` | — | In-process candle scheduler (`true` on an always-on server, `false` on Vercel) |
| `TELEGRAM_POLLING` | — | Bot long polling (`true` on an always-on server, `false` on Vercel) |
| `TELEGRAM_BOT_TOKEN` · `TELEGRAM_CHAT_ID` | — | Bot token and an optional group chat (both can be set in the app instead) |
| `TELEGRAM_WEBHOOK_URL` · `TELEGRAM_WEBHOOK_SECRET` | serverless | Bot webhook: `https://<api>/api/telegram/webhook` and a random secret |
| `GEMINI_API_KEY` · `GEMINI_MODEL` | — | AI assistant answers (otherwise deterministic answers from the strategy output) |
| `VAPID_PUBLIC_KEY` · `VAPID_PRIVATE_KEY` · `VAPID_SUBJECT` | — | Web Push keys (generated and stored automatically when absent) |

Frontend: `VITE_API_URL` — the backend's address when the frontend and the API are on different domains.

## Deploy

The app runs at **https://liquiditydissection.app**. The production setup is **two Vercel projects from this repository** plus a free PostgreSQL database
(step-by-step: [DEPLOY_VERCEL.md](DEPLOY_VERCEL.md)).

1. **Database** — create a Neon (or Supabase) PostgreSQL and use its *pooled* URL as `DATABASE_URL`.
   Tables are created and upgraded automatically on start.
2. **Backend project** — root directory `backend`, keep `backend/vercel.json`. Set the variables above with
   `SCHEDULER_ENABLED=false` and `TELEGRAM_POLLING=false`. Check `https://<api>/api/health` returns
   `"status":"ok"` and `"database":"ok"`.
3. **Frontend project** — root directory `frontend`, `VITE_API_URL=https://<api>`, then redeploy.
4. **Every minute** — an external scheduler (e.g. cron-job.org) calls
   `GET https://<api>/api/cron/tick` with the header `Authorization: Bearer <CRON_SECRET>`. This runs the strategies,
   sends signals, follow-ups and results, and keeps the bot's menu up to date.
5. **Telegram** — set `TELEGRAM_WEBHOOK_URL` / `TELEGRAM_WEBHOOK_SECRET`, then connect the bot token in the app
   (*Bot Telegram*): the webhook and the command menu are registered automatically.
6. **Custom domain** — in the frontend project: *Settings → Domains → Add* `liquiditydissection.app` and
   `www.liquiditydissection.app`, then at the registrar an `A` record `@ → 76.76.21.21` and a `CNAME`
   `www → cname.vercel-dns.com` (use the exact values Vercel shows). HTTPS is automatic. Then set
   `CORS_ORIGINS` and `PUBLIC_APP_URL` on the backend to the new address. Users log in again and re-enable
   notifications on the new domain (browser data is per address).
7. **Production branch** — make sure both projects deploy from `medv`.

An always-on alternative (`render.yaml`) runs the scheduler and bot polling in-process; a free instance sleeps after
15 minutes idle, so it needs a keep-alive ping on `/api/health`.

## API reference

All routes are under `/api`. Interactive docs at `/docs`. 🔒 = logged in, 👑 = admin.

| Area | Routes |
|---|---|
| Health & jobs | `GET /health` · `GET/POST /cron/tick` (Bearer `CRON_SECRET`) · `GET /cron/status` (is the signal engine running, what each pair decided, the last signal sent) |
| Auth | `POST /auth/login` · `POST /auth/register` · `GET /auth/password-check` · `GET /auth/me` 🔒 · `POST /auth/logout` 🔒 |
| My account 🔒 | `GET/PUT /me` · `GET /lot?symbol&entry&sl` · `GET /stats` · `GET/POST /trades` · `PATCH/DELETE /trades/{id}` · `POST /trades/{id}/close` · `POST /trades/{id}/breakeven` |
| Telegram link 🔒 | `GET /telegram/bot` · `GET /telegram/connect/{token}` · `POST /telegram/connect` · `DELETE /me/telegram-link` |
| Users 👑 | `GET/POST /users` · `GET /users/stats` · `GET/PATCH/DELETE /users/{id}` · `POST /users/{id}/approve` · `DELETE /users/{id}/telegram-link` |
| Strategies & chart | `GET /exunu/setup?symbol` · `GET /exunu/candles?symbol&timeframe&count` · `POST /exunu/dispatch-telegram` 👑 · `GET /backtest` |
| Signals & dashboard | `GET /dashboard` · `GET /signals` · `GET /signals/performance` |
| Market | `GET /market/assets` · `GET /market/candles` · `GET /market/ticker` · `GET /market/sync-all` · `GET /news` · `POST /news/sync` · `GET /sentiment` |
| Web Push 🔒 | `GET /push/key` · `POST /push/subscribe` · `POST /push/unsubscribe` · `POST /push/test` |
| Telegram admin 👑 | `GET/POST /telegram/config` · `POST /telegram/switch-bot` · `GET /telegram/bot-info` · `POST /telegram/test` · `POST /telegram/dispatch-now` · `GET /telegram/subscribers` · `DELETE /telegram/subscribers/{chat_id}` · `GET /telegram/trace?ref` · `GET /telegram/latency` |
| Telegram webhook | `POST /telegram/webhook` (Telegram only, checked with `TELEGRAM_WEBHOOK_SECRET`) |
| Settings | `GET /settings` · `PUT /settings` 👑 |
| AI assistant | `POST /agent/ask` · `POST /agent/explain-drawing` · `GET /agent/context` · `GET /agent/system-prompt` |

## Project structure

```
backend/
  app/
    main.py              FastAPI app, health, cron tick, startup (tables, admin, bot)
    config.py            Environment settings
    models.py            Users, sessions, signals, trades, subscribers, push, Telegram links…
    auth.py              Login, sign-up, sessions, password rules
    trading.py           Lot sizing, P&L, stats, signal outcomes
    push.py              Web Push (VAPID), new trade / follow-up / result notices
    followup.py          Follow-up notices of running trades
    agents/              The 4 pair agents (state machines + chart overlays), their engine and registry
    core/                Instrument specs, quant primitives (fractals, FVG, OB, OTE), risk coordinator
    agent/               AI chat assistant, explanations, rule re-check
    strategies/          Service, replay, lifecycle, shared helpers
    market/              Prices and candles (spot gold kept in spot terms), news
    telegram/            Bot (commands, delivery), scheduler, chart pictures, leak protection
    api/                 HTTP routes
  tests/                 pytest suite
frontend/
  index.html             Intro animation (shown before the app's code loads)
  src/
    App.tsx              Session, pages, Telegram link flow, notifications
    components/          Dashboard, chart (SmcChart), setup panel, agents, pages, layout
    chart-overlays/      The agent overlay renderer (zones, lines, trade projection)
    agentOverlay.ts      AgentChartOverlayState contract + per-symbol subscription
    notifications.ts     Browser + Web Push notifications
    splash.ts            Intro timing (≥ 4 s, waits for the first data)
docs/STRATEGIES.md       The 4 agents' rules and the risk coordinator
```

## Troubleshooting

| Symptom | Check |
|---|---|
| No signals on Vercel | Open `https://<api>/api/cron/status` (or the dashboard's "Automatic signals" line): `running: false` = the every-minute call to `/api/cron/tick` with `Authorization: Bearer <CRON_SECRET>` is not happening (check the cron-job.org job is enabled, every minute, with that header); `pairs` shows each pair's last decision or why a send failed. Markets close Fri 21:00 → Sun 22:00 UTC |
| `/api/health` says database missing | `DATABASE_URL` is not set on the backend project |
| Bot does not answer | `TELEGRAM_WEBHOOK_URL` / `TELEGRAM_WEBHOOK_SECRET` set, then the bot re-connected in *Bot Telegram*; only one process may poll a token |
| The bot's invitation opens the API instead of the app | Set `PUBLIC_APP_URL` (or put the app's address first in `CORS_ORIGINS`) |
| "Connect your app account first" | The Telegram is not linked, or the account is pending, disabled or deleted |
| No phone notifications | Notifications enabled in the app on this device; on iPhone the app must be on the home screen |
| Login asked again | Sessions last `SESSION_MINUTES` (60 by default) |
| Chart picture fails | Pillow installed (`backend/requirements.txt`) and the candle feed reachable |

---

Past results do not guarantee future results. Risk only what you can afford to lose.
