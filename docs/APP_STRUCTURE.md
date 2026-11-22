# LiquidityDissection — app structure

State on 2026-11-20 (branch `medv`). A signals app for gold and the 28 forex pairs: every minute it reads the market with
the **FX Alex G Set & Forget** strategy (v2 blueprint), sends each trade to Telegram, to phones (web push) and into the
app, and follows the trade to its TP or SL. **It never places an order.**

---

## 1. Hosting

| Part | Where | Address |
|---|---|---|
| Frontend (React) | Vercel project `ia-app-co94`, root `frontend/` | https://liquiditydissection.app |
| Backend (FastAPI, Python) | Vercel project `ia-app-tawny`, root `backend/` | https://ia-app-tawny.vercel.app |
| Database | Supabase Postgres `liquiditydissection-db` (free, us-east-1), via the Supabase Vercel integration (`POSTGRES_URL`) | — |
| Market data | Yahoo Finance (forex), COMEX GC=F adjusted to spot (gold); OANDA if a key is set | — |
| News | ForexFactory high-impact calendar | — |
| Every-minute run | Vercel Cron → `GET /api/cron/tick` (with `CRON_SECRET`) | — |

Locally: SQLite `backend/data/exunu.db`; `.claude/launch.json` starts `api` (port 8000) and `web` (port 3000).
Deploys: push to `medv` → Vercel previews → promoted to production.

---

## 2. Folders

```text
├── backend/                     FastAPI API + the strategy
│   ├── app/
│   │   ├── main.py              app, routers, /api/health, /api/cron/tick, /api/cron/status, local scheduler
│   │   ├── config.py            settings from environment variables (.env locally); which database URL wins
│   │   ├── db.py                SQLAlchemy engine (Postgres pool 3 + 7 on Vercel), auto-added columns, RLS on every table
│   │   ├── db_import.py         one-time copy of the old Neon data (admin route, dry run by default)
│   │   ├── models.py            database tables (section 7)
│   │   ├── auth.py              login, register, sessions, current_user, admin_user
│   │   ├── store.py             key/value settings in the database (telegram, overview, engine, history, push keys)
│   │   ├── push.py              web push (VAPID keys, sending)
│   │   ├── api/                 HTTP routes (section 6)
│   │   ├── market/              candles and prices (data.py), OANDA (oanda.py), the 28 pairs (pairs.py),
│   │   │                        candle cleaning (sanitize.py), news calendar (news.py), jsnum.py, types.py
│   │   ├── smc/                 the strategy and everything around it
│   │   │   ├── fxag/            ★ FX Alex G Set & Forget (section 3)
│   │   │   ├── desk.py          one pair's read: fetches candles, runs fxag, builds the JSON the app shows
│   │   │   ├── notify.py        every minute: reads the 29 pairs, sends new trades, saves the overview
│   │   │   ├── manager.py       follows every sent trade on M5 to TP / SL; history and win rate
│   │   │   ├── sizing.py        each user's lot from their own $ risk (saved once per signal)
│   │   │   ├── playbook.py      shared tools: candles, EMA, ATR, the trade follower run()
│   │   │   ├── skill/portfolio.py   one trade per pair, at most 3 trades per currency
│   │   │   ├── configs/<PAIR>.json  29 pair configs (pip, decimals, spread, pip value, lot step, currencies)
│   │   │   └── research/playbook.json  the last backtest numbers (shown in the app)
│   │   └── telegram/bot.py      bot commands (section 5), linking chats to accounts, sending messages
│   ├── tests/                   pytest (156 tests)
│   ├── requirements.txt
│   └── vercel.json              Python function + cron every minute
├── frontend/                    React 19 + Vite + Tailwind 4 + lightweight-charts (section 8)
├── smc/                         backtest tool (tools/playbook_test.py), news CSV, PLAYBOOK.md, FXAG_V2_REPORT.md, CHANGELOG.md
├── docs/                        this file, TRADINGVIEW.md
├── README.md
└── DEPLOY_VERCEL.md             how the two Vercel projects and the database are set up
```

---

## 3. The strategy: `backend/app/smc/fxag/` (2 agents)

