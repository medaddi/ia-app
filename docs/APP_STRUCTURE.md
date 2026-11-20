# LiquidityDissection — app structure

State on 2026-11-20 (commit `4f6537d`, branch `medv`). A signals app for gold and the 28 forex pairs: it reads the market every
minute with the **FX Alex G Set & Forget** strategy, sends the trades it finds to Telegram, to phones (web push) and into
the app, and follows each trade to its end. **It never places an order.**

---

## 1. Hosting

| Part | Where | Address |
|---|---|---|
| Frontend (React) | Vercel project `ia-app-co94`, root `frontend/` | https://liquiditydissection.app |
| Backend (FastAPI, Python) | Vercel project `ia-app-tawny`, root `backend/` | https://ia-app-tawny.vercel.app |
| Database | Neon PostgreSQL (Vercel integration, `DATABASE_URL`) | — |
| Market data | Yahoo Finance (forex), COMEX GC=F adjusted to spot (gold); OANDA if a key is set | — |
| Every-minute run | Vercel Cron → `GET /api/cron/tick` (with `CRON_SECRET`) | — |

Locally: SQLite `backend/data/exunu.db`, `.claude/launch.json` starts `api` (port 8000) and `web` (port 3000).
Deploys: push to `medv` → Vercel previews → promoted to production (the production branch in Vercel is still `main`).

---

## 2. Folders

```text
tradingai-pro---intelligence-&-signals/
├── backend/                     FastAPI API + the strategy
│   ├── app/
│   │   ├── main.py              app, routers, /api/health, /api/cron/tick, /api/cron/status, local scheduler
│   │   ├── config.py            settings from environment variables (.env locally)
│   │   ├── db.py                SQLAlchemy engine (Postgres pool 3 + 7 on Vercel), auto-added columns
│   │   ├── models.py            database tables (section 6)
│   │   ├── auth.py              login, register, sessions, current_user
│   │   ├── store.py             key/value settings in the database (telegram, overview, history, …)
│   │   ├── push.py              web push (VAPID)
│   │   ├── api/                 HTTP routes (section 5)
│   │   │   ├── account.py       my account, my $ risk, my lot per signal, users (admin), Telegram link
│   │   │   ├── market.py        prices, candles, news
│   │   │   ├── settings.py      app settings, Telegram bot config / webhook / test
│   │   │   └── smc.py           the strategy: team read, overview, signals, history, results
│   │   ├── market/              market data
│   │   │   ├── data.py          candles and live prices (cache: M5 60 s, H1 5 min, D1 30 min), sessions
│   │   │   ├── oanda.py         OANDA feed (optional)
│   │   │   ├── pairs.py         the 28 forex pairs (Yahoo tickers)
│   │   │   ├── sanitize.py      candle cleaning (gaps, spikes; never vetoes on missing volume)
│   │   │   ├── news.py          ForexFactory high-impact calendar
│   │   │   ├── jsnum.py, types.py
│   │   ├── smc/                 the strategy and everything around it
│   │   │   ├── fxag/            ★ FX Alex G Set & Forget (section 3)
│   │   │   ├── desk.py          one pair's read: fetches candles, runs fxag, builds the JSON the app shows
│   │   │   ├── notify.py        every minute: reads the 29 pairs, sends new trades, saves the overview
│   │   │   ├── manager.py       follows every sent trade on M5 to TP / SL; history and win rate
│   │   │   ├── sizing.py        each user's lot from their own $ risk (saved once per signal)
│   │   │   ├── playbook.py      shared tools: candles, EMA, ATR, the trade follower `run()`
│   │   │   ├── skill/portfolio.py   one trade per pair at a time
│   │   │   ├── configs/<PAIR>.json  29 pair configs (pip, decimals, spread, pip value, lot step, currencies)
│   │   │   └── research/playbook.json  the last backtest numbers (shown in the app)
│   │   └── telegram/bot.py      bot commands (/risk …), linking chats to accounts, sending messages
│   ├── tests/                   pytest (61 tests; test_fxag.py = the strategy + the spec's 18 edge cases)
│   ├── requirements.txt
│   └── vercel.json              Python function + cron every minute
├── frontend/                    React 19 + Vite + Tailwind 4 + lightweight-charts
│   ├── src/                     (section 7)
│   └── vercel.json              /api/* rewritten to the backend
├── smc/                         research: backtests, reports, changelog
│   ├── tools/playbook_test.py   backtest on history (writes smc/PLAYBOOK.md + research/playbook.json)
│   ├── PLAYBOOK.md              last backtest
│   ├── FXAG_OPTIONS.md          why so few trades; what loosening a rule does
│   ├── LOSS_ANALYSIS.md         the previous strategy's analysis (history)
│   ├── CHANGELOG.md             every version
│   └── news/high_impact.csv     stored news calendar for backtests
├── docs/                        this file, DEPLOY notes, older architecture notes
└── DEPLOY_VERCEL.md             how the two Vercel projects are set up
```

