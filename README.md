# LiquidityDissection — Private Trading Desk

Gold and forex signals with a strict, tested rule set, a live chart for every pair, four agents that check every trade,
and delivery to the web app, the phone (Web Push) and Telegram, each with the lot for the trader's own risk.

- **9 instruments:** XAU/USD, EUR/USD, GBP/USD, USD/CAD, NZD/USD, EUR/CHF, NZD/CAD, AUD/CAD, AUD/CHF
- **3 strategies**, each kept on the pairs where it tested best (rules in [docs/STRATEGIES.md](docs/STRATEGIES.md))
- **One target between 1.5R and 2R** on every trade; stops and targets never move once a trade is placed
- **Accounts managed by the admin**; Telegram works only for a linked, approved account

```
frontend/   React 19 · Vite · Tailwind CSS 4 · lightweight-charts · motion       → Vercel project (root: frontend)
backend/    Python 3.12 · FastAPI · SQLAlchemy · Pillow · pywebpush              → Vercel project (root: backend)
docs/       STRATEGIES.md — the exact rules of every strategy and how they were tested
```

---

## Contents

1. [How the app works](#how-the-app-works)
2. [Strategies](#strategies)
3. [The four agents](#the-four-agents)
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
 candle closes ──► strategy runs on fresh candles ──► SIGNAL? ──► 3 agents vote (3/3 needed)
                                                                      │
                          ┌───────────────────────────────────────────┼─────────────────────────────┐
                          ▼                                           ▼                             ▼
                 Telegram (linked accounts,                 Web Push (phones,             Web app (chart, setup
                 personal lot, protected)                   browsers)                     panel, dashboard)
                          │
                          ▼
     while the trade runs: agent 4 + follow-up notices (filled · +1R · near SL · news · exit soon)
                          │
                          ▼
     the trade ends: TP hit · SL hit · breakeven · closed early · cancelled — sent once, with what to do
```

1. **Candle close.** Each strategy is evaluated the moment its decision candle closes (gold every M15 close inside
   the forming H1, RSI(2) at the H4 close, GPA at the M30 close). On Vercel an external pinger calls
   `/api/cron/tick` every minute; on an always-on server an in-process scheduler does the same.
2. **Signal.** A trade is only considered when every required rule passes (score ≥ 75 for gold and RSI(2), grade
   ≥ C+ for GPA), the market is open and no high-impact news is within 30 minutes.
3. **Agents.** Market analysis, strategy and risk & execution must all agree (3/3); any one of them can block.
4. **Delivery.** Each linked account gets the trade with the lot computed from **its own** risk (stop, spread and
   slippage included, rounded down to 0.01). Telegram messages are protected (no forwarding) and carry a personal
   reference code that traces leaks.
5. **Follow-up.** While the trade runs, agent 4 (trade management) watches it and one-time notices go out: order
   filled, +1R, near the stop, news ahead, exit soon (the strategy's own exit forming), order about to expire.
6. **Result.** When the trade ends, the result in R and what to do are sent once; the track record, win rate and
   the per-pair performance update automatically.

## Strategies

| Pairs | Strategy | Decides on | Entry | Exit |
|---|---|---|---|---|
| XAU/USD | **H1 Trend Breakout + Bollinger Reversion** (two engines, one trade at a time) | H1, confirmed at each M15 close | Breakout: H1 close beyond the 20-hour range with a strong body, in the EMA50/EMA200 trend · Reversion (London / New York): close back inside the 2.2σ band | Breakout 2R · Reversion 1.5R, or after 24 H1 candles |
| EUR/USD, GBP/USD | **RSI(2) Connors pullback** | H4 | RSI(2) extreme against the H4 trend (EMA50/EMA200) | 1.5R, or earlier at the first H4 close back across EMA5, max 48 H4 candles |
| USD/CAD, NZD/USD, EUR/CHF, NZD/CAD, AUD/CAD, AUD/CHF | **FXAlexG Set & Forget GPA** | M30 at the London / New York open | W1/D1/H4 trend majority, W1/D1 area of interest with ≥ 3 touches, H4 rejection, M30 engulfing | Next W1/D1 zone, between 1.5R and 2R |

Every target is kept between **1.5R and 2R** (`TARGET_MIN_R` / `TARGET_MAX_R`). Past trades are replayed with the
same rules, so the TP / SL / breakeven record and each pair's performance are measured, not estimated.
Full rules, filters and test results: [docs/STRATEGIES.md](docs/STRATEGIES.md).

## The four agents

| # | Agent | Reads | Blocks a trade when |
|---|---|---|---|
| 1 | **Market analysis** | Daily EMA20/EMA50 trend, ATR regime, high-impact news | Against the daily trend, volatility spike (ATR > 2.5× usual), major news < 1 h away |
| 2 | **Strategy** | The strategy's decision and the market report | The signal is not valid, not fresh, or does not fit the market report |
| 3 | **Risk & execution** | AI trade desk (rules re-checked on live data, price drift, live R:R, currency exposure), open book | Any check fails, or 4 signals are already open |
| 4 | **Trade management** | The running trade, its candles since the fill, the market report | — (never blocks; runs after the entry) |

Agent 4 manages a placed trade like a disciplined professional: **the stop and the target never move** (that is the
tested edge). It tracks R now, best and worst R since the fill, applies the strategy's own exits on time (RSI(2) EMA5
close, time limits, limit-order expiry) and reads the market around the trade. Its verdict is one of
`HOLD`, `CAUTION`, `EXIT_SOON`, `WAIT`, `CANCEL`, always with one sentence saying what to do. It appears in the setup
panel ("Gestion du trade"), in the agents card, on Telegram and in the follow-up card picture.

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
| Health & jobs | `GET /health` · `GET/POST /cron/tick` (Bearer `CRON_SECRET`) |
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
    agent/               The four agents, AI trade desk, explanations
    strategies/          Gold, RSI(2), FXAlexG GPA; replay, lifecycle, shared rules
    market/              Prices and candles (spot gold kept in spot terms), news
    telegram/            Bot (commands, delivery), scheduler, chart pictures, leak protection
    api/                 HTTP routes
  tests/                 pytest suite
frontend/
  index.html             Intro animation (shown before the app's code loads)
  src/
    App.tsx              Session, pages, Telegram link flow, notifications
    components/          Dashboard, chart (SmcChart), setup panel, agents, pages, layout
    chart-overlays/      Strategy drawings on the chart
    notifications.ts     Browser + Web Push notifications
    splash.ts            Intro timing (≥ 4 s, waits for the first data)
docs/STRATEGIES.md       Strategy rules and test results
```

## Troubleshooting

| Symptom | Check |
|---|---|
| No signals on Vercel | The every-minute call to `/api/cron/tick` with `Authorization: Bearer <CRON_SECRET>`; markets closed (Fri 21:00 → Sun 22:00 UTC) |
| `/api/health` says database missing | `DATABASE_URL` is not set on the backend project |
| Bot does not answer | `TELEGRAM_WEBHOOK_URL` / `TELEGRAM_WEBHOOK_SECRET` set, then the bot re-connected in *Bot Telegram*; only one process may poll a token |
| The bot's invitation opens the API instead of the app | Set `PUBLIC_APP_URL` (or put the app's address first in `CORS_ORIGINS`) |
| "Connect your app account first" | The Telegram is not linked, or the account is pending, disabled or deleted |
| No phone notifications | Notifications enabled in the app on this device; on iPhone the app must be on the home screen |
| Login asked again | Sessions last `SESSION_MINUTES` (60 by default) |
| Chart picture fails | Pillow installed (`backend/requirements.txt`) and the candle feed reachable |

---

Past results do not guarantee future results. Risk only what you can afford to lose.
