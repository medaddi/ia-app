# LiquidityDissection — the 4 autonomous pair agents

Each instrument is run by **its own agent** (`backend/app/agents/`) with **its own deterministic strategy** and **its own
chart**. Nothing else creates signals. Same closed candles → same result. Every session time is **UTC+1 (Morocco time)**,
a fixed offset (`core/quant_primitives.py`, `TZ_OFFSET_SEC`).

Each agent runs the plan its pair's behaviour favours, chosen for a **high win rate that still makes money**: tuned on the
first 60 % of 2 years of H1 / H4 (win ≥ 55 %, expectancy ≥ +0.08R per trade, ≥ 40 trades), kept only if it **also won
≥ 55 % and made money on the last 40 % it never saw**, stayed positive with double costs, and most of its neighbouring
settings agreed (the pair's spread + slippage, the stop counted first, one trade at a time).

| Pair | Agent | Plan | Target | App replay (~2 years) | Unseen 40 % |
|---|---|---|---|---|---|
| XAU/USD | `XAUUSD_FastIntraday_Agent` | **Fast, every trade closed within 3 h** (3 H1 candles). Asian breakout 00–06 GMT: H1 close beyond the 40-candle channel in the EMA50 / EMA200 trend · SL 1.5 ATR · 1.5R. London dip 07–11 GMT: H1 close beyond the 5-candle range against the EMA200 side, faded in the trend · SL 1 ATR · 1.25R | 1.25–1.5R | 210 trades · **60.0 %** · +41.9R · PF 1.75 · DD 3.9R | 84 trades · 61.9 % · +18.6R |
| EUR/USD | `EURUSD_AsianFade_Agent` | H1 fade of the 10-hour channel, 00–06 GMT, ADX < 35 · SL 2 ATR · 48 candles | 1R | 212 trades · **57.1 %** · +21.6R · PF 1.23 · DD 6.7R | 90 trades · 56.7 % · +6.1R |
| GBP/USD | `GBPUSD_TrendPullback_Agent` | H1 fade of the 40-hour channel in the trend's direction (EMA200), ADX < 35 · SL 1.5 ATR · 48 candles | 1.25R | 75 trades · **60.0 %** · +21.6R · PF 1.68 · DD 3.8R | 29 trades · 65.5 % · +11.1R |
| EUR/CHF | `EURCHF_AsianFade_Agent` | H1 fade of the 10-hour channel, 00–06 GMT · SL 1 ATR · 24 candles | 0.75R | 131 trades · **67.9 %** · +17.4R · PF 1.39 · DD 3.9R | 64 trades · 79.7 % · +15.0R |
| AUD/CAD | `AUDCAD_RangeFade_Agent` | H1 fade of the 40-hour channel · SL 1 ATR · 48 candles | 0.75R | 376 trades · **67.0 %** · +48.7R · PF 1.37 · DD 7.6R | 165 trades · 70.9 % · +21.5R |
| AUD/CHF | `AUDCHF_RangeFade_Agent` | H1 fade of the 40-hour channel, ADX < 35 · SL 1.5 ATR · 48 candles | 0.75R | 250 trades · **70.0 %** · +49.9R · PF 1.65 · DD 7.2R | 106 trades · 73.6 % · +20.0R |

**The trade-off:** a closer target wins more often and earns less per win; a loss always costs 1R. So a 70 % win rate at
0.75R is worth about +0.2R per trade, not a sure thing. No strategy guarantees profit: these are the plans that held
up on history they were never tuned on. Past results do not guarantee future results.

USD/CAD, NZD/USD and NZD/CAD: no plan won ≥ 55 % and made money on the unseen part, so they are not traded.

## 1. Instrument normalisation (`core/instrument_specs.py`)

| Symbol | Pip | Decimals | Max spread |
|---|---|---|---|
| EURUSD | 0.0001 | 5 | 1.5 pips |
| GBPUSD | 0.0001 | 5 | 2.2 pips |
| AUDCHF | 0.0001 | 5 | 3.0 pips |
| XAUUSD | 0.10 ($1.00 = 10 pips) | 2 | 3.5 pips |

`pips_to_price(symbol, pips)` and `price_to_pips(symbol, diff)` are used for every stop, buffer and zone width.

## 2. Quantitative primitives (`core/quant_primitives.py`)

- **5-bar fractal**: swing high at `[-3]` when `High[-3]` is above `High[-5]`, `High[-4]`, `High[-2]`, `High[-1]` (low: mirror). Known 2 candles after the pivot.
- **FVG** on `[-3] [-2] [-1]`: bullish `Low[-1] > High[-3]` (bottom `High[-3]`, top `Low[-1]`), bearish `High[-1] < Low[-3]`; `ce_50` = middle; min 2.5 pips forex, 6 pips ($0.60) gold.
- **Order block**: bullish MSS → the lowest bearish candle of the 10 before the break; bearish MSS → the highest bullish candle. `OB_Mean = (Open + Close) / 2`.
- **OTE** of a displacement leg: 0.618, 0.705 (sweet spot), 0.786 retracements.
- Wilder RSI / ATR / ADX (14).

## 3. The agents (`agents/channel.py`, `agents/plans.py`)

Each agent works like a disciplined trader: it **reads the market** first (the trend by EMA50 vs EMA200, the volatility
against its usual level, the session, the channel it watches and how far price is from it), **acts only on its edge**,
takes **one trade at a time** (while a trade runs it manages it and takes no other), and **plans the exit first**: stop at
an ATR multiple, one target (its plan's R), closed at market at the plan's time limit. No partials, no break-even.
States: `IDLE` (outside its hours) · `ARMED` (watching the channel) · `COOLDOWN` (a strong trend for a fade) · `IN_TRADE`.

- **Gold** is traded fast: every trade is closed within 3 hours (its stop, its target, or at market after 3 H1 candles).
  Two legs, one trade at a time: in the **Asian hours (00–06 GMT)** it buys a close above its 40-hour high in an uptrend
  (sells the mirror), never against the trend; at the **London open (07–11 GMT)** it buys a close below its 5-hour low
  above EMA200 (sells a close above its 5-hour high below it): the first push often overshoots and comes back. The
  afternoon and New York hours had no fast edge on gold, so it does not trade them. Search: breakout and fade, channels
  5–40, stops 0.5–1.5 ATR, targets 0.5–1.5R, held 2, 3 or 4 hours, in 6 session windows (21,600 combinations); both
  legs and every one-step neighbour of their settings were positive on the tuned and the unseen part, and with double
  costs (+37.4R). The 2-year test is on H1: free M5 / M15 history only goes back ~60 days, too short to prove a plan.
- **EUR/USD, EUR/CHF** fade a close beyond their 10-hour channel in the quiet Asian hours (00–06 GMT), when the move has
  no volume behind it.
- **GBP/USD** buys a close below its 40-hour low only above EMA200 (a dip in an uptrend), sells a close above its 40-hour
  high only below it, and stands aside when ADX ≥ 35.
- **AUD/CAD, AUD/CHF** (commodity / safe-haven crosses that swing in ranges) fade a close beyond their 40-hour channel at
  any hour; AUD/CHF only while ADX < 35.

Draws (every agent): the channel high / low it watches, the broken level and the `BREAKOUT` / `FADE` marker at the
signal, and the trade box.

### The SMC view (Exunu's method, `agents/smc.py`) — context, never a signal

The app's original Exunu engine traded Smart Money Concepts, but most of its checks were hard-coded to pass (a sweep was
"verified" even when none happened, missing order blocks and FVGs were invented, entry was always the current price), so it
emitted a trade at almost every refresh. Rebuilt with every check real — structure by confirmed 3-bar swings, a sweep of
the last swing low (high) closed back inside in that trend, the order block before it, entry at market or at the OB, stop
beyond, target 1R–2R — it **lost on every pair** on 2 years of H1 / H4 (unseen part: gold −6.1R, EUR/USD −7.6R, GBP/USD
−7.5R, EUR/CHF −17.7R, AUD/CAD −1.5R, AUD/CHF −18.4R; 80 variants per pair, none profitable on both parts).

So the signals stay with the pair agents above, and Exunu's read is drawn on every chart as its own layer
("SMC view"): swing labels HH / HL / LH / LL, the latest BOS or CHoCH, the untaken buy-side (BSL) and sell-side (SSL)
liquidity, the order block behind the latest break and the latest unfilled FVG.

## 4. The chart contract

Every agent emits an `AgentChartOverlayState` (`frontend/src/agentOverlay.ts`): `fsmState`, `statusBannerText` (top-left
of its chart), `metrics` (spread, ATR, session, confluence tag), `zones`, `priceLines`, `markers` and
`tradeExecutionBox`. It is in every strategy result (`overlay`) and at `GET /api/agents/overlay?symbol=`. A chart renders
only its own agent's state, in the single view and in the 4-chart split screen.

## 5. Risk notes (`core/risk_guard.py`) — nothing blocks a setup

Every fresh setup an agent sees is sent. **Each trader controls their own risk**: their $ or % per trade on their
account (and `/risk` on Telegram) sizes their lot. The lot table of a signal is for 1 % of the balance.

With each order the trader gets notes, never a veto: the agent's rules re-checked and fresh data, the limit still
valid / a market entry not chased, red news of the pair's currencies within ±30 min, the spread, the other open
same-direction USD trades not yet at break-even (EURUSD, GBPUSD and XAUUSD share the dollar), the orders open on the desk
and today's result. A pending limit keeps its own expiry (12 M5 bars, 90 min for GBP/USD), even with news ahead.

## 6. Trade-management agents (`agents/trade_manager.py`) and delivery

The setup agents only look for setups and keep scanning while their earlier trades run: **every setup becomes an
order**, several can run at once on a pair. Next to each setup agent a **trade-management agent** runs every trade
that was sent: at each tick it replays the trade on the latest candles and tells the traders, once per step, on Telegram
and on the app (Web Push): 🟡 order filled · 🎯 TP1 hit (close 50 % / move the SL to break-even, +2 pips on gold) ·
📈 +1R · ⚠️ near SL · 📰 news in N min · ⌛ order expires soon · and how the trade ended (TP / SL / BE / cancelled).

Delivery of a new setup, at the candle close where it completes:
1. the trade is **recorded first** (the trade-management agent and the app follow it from there, Telegram on or off);
2. Telegram and the app's Web Push are sent **independently** (one failing never stops the other);
3. a Telegram attempt that reached nobody is **retried at each tick** for 15 minutes; a push that failed is retried too.

On Vercel the tick is the cron `/api/cron/tick` every minute (`backend/vercel.json`, Vercel Pro).

## 7. Testing

`backend/tests/test_four_agents.py` builds each agent's setup by hand and checks the order, the lifecycle and the chart
overlay; the replay (`strategies/replay.py`) runs the same code bar by bar. `GET /api/backtest?symbol=` replays the
agent on the feed's history (60 days of M5, 2 years of H1). Losses happen; nothing here is a guaranteed result.