```text
fxag/
├── config.py           29 pairs in 5 volatility groups (λ), 4 shards, "500" levels, every threshold of the blueprint
├── time_utils.py       New York 17:00 daily close (DST-aware), W / D / H4 / H2 buckets, sessions, blackouts, news window
├── strategy/           ── Agent 1 · Strategy & confirmation ──
│   ├── data.py         closed candles on 7 timeframes, data health (holes of more than 3 bars, duplicates)
│   ├── structure.py    body pivots, "True Elbows" (α × ATR), trend state machine, chop (ER12 + overlap), ATH / ATL
│   ├── alignment.py    W / D / H4 matrix → M1 full sync, M2 HTF retracement, M3 daily counter-weekly, M4 = no trade
│   ├── zones.py        ATR-adaptive W / D (/ H4 for M3) zones, validity, W+D merge, "500" level, suspension & flip
│   ├── confluence.py   C1..C8 score (0–100) → grade A+ ≥ 85 / A ≥ 75 / B+ ≥ 68 (B+ only M1 with R:R ≥ 2.5)
│   ├── entry.py        SoS on M15 / M30 / H1 + clean engulfing; models E1 (market) and E3 (limit at 50 % or the
│   │                   SoS neckline, 8 h); E2 is disabled (16 % win in the 60-day test)
│   └── checks.py       final gates: grade, R:R, weekly trap, SL too wide, session, news (−45 / +30 min), spread,
│                       data health, one trade per pair, currency cap → APPROVE or veto codes
├── risk/               ── Agent 2 · Stop loss, take profit & lot ──
│   ├── levels.py       SL behind the anchor + buffer + spread (floor / 1.8 ATR_D veto); TP at the first major D / W
│   │                   target ≥ 2R (cap 4.5R); weekly trap 1.85R (M3 2.2R); risk × grade × season (December 0.5)
│   └── order.py        the locked Set & Forget order: id = SHA256(pair | side | entry TF | candle)[:16]
├── pair_actor.py       evaluate(): ONE pure function for both the backtest and the live read;
│                       TIER_3_DORMANT → TIER_2_WATCHLIST → TIER_1_SNIPER_AOI → TIER_1_SOS_CONFIRMED
│                       → (AWAIT_PULLBACK_LIMIT) → SIGNAL_EMITTED
└── engine.py           scan (replay without look-ahead), report (the live read of the 2 agents), chart objects
```

Measured results and the blueprint's gates: `smc/FXAG_V2_REPORT.md` (the quality gates are not met yet).

---

## 4. The path of a trade, from the market to the notification

Checked end to end on 2026-11-20 by replaying a real EUR/USD SELL through the live code (only the sending was captured):
every step below ran and produced the messages shown.

```text
1  Vercel Cron, every minute ─► GET /api/cron/tick (Bearer CRON_SECRET) ─► notify.tick()
2  for each open pair (8 at a time): desk.team(pair)
      market/data.py: M5 (2000), H1 (6600), D1 (1600) candles → only CLOSED candles kept
      fxag.engine.scan → pair_actor.evaluate at each close → Agent 1 then Agent 2 → approved trade or vetoes
      fxag.engine.report → the live read; the trade still running is the pair's signal
3  a new signal ─► skill/portfolio.check (one per pair, ≤ 3 per currency) ─► saved once in `signals`
      (its id makes a second cron call in the same minute send nothing)
4  notify.broadcast:
      Telegram, every linked approved chat + the admin chat:      🔴 EUR/USD · SELL
                                                                  Entry 1.16158
                                                                  SL 1.16579
                                                                  TP 1.15221
                                                                  Lot 0.11        ← private chat only, from that user's $ risk
      Web push, every approved account's devices, ONE line:       🔴 EUR/USD SELL · Entry 1.16158 · SL 1.16579 · TP 1.15221 · Lot 0.11
      The app (GET /api/smc/signals every 20 s): the same one line as a toast and in the bell
5  manager.manage_all, every minute: the trade followed on M5 with the backtest's own follower
      Telegram + push, one line:  EUR/USD SELL · 🏆 TP hit · +2.20R   (or 🔴 SL hit, 🟢 Filled at …, ⏱️ Expired)
      the result (outcome, R) saved → the history and win rate in the app and in /history
6  the overview of all pairs saved (setting "overview") + heartbeat (setting "engine")
```

Nothing is sent while every market is closed (Friday 21:00 → Sunday 22:00 UTC): the tick then reports "market closed".

---

## 5. Telegram

Trade message: pair, side, entry, SL, TP, and the user's own lot in a private chat (never in a group). Endings: one line.

| Section | Commands |
|---|---|
| 📈 Trades | `/trades` running now · `/history` win rate, won / lost, R, last 5 · `/pairs` waiting for their trigger |
| 👤 My account | `/risk 50` my $ risk per trade · `/account` · `/connect` link this Telegram to my app account |
| 📊 Market | `/market` open / closed, session · `/news` next high-impact news |
| ℹ️ Help | `/help`, `/start` |

The trade and account commands answer only a Telegram linked to an approved account. Old names still work
(`/status` → `/account`, `/time` → `/market`).

---

## 6. API routes (all under `/api`; a login is needed except auth / health / cron / Telegram webhook)