---

## 3. The strategy: `backend/app/smc/fxag/` (2 agents)

The owner's specification of 2026-11-20 (`fx_alex_g_set_forget_ai_multi_agent_quantitative_specification.md`), grouped
into **2 agents** at the owner's request.

```text
fxag/
├── config.py           29 pairs, pip size, λ (gold 2.5, GBPJPY/AUD/NZD 1.25), shards, "500" steps, every threshold
├── time_utils.py       New York 17:00 daily close (DST-aware), W / D / H4 / H2 buckets, sessions, blackouts, news window
├── strategy/           ── Agent 1 · Strategy & confirmation ──
│   ├── data.py         closed candles on 7 timeframes (W, D, H4, H2, H1, M30, M15), gaps / duplicates
│   ├── structure.py    body-only swings, alternating "True Elbows", HH/HL/LH/LL trend, chop & extreme filters,
│   │                   the W / D / 4H alignment table (full sync, HTF retracement, daily counter-trend)
│   ├── zones.py        W (150) / D (250) zones: ≥ 3 body touches, ≤ 60 λ pips, W+D merge, "500" level,
│   │                   ≤ 5 λ pips proximity, broken-zone suspension, opposing-weekly "No-Trap" runway
│   ├── confluence.py   live confluences (last 0–2 candles): 50 EMA, previous structure, 500 level, candle
│   │                   patterns, chart patterns → score % and grade A+ / A / B / C / D
│   ├── entry.py        shift of structure (body close) on M15 / M30 / H1, then engulfing on H1 / H2 / H4;
│   │                   a huge engulfing → 50 % limit (6 h)
│   └── checks.py       final confirmation gates: score ≥ 80, R:R, proximity, session, news (−45 / +30 min),
│                       spread, data gaps → APPROVE or veto codes
├── risk/               ── Agent 2 · Stop loss, take profit & lot ──
│   ├── levels.py       SL = structure − (6 λ pips + spread); TP = 4 λ pips before the next D / W structure,
│   │                   capped before an opposing weekly zone; R:R ≥ 2.0; seasonal risk % × grade; lot formula
│   └── order.py        the locked Set & Forget order: fixed id hash(pair, side, entry TF, candle), signal only
├── pair_actor.py       one pair at one close, in order: data → structure → zones → score → entry → risk → checks;
│                       its state: TIER_3_DORMANT → TIER_2_WATCHLIST → TIER_1_SNIPER_AOI → TIER_1_SOS_CONFIRMED
│                       → (AWAIT_PULLBACK_LIMIT) → SIGNAL_EMITTED → SET_AND_FORGET_LOCKED
└── engine.py           scan (replay of the history, no look-ahead), report (the 2 agents' live read), chart objects
```

**Owner's choices:** signals only (no broker) · every pair's trade (one per pair at a time) · each user's own $ risk
sizes the lot · notifications = the trade and its end (no radar, no break-even, no partial).

**Measured:** 1 trade in 2 years, 0 in the last 60 days (see `smc/FXAG_OPTIONS.md`).

---

## 4. What happens every minute

```text
Vercel Cron ─► /api/cron/tick ─► notify.tick()
                                   │
                                   ├─ for each of the 29 pairs (8 at a time): desk.team(pair)
                                   │     ├─ market/data.py: M5 (2000), H1 (6600), D1 (1600) closed candles
                                   │     ├─ fxag.engine.scan: every engulfing close → the 2 agents → trades (approved or not)
                                   │     ├─ fxag.engine.report: the live read (tier, 2 agents, grade, decision)
                                   │     └─ the pair's JSON (agents, setup rows, chart objects, signal)
                                   ├─ a new approved trade → saved (signals table) → Telegram + web push + app feed
                                   │     (a private chat also gets that user's own lot)
                                   ├─ manager.manage_all(): every open trade followed on M5 → FILLED / TP_HIT / SL_HIT /
                                   │     EXPIRED messages, result (R) saved
                                   └─ the overview of all pairs saved (setting "overview") + heartbeat (setting "engine")
```

---

## 5. API routes (all under `/api`, a login is needed except auth / health / cron)

