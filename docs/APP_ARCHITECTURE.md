# LiquidityDissection — the whole app, A to Z

A briefing for another AI (or developer). State: 2026-11-11, branch `medv` (the only branch pushed). Research software:
it analyses markets and sends trade ideas; **it never places an order**.

## 1. What the app is

A private web app (plus a Telegram bot) for **29 instruments**: XAU/USD and the 28 forex pairs of USD, EUR, GBP, JPY, CHF,
CAD, AUD, NZD. Every instrument runs ONE strategy, **FXAlexG "Set & Forget"** (`backend/app/smc/alexg.py`), read by a team
of **5 deterministic agents** (code, not LLM calls): `trend_director`, `aoi_architect`, `confluence_grader`,
`trigger_sniper`, `risk_guardian`. The UI shows each pair's live chart with the analysis drawn on it, the 5 agents, the
grade and confluence bar, and the setup. Alerts go to Telegram, web push and an in-app toast. A trade manager follows each
sent setup on M5 candles; the app's real win rate comes from those results.

## 2. Stack and deployment

| Part | Tech | Where |
|---|---|---|
| Backend | Python 3.12, FastAPI, SQLAlchemy 2, httpx, pywebpush | `backend/` -> Vercel, `https://ia-app-tawny.vercel.app` |
| Database | PostgreSQL (Neon) in production; SQLite `backend/data/exunu.db` locally | env `DATABASE_URL` |
| Frontend | React 19, Vite 6, Tailwind 4, TypeScript, lightweight-charts v5 | `frontend/` -> Vercel, `https://liquiditydissection.app` |
| Research | Python scripts over CSV candles | `smc/` (not deployed) |

`frontend/vercel.json` rewrites `/api/*` to the backend. `backend/vercel.json` declares a cron every minute on
`/api/cron/tick` (Bearer `CRON_SECRET`); on an always-on server `main.py` runs the loop itself. Env: `backend/.env.example`
(`DATABASE_URL`, `ADMIN_*`, `CORS_ORIGINS`, `TELEGRAM_*`, `CRON_SECRET`, `PUBLIC_APP_URL`, `OANDA_API_TOKEN`, `OANDA_ENV`).
`mobile/`, `android-project/`, the Firebase files and `docs/STRATEGIES.md` are leftovers of older versions.

## 3. Repository map

```
backend/app/
  main.py, config.py, db.py, models.py, auth.py, store.py, push.py
  api/        account.py, market.py, settings.py, smc.py
  market/     data.py (prices, candles, caches) · oanda.py (primary feed when OANDA_API_TOKEN is set) · sanitize.py
              (UTC grid, duplicates, bad ticks, gaps) · news.py (ForexFactory) · pairs.py (the 28 pairs) · types.py
  smc/
    alexg.py     THE engine: bodies, elbows, structure, AOIs, confluences, the two-step trigger, the plan, the 5 agents
                 (squad), scan (history + live), report (pairReport), draw_objects (chart)
    playbook.py  shared pieces: resample, ema, atr, run() (the trade followed on M5), _make, the registry (STRATEGIES)
    desk.py      one team read: team(pair) / read_team(...): candles -> alexg.scan -> alexg.report -> chart -> JSON
    notify.py    tick(): radar, signal, then the trade manager; broadcast to Telegram + push; recent(), recent_radar()
    manager.py   follows each sent setup (FILLED, BREAKEVEN +1.5R, TP_HIT, SL_HIT, BE_CLOSED, EXPIRED), saves results
    skill/portfolio.py   cross-team check: one trade per pair, <= 2 same-way bets per currency, 3 % total, 5 a day
    skill/cot.py         CFTC positioning (not used by the 5 agents)
    configs/<PAIR>.json  pip, decimals, psych_step, max_aoi_pips, spread_pips, currencies, oanda, yahoo
    research/playbook.json   the one-year test results (written by smc/tools/playbook_test.py)
  telegram/bot.py   link a chat to an account, info commands, webhook or polling
backend/tests/      40 tests: test_alexg.py, test_notify_pipeline.py, test_feed.py, test_skill.py, others
frontend/src/
  App.tsx (views, SignalToasts) · components/ExunuTerminalView (pair tabs, charts, team) · PriceChart · TeamCard (5 agents,
  grade, confluence bar) · SignalToasts (in-app toast) · DashboardView · chart/smcDrawing.ts + smcOverlay.ts ·
  smcTeam.ts (team types, polling) · instruments.ts (29 symbols, decimals, timeframes)
smc/                pairs/<PAIR>/config.json + data (gitignored candles; 6 pairs have one year of Dukascopy) ·
                    news/high_impact.csv · tools/fetch_dukascopy.py, playbook_test.py · CHANGELOG.md · PLAYBOOK.md
```