| Area | Routes |
|---|---|
| Auth | `POST /auth/login`, `POST /auth/register`, `GET /auth/password-check`, `GET /auth/me`, `POST /auth/logout` |
| My account | `GET/PUT /me`, `GET/PUT /me/risk`, `GET /me/sizing/{signal_id}`, `GET /me/sizings`, `DELETE /me/telegram-link` |
| Users (admin) | `GET/POST /users`, `GET/PATCH/DELETE /users/{id}`, `POST /users/{id}/approve`, `DELETE /users/{id}/telegram-link`, `POST /admin/import-old-db` |
| Strategy | `GET /smc/team?symbol=`, `GET /smc/overview`, `GET /smc/signals`, `GET /smc/history`, `GET /smc/results` |
| Market | `GET /market/assets`, `/market/ticker`, `/market/prices`, `/market/candles`, `/exunu/candles`, `GET /news`, `POST /news/sync` |
| Settings / Telegram | `GET/PUT /settings`, `/telegram/config`, `/telegram/bot-info`, `/telegram/switch-bot`, `/telegram/webhook`, `/telegram/test`, `/telegram/test-me`, `/telegram/subscribers`, `/telegram/bot`, `/telegram/connect` |
| Push | `GET /push/key`, `POST /push/subscribe`, `/push/unsubscribe`, `/push/test` |
| System | `GET /health`, `GET/POST /cron/tick`, `GET /cron/status` |

---

## 7. Database tables (`backend/app/models.py`)

| Table | Holds |
|---|---|
| `users` | accounts (status pending / approved, role, Telegram chat, own $ risk) |
| `sessions` | login tokens |
| `subscribers`, `telegram_connect` | Telegram chats and their link to accounts |
| `push_subscriptions`, `push_sent` | phones / browsers for web push |
| `signals` | every trade sent (entry, SL, TP, state, outcome, R, steps sent): the history |
| `user_signal_sizes` | each user's lot for each signal (saved once) |
| `settings` | key/value: telegram (bot token), push keys, overview, engine heartbeat, history start, news |
| `watermarks`, `activation_keys`, `trades`, `trader_files` | older features, kept by the schema |

---

## 8. Frontend (`frontend/src/`)

| File | What it is |
|---|---|
| `main.tsx`, `App.tsx` | start, login gate, the pages |
| `api.ts`, `cache.ts` | calls to the backend; device cache (screens shown at once, refreshed behind) |
| `smcTeam.ts` | types of a pair's read; `signalLine()` = the one-line trade used by the toast and the bell |
| `components/DashboardView.tsx` | home: `PairsOverview` (29 pairs, counters trade / waiting / watching) + `TradeHistory` + market clock + news |
| `components/ExunuTerminalView.tsx` | chart page: pair bar, `PriceChart`, `TeamCard` (the 2 agents, grade bar 68 / 75 / 85) |
| `components/RiskSizing.tsx` | my $ risk and my lot per trade |
| `components/SignalToasts.tsx`, `NotificationBell.tsx` | new trade pop-up (one line, sound); alerts list; Telegram / push tests |
| `components/AccountView.tsx`, `AdminView.tsx`, `TelegramSettingsModal.tsx` | my account, user admin, Telegram setup |
| `components/LoginScreen.tsx`, `PendingApproval.tsx` | sign in / sign up, waiting for approval |
| `chart/`, `tradingview/` | drawing zones / levels / trades; optional TradingView Charting Library (docs/TRADINGVIEW.md) |
| `components/ui.tsx`, `components/layout/` | shared pieces, page layout (desktop + phone) |
| `notifications.ts`, `livePrices.ts`, `instruments.ts`, `splash.ts` | push registration, live prices, pair list, intro screen |
| `public/sw.js` | the service worker that shows the push notification and opens the pair when clicked |

Languages: French, English, Arabic (Darija).

---

## 9. Tests and tools

| Command | What it does |
|---|---|
| `.venv/Scripts/python -m pytest -q` (in `backend/`) | 156 backend tests |
| `node node_modules/typescript/bin/tsc --noEmit -p .` (in `frontend/`) | frontend type check |
| `PYTHONPATH=. backend/.venv/Scripts/python smc/tools/playbook_test.py feed` | backtest on the feed's history → `smc/PLAYBOOK.md` |

---

## 10. Main settings (Vercel backend environment)

`POSTGRES_URL` (Supabase integration), `CORS_ORIGINS`, `ADMIN_USERNAME`, `ADMIN_ACCESS_CODE`, `CRON_SECRET`,
`SCHEDULER_ENABLED=false`, `TELEGRAM_POLLING=false`, `TELEGRAM_WEBHOOK_URL`, `TELEGRAM_WEBHOOK_SECRET`.
Frontend: `VITE_API_URL`. The Telegram bot token is saved in the database (admin → Telegram).
