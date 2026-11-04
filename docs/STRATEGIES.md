# LiquidityDissection — the 4 autonomous pair agents

Each instrument is run by **its own agent** (`backend/app/agents/`) with **its own deterministic strategy** and **its own
chart**. Nothing else creates signals. Same closed candles → same result. Every session time is **UTC+1 (Morocco time)**,
a fixed offset (`core/quant_primitives.py`, `TZ_OFFSET_SEC`).

Each agent runs the plan its pair's behaviour favours, kept because it held up on the **last 40 % of 2 years of H1 / H4
it was never tuned on** (with the pair's spread + slippage, the stop counted first, one trade at a time). The M5 SMC
agents that ran before could only be tested on the ~60 days of M5 the free feed keeps, and placed no filled trade there.

| Pair | Agent | Decides on | App replay, ~2 years | Unseen 40 % |
|---|---|---|---|---|
| XAU/USD | `XAUUSD_TrendBreakout_Agent` | H1 | 223 trades · 44.8 % · **+50.1R** · PF 1.41 · max DD 16.5R | 87 trades · **+31.3R** |
| EUR/USD | `EURUSD_AsianFade_Agent` | H1, 00–06 GMT | 254 trades · 40.6 % · **+38.6R** · PF 1.24 · max DD 13.9R | 107 trades · **+19.9R** |
| GBP/USD | `GBPUSD_ChannelFade_Agent` | H4 | 171 trades · 40.8 % · **+20.6R** · PF 1.20 · max DD 10.7R | 80 trades · **+14.3R** |
| AUD/CHF | `AUDCHF_AsianFade_Agent` | H1, 22–05 GMT | 100 trades · 47.0 % · **+35.3R** · PF 1.63 · max DD 7.6R | 36 trades · **+6.3R** |

Every target is **2R**: a 41–47 % win rate is profitable at 2:1 (break-even 33 %). Past results do not guarantee future
results.

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
an ATR multiple, one target at 2R, closed at market at the plan's time limit. No partials, no break-even.
States: `IDLE` (outside its hours) · `ARMED` (watching the channel) · `COOLDOWN` (a strong trend for a fade) · `IN_TRADE`.

### XAUUSD_TrendBreakout_Agent (H1)
Gold trends: a close beyond its channel runs on 40 % of the time against 28 % that comes back.
1. Trend: EMA50 above EMA200 (H1) for buys, below for sells.
2. Entry: an H1 close beyond the **20-candle** high (buy) / low (sell) → MARKET at that close.
3. Stop **2 × ATR(14, H1)** · TP **2R** · closed after **48 H1 candles**.
- Tuned 142 trades +24.9R · unseen 87 trades +31.3R · every channel (10–55) and stop (1–2 ATR) positive on the unseen part.

### EURUSD_AsianFade_Agent (H1)
No lean over the day, but a stretch in the quiet Asian hours has no volume behind it and comes back.
1. Window: the H1 candle opened **00:00–06:00 GMT** (01:00–07:00 Morocco).
2. Entry: it closes beyond the **10-candle** high (sell) / low (buy) → MARKET at that close.
3. Stop **1.5 × ATR(14, H1)** · TP **2R** · closed after **48 H1 candles**.
- Tuned 160 trades +26.3R · unseen 107 trades +19.9R · every Asian window positive on both parts.

### GBPUSD_ChannelFade_Agent (H4)
H4 closes beyond the channel come back more often than they run, unless a strong trend is under way.
1. No strong trend: **ADX(14, H4) < 35** (else COOLDOWN).
2. Entry: an H4 close beyond the **10-candle** high (sell) / low (buy) → MARKET at that close.
3. Stop **1 × ATR(14, H4)** · TP **2R** · closed after **12 H4 candles** (2 days).
- Tuned 144 trades +27.4R · unseen 80 trades +14.3R. **Fragile:** only the 10-candle channel with a 1 ATR stop holds.

### AUDCHF_AsianFade_Agent (H1)
The most reverting pair: a close beyond its channel comes back 43 % of the time against 19 % that runs on.
1. Window: the H1 candle opened **22:00–05:00 GMT** (23:00–06:00 Morocco).
2. Entry: it closes beyond the **40-candle** high (sell) / low (buy) → MARKET at that close.
3. Stop **1 × ATR(14, H1)** · TP **2R** · closed after **48 H1 candles**.
- Tuned 70 trades +25.7R · unseen 36 trades +6.3R. **The weakest edge of the four.**

Draws (every agent): the channel high / low it watches, the broken level and the `BREAKOUT` / `FADE` marker at the
signal, and the trade box.

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