## 4. Data layer

Live price: OANDA M1 mid + spread when the token is set; else gold-api (gold) / one Yahoo request for all pairs.
Candles `fetch_candle_series(symbol, tf, limit)`: OANDA v20 (mid, bid/ask spread, UTC aligned, backfill) when the token
is set, else Yahoo (gold = COMEX GC=F shifted to spot). Caches: W1 / D1 30 min, H1 5 min, M5 60 s, each ending just after
its next candle closes. Every intraday series passes `sanitize()`. JPY pairs use 3 decimals, gold 2, the rest 5. Only
CLOSED candles reach the teams. News: ForexFactory weekly high-impact events, by the pair's currencies.

## 5. The strategy and the team

**The engine (alexg.py)**, on closed candles, three setup types: **SF_BR** (break & retest continuation), **SF_BOUNCE**
(direct pro-trend AOI bounce), **SF_COUNTER** (1D shifted against the 1W):
1. No-Gap candles (O' = previous close) for every candle pattern; the EMA 50 on closes on every timeframe.
2. Line-chart structure on CLOSES on W1 / D1 / H4 (pivots m = 2 / 3 / 3): bullish while HL <= close <= HH, bearish only on a
   close strictly below HL; HL is always behind HH in time (the mirror for LL / LH).
3. AOIs on W1 (120 bars) and D1 (250 bars) only: close + wick pivots in zones <= 0.35 ATR (D1); a touch = price enters and
   reverses 0.75 ATR (D1); >= 3 touches; a BUY zone inside the active [HL, HH], a SELL zone inside [LL, LH]; strong =
   W1 + D1 overlap or >= 5 touches; a round number (50 / 100 pips, gold $25 / $50) within 10 pips.
4. A closed confirmation on 2H / 1H / 30M / 15M at the AOI: doji / pinbar, engulfing (body >= 80 % of the previous and
   >= 50 % of its range), the LTF SoS, double top-bottom / H&S.
5. The 100-point GPA (9 items: 1W 10, 1D 10, 4H 10, AOI 10, strong AOI 10, HTF EMA 10, SoS / pattern 15, confirmation
   candle 15, LTF EMA + session 10). A+ >= 90, A >= 80, B >= 75, C+ >= 70, F below (no trade). Risk 1 / 1 / 0.75 / 0.5 %.
6. The plan: entry at the confirmation close (band +-0.15 ATR 1H); SL = min(Z_low, swing) - 0.20 ATR 1H - spread; TP 7 pips
   before the next opposing D1 / W1 zone or the round number inside it; RR >= 2.0. At +1.5 R the stop goes to the entry
   + 2 pips; a trade not in profit on Friday 20:00 UTC is closed. A confirmation outside 06:00-17:00 UTC waits for 06:00.

**The 5 agents** (`alexg.squad`): `trend_director` (1W / 1D / 4H sync), `aoi_architect` (in a valid AOI, psych),
`confluence_grader` (the GPA), `trigger_sniper` (the closed LTF trigger), `risk_guardian` (R:R >= 2, session 06-17 UTC,
Mon-Wed / Thursday grade A + target <= 1.2 ADR / no Friday entries, news +-30 min, rollover 21:45-22:15, spread <= 25 % of
SL). Each: status ok / warn / wait / veto, score 0-100, badge <= 55 chars, details. Consensus = 0.25 trend + 0.25 AOI +
0.20 grader + 0.20 trigger + 0.10 guardian. **EXECUTE** iff consensus >= 70, GPA >= 70, no veto, trigger and guardian ok.

**One read** (`desk.team(pair)`, cached 60 s): M5 2000, H1 4000 (4H / 2H aggregated), D1 900 (W1 resampled) ->
`alexg.scan` -> `alexg.report` -> chart objects -> JSON: `strategies` (one row per setup type), `signals`, `chart`,
`agents`, `grade`, `gpa`, `consensus`, `decision`, `setupType`, `checklist`, `radar`, `pairReport`.

**Alerts** (`notify.tick()`, every minute, 29 pairs read 8 at a time): 1 · AOI_WATCH_ALERT ("👀 [RADAR] ..."), once per
wave (watermarks); 2 · SIGNAL_EXECUTE after `portfolio.check` (1 per pair, <= 2 same-way bets per currency, <= 3 % total),
saved in `signals`, sent to Telegram (linked chats + admin), web push and the app; 3 · MANAGER_LIVE_UPDATE: FILLED,
BREAKEVEN LOCKED (+1.5R), TAKE PROFIT HIT, STOP LOSS HIT, CLOSED / EXPIRED.

## 6. Database tables

`users`, `sessions`, `activation_keys`, `subscribers`, `telegram_connect`, `push_subscriptions`, `push_sent`, `signals`
(each sent setup, its events and outcome), `trades`, `settings` (key/value; `radar` holds the last radar alerts),
`watermarks` (radar dedupe), `trader_files`. Created on startup.

## 7. HTTP API (under /api, bearer token unless public)

Health: `/api/health`, `/api/cron/status`, `/api/cron/tick`. Auth / account: `/auth/login|register|me|logout`, `/me`,
`/push/key|subscribe|unsubscribe|test`, `/telegram/bot|connect`, `/users...` (admin). Market: `/market/prices`,
`/market/candles`, `/exunu/candles?symbol=&timeframe=1M|5M|15M|1H|4H`, `/news`. Settings: `/settings`,
`/telegram/config|bot-info|switch-bot|webhook|test|subscribers`. Teams: `/smc/team?symbol=`, `/smc/results`,
`/smc/signals` (sent setups + `radar`).

## 8. Frontend

Login -> token in localStorage. Dashboard (prices, sent setups, results, news). Terminal: pairs grouped (Majors, JPY
Crosses, GBP/EUR Crosses, Commodity/CHF, Gold) with a "Sunday Swings" toggle (top 5 by consensus, signals and radars
first); chart tabs M15 | M30 | H1 | H2 | H4 | D1 | W1 | H4 + H1; the blue 50 EMA on every timeframe, AOI boxes with
touches and psych, HH / HL / LH / LL markers, the SoS line, the position box with the +1.5R line; the team card (5 agents
with score and weight, the GPA grade and bar, the 9-point checklist, the setup rows) and the bell (live alerts, Test
Telegram, Test Web Push). `SignalToasts` shows a toast with a sound for a new signal or radar. Languages: English,
French, Darija/Arabic.

## 9. Research loop

`python smc/tools/fetch_dukascopy.py` -> `smc/pairs/<P>/data/dukascopy/{M5,H1}.csv` (6 pairs so far).
`PYTHONPATH=. backend/.venv/Scripts/python smc/tools/playbook_test.py dukascopy` -> `smc/PLAYBOOK.md` and
`backend/app/smc/research/playbook.json`. No parameter is changed after seeing results.

## 10. Running it locally

```
backend:  cd backend && .venv/Scripts/python -m uvicorn app.main:app --port 8000   (or the "api-quiet" launch config)
frontend: cd frontend && npm run dev                                                (port 3000, proxies /api)
tests:    cd backend && .venv/Scripts/python -m pytest -q        types: cd frontend && npm run lint
```

## 11. Rules the owner set

Research, not advice; no orders. Push only to `medv`; commit only when asked. No secrets in the repo (test with
"api-quiet": the local DB holds a real bot token). No trades at high-impact news. Ask before a new data source.

## 12. Known limits (honest state)

- Dukascopy one year on 6 pairs (D1 / W1 from that year only): 16 trades, 19 % wins, -3.14R, PF 0.76. Yahoo last 60 days
  on 29 pairs (full W1 / D1): 29 trades, 21 % wins, +2.25R, PF 1.14. Small samples either way; the 23 new pairs have no
  stored year (Dukascopy refused the download with 503).
- OANDA is coded but off until its token is set; on Yahoo forex has no volume and gold is GC=F futures.