| Area | Routes |
|---|---|
| Auth | `POST /auth/login`, `POST /auth/register`, `GET /auth/password-check`, `GET /auth/me`, `POST /auth/logout` |
| My account | `GET/PUT /me`, `GET/PUT /me/risk`, `GET /me/sizing/{signal_id}`, `GET /me/sizings`, `DELETE /me/telegram-link` |
| Users (admin) | `GET/POST /users`, `GET/PATCH/DELETE /users/{id}`, `POST /users/{id}/approve`, `DELETE /users/{id}/telegram-link` |
| Strategy | `GET /smc/team?symbol=` (one pair's read), `GET /smc/overview` (all pairs), `GET /smc/signals` (sent trades), `GET /smc/history` (history + win rate), `GET /smc/results` |
| Market | `GET /market/assets`, `/market/ticker`, `/market/prices`, `/market/candles`, `/exunu/candles`, `GET /news`, `POST /news/sync` |
| Settings / Telegram | `GET/PUT /settings`, `GET/POST /telegram/config`, `/telegram/bot-info`, `/telegram/switch-bot`, `/telegram/webhook`, `/telegram/test`, `/telegram/test-me`, `/telegram/subscribers`, `/telegram/bot`, `/telegram/connect` |
| Push | `GET /push/key`, `POST /push/subscribe`, `/push/unsubscribe`, `/push/test` |
| System | `GET /health`, `GET/POST /cron/tick`, `GET /cron/status` |

---

## 6. Database tables (`backend/app/models.py`)

| Table | Holds |
|---|---|
| `users` | accounts (status pending / approved, role, Telegram chat, own $ risk) |
| `sessions` | login tokens |
| `activation_keys` | sign-up keys |
| `subscribers`, `telegram_connect` | Telegram chats and their link to accounts |
| `push_subscriptions`, `push_sent` | phones / browsers for web push |
| `signals` | every trade sent (entry, SL, TP, state, outcome, R, steps sent) — the history |
| `user_signal_sizes` | each user's lot for each signal (saved once) |
| `settings` | key/value: telegram, overview, engine heartbeat, history start, … |
| `watermarks` | "already sent" marks |
| `trades`, `trader_files` | older features kept |

---

## 7. Frontend (`frontend/src/`)

| File | What it is |
|---|---|
| `main.tsx`, `App.tsx` | start, login gate, the pages |
| `api.ts`, `cache.ts` | calls to the backend; device cache (screens shown at once, refreshed behind) |
| `smcTeam.ts` | types and hook for a pair's strategy read |
| `components/DashboardView.tsx` | home: **PairsOverview** (all 29 pairs: price, trend, grade, agents, status, trade, my lot) + **TradeHistory** (history & win rate) + market clock + news |
| `components/ExunuTerminalView.tsx` | the chart page: pair bar, **PriceChart** (zones, levels, EMA 50, trade), **TeamCard** (the 2 agents, tier, grade bar, setup classes) |
| `components/TeamCard.tsx` | verdict, tier, grade bar (80 % B and 100 % A+ lines), 2 agent tiles with their checklist, the plan |
| `components/RiskSizing.tsx` | my $ risk setting and my lot per trade |
| `components/SignalToasts.tsx`, `NotificationBell.tsx` | new trade pop-ups with sound; the alerts list; Telegram / push tests |
| `components/AccountView.tsx`, `AdminView.tsx`, `TelegramSettingsModal.tsx` | my account, user admin, Telegram setup |
| `components/LoginScreen.tsx`, `PendingApproval.tsx` | sign in / sign up, waiting for approval |
| `chart/smcDrawing.ts`, `chart/smcOverlay.ts` | drawing zones, levels and trades on the chart |
| `design-system/`, `components/ui.tsx`, `layout/` | colors, shared pieces, page layout (desktop + phone) |
| `notifications.ts`, `livePrices.ts`, `instruments.ts`, `splash.ts` | push registration, live prices, pair list, intro screen |

Languages: French, English, Arabic (Darija).

---

## 8. Tests and research tools

| Command | What it does |
|---|---|
| `backend/.venv/Scripts/python -m pytest -q` (in `backend/`) | 61 backend tests |
| `node node_modules/typescript/bin/tsc --noEmit -p .` (in `frontend/`) | frontend type check |
| `python smc/tools/playbook_test.py feed` | backtest on the feed's history → `smc/PLAYBOOK.md` |

---

## 9. Main settings (Vercel backend environment)

`DATABASE_URL` (Neon), `CORS_ORIGINS`, `ADMIN_USERNAME`, `ADMIN_ACCESS_CODE`, `CRON_SECRET`, `SCHEDULER_ENABLED=false`,
`TELEGRAM_POLLING=false`, `TELEGRAM_WEBHOOK_URL`, `TELEGRAM_WEBHOOK_SECRET`. Frontend: `VITE_API_URL`.
