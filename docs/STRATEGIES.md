# LiquidityDissection — the strategies

Every pair runs **one** rule-based strategy designed from the pair's own behaviour, and only where that strategy held up
on history it was never tuned on. A pair where nothing held up gets **no strategy and no signal**: its chart, trend and
analysis only. Nothing else creates signals or sends Telegram messages. Every rule below is code
(`backend/app/strategies/pairs/`); every parameter lives in `pairs/config.py`. Same closed candles → same result.

| Pair | Strategy | Timeframe | Unseen 40 % of 2 years | Status |
|---|---|---|---|---|
| **XAU/USD** | Channel breakout in the trend | H1 | 87 trades · 47 % winners · **+31.3R** · 42 % reached 2R | 🟢 live |
| **EUR/USD** | Asian-session channel fade (00:00–06:00 GMT) | H1 | 107 trades · 43 % · **+19.9R** · 42 % reached 2R | 🟢 live |
| **GBP/USD** | Channel fade, ADX < 35 | H4 | 80 trades · 45 % · **+14.3R** · 38 % reached 2R | 🟢 live (fragile) |
| **AUD/CHF** | Asian-session channel fade (22:00–05:00 GMT) | H1 | 36 trades · 44 % · **+6.3R** · 44 % reached 2R | 🟢 live (small edge) |
| USD/CAD, NZD/USD, EUR/CHF, NZD/CAD, AUD/CAD | — | H4 chart | nothing held up | ⏸ no signals |

## How they were built

**1. Analysis.** For each pair, on 2 years of the app's own H1 and H4 candles: after a close beyond the 20-candle
channel, how often does price go 2 ATR further (follow) or 2 ATR back (fade) before 1 ATR the other way? At 2:1 the
break-even is 33 %. Also the variance ratio over a day (VR(24): above 1 trends, below 1 comes back) and the most active
hours.

| Pair | Follow | Fade | Character | VR(24) H1 | Most active (GMT) |
|---|---|---|---|---|---|
| XAU/USD | 40 % (H4) | 28 % | trending | 1.13 | 12:00–16:00 |
| USD/CAD | 36 % (H4) | 26 % | trending | 0.88 | 12:00–17:00 |
| EUR/USD | 32 % (H1) | 36 % | mixed | 0.89 | 07:00–08:00, 12:00–15:00 |
| GBP/USD | 32 % (H4) | 35 % | mixed | 0.90 | 07:00–08:00, 12:00–15:00 |
| NZD/USD | 34 % (H4) | 33 % | mixed | 1.04 | 01:00, 07:00, 12:00–15:00 |
| EUR/CHF | 26 % (H4) | 39 % | reverting | 0.76 | 07:00–09:00, 13:00–15:00 |
| NZD/CAD | 27 % (H4) | 36 % | reverting | 1.01 | 12:00–15:00, 21:00–22:00 |
| AUD/CAD | 20 % (H4) | 43 % | reverting | 0.97 | 00:00–01:00, 12:00–15:00 |
| AUD/CHF | 19 % (H4) | 43 % | reverting | 0.82 | 07:00–08:00, 13:00–15:00 |

**2. Design.** The family the behaviour favours: a **breakout** in the trend for trending pairs, a **fade** of the
stretched close for reverting pairs, both for the mixed ones. Round 1: channel fade, liquidity sweep, channel breakout,
EMA pullback, Asian-range breakout. Round 2 (for the pairs round 1 left without an edge): previous-day high / low sweep
and break, Asian-session fade, RSI pullback in the higher-timeframe trend. Every target is **2R**.

**3. Test.** Tuned on the **first 60 %** of the 2 years only, then judged on the **last 40 %** it never saw, with the
pair's spread + slippage, the stop counted first when both levels sit in one candle, one trade at a time. A plan is live
only if it is positive on the unseen part, still positive with double costs, and its neighbouring settings agree
(a lone lucky setting is not an edge). The app's own engine replays each plan over the 2 years to the same result
(gold 230 trades +51.2R, EUR/USD 265 +40.0R, GBP/USD 215 +33.8R, AUD/CHF 107 +31.4R).

The research also showed the previous strategies decaying: GBP/USD's London breakout, positive in the first 60 %, lost
in the last 40 % in every variant.

## XAU/USD — "Channel breakout in the trend" H1

Gold trends: a close beyond its channel in the trend runs on more often than it comes back.

1. **Trend:** EMA50 above EMA200 on H1 for buys, below for sells.
2. **Entry:** an H1 candle closes above the highest high (below the lowest low) of the previous 20 H1 candles → MARKET
   at that close.
3. **Stop:** 2 × ATR(14, H1) from the entry (room for the New York noise). **Target:** 2R (4 ATR, covered within two
   days on gold). Closed at market after 48 H1 candles.

Tuned 142 trades +24.9R · unseen 87 trades +31.3R · double costs +53.7R. Every channel (10 / 20 / 40 / 55) and stop
(1 / 1.5 / 2 ATR) is positive on the unseen part (+21R to +57R). Max drawdown over the 2 years in the app replay: 16.5R.

## EUR/USD — "Asian-session channel fade" H1

No clear lean over the whole day, but in the quiet Asian hours a stretched close has no news or volume behind it.

1. **Window:** the H1 candle opened between 00:00 and 06:00 GMT.
2. **Entry:** it closes above the highest high (below the lowest low) of the previous 10 H1 candles → SELL (BUY) MARKET
   at that close.
3. **Stop:** 1.5 × ATR(14, H1) beyond the entry. **Target:** 2R, back across the channel. Closed after 48 H1 candles.

Tuned 160 trades +26.3R · unseen 107 trades +19.9R · double costs +26.3R. Every Asian window (21–06, 22–05, 00–06)
is positive on both parts (+13R to +26R). Tighter stops (0.6 / 1 ATR) lose.

## GBP/USD — "Channel fade" H4

GBP/USD's H4 closes beyond the 10-candle channel come back more often than they run, unless a strong trend is under way.

1. **No strong trend:** ADX(14, H4) below 35.
2. **Entry:** an H4 candle closes above the highest high (below the lowest low) of the previous 10 H4 candles → SELL
   (BUY) MARKET at that close.
3. **Stop:** 1 × ATR(14, H4) beyond the entry. **Target:** 2R. Closed after 12 H4 candles (2 days).

Tuned 144 trades +27.4R · unseen 80 trades +14.3R · double costs +29.3R. Positive on both parts with ADX < 25, < 35 or
none. **Fragile:** a 0.6 ATR stop or a 20-candle channel lose; only the 10-candle channel with a 1 ATR stop holds.

## AUD/CHF — "Asian-session channel fade" H1

The most reverting pair of the nine.

1. **Window:** the H1 candle opened between 22:00 and 05:00 GMT.
2. **Entry:** it closes beyond the previous 40 H1 candles' high / low → faded at that close.
3. **Stop:** 1 × ATR(14, H1). **Target:** 2R. Closed after 48 H1 candles.

Tuned 70 trades +25.7R · unseen 36 trades +6.3R · double costs +16.4R. Every Asian window is positive on both parts
with a 40-candle channel. **The weakest of the four:** a small edge on few unseen trades.

## The pairs without a strategy

| Pair | Why no strategy |
|---|---|
| USD/CAD | Trending on H4, but no breakout or pullback held up on the unseen 40 % (the best, a previous-day-high break in New York, +4R on 37 trades with most neighbours losing) |
| NZD/USD | No lean either way (34 % follow vs 33 % fade): no design held up (a fade that made +22R in the tuning lost −11R) |
| EUR/CHF | Reverting, but the fades that won in the tuning lost on the unseen 40 % (−5R to −37R) |
| NZD/CAD | Reverting, but no fade or sweep held up on the unseen 40 % |
| AUD/CAD | The strongest fade profile (43 %), but every fade lost on the unseen 40 % once costs are counted |

They keep the H4 chart, the EMA50 / EMA200 trend and the analysis card; the strategy agent refuses any trade on them.

## The agents

- **Market analysis:** daily trend, volatility regime, high-impact news. It objects to a *trend* trade against the daily
  trend; a *fade* trades against the move by design (that is how it was tested), so the daily trend only informs it.
- **Strategy:** knows each pair's plan and re-checks the setup against it: a validated plan, the stop at the plan's ATR
  multiple, the one 2R target, the plan's hours.
- **Risk & execution:** the trade desk (live price drift, live R:R, market open, currency exposure, open book).
- **Trade management** (after the entry): the stop and the target never move; it follows R, news, the time limit.

The plans were tested without the agents' vetoes (news ±30 min aside): the vetoes are safety, not the edge.

## Risk (all)

One target at 2R, no partial closes, no breakeven. Risk 1 % per trade (the lot table). Max 2 trades per day per pair,
stop after 2 losses in a day, no trade ±30 min around high-impact news of the pair's currencies. Each user chooses the
lot they took on a signal in the app; P&L = price move × lots × contract size (gold 100 oz, forex 100,000 units),
converted to USD for CAD- and CHF-quoted pairs. Each user's daily loss limit blocks new trades for the rest of the day.

**Limits of the test:** 2 years of Yahoo / COMEX candles (not broker data), a fixed spread, no past news filter, and a
40 % unseen part of 8–10 months. A positive test is evidence, not a guarantee: past results do not guarantee future
results.

## On the chart (`frontend/src/chart-overlays/drawingsPrimitive.ts`)

The pair's channel high / low (the levels the plan waits for), EMA 50 / 200, the signal marker ("Breakout" or "Fade")
and the TradingView-style position box (red SL zone, green TP zone, R:R and lot size). The side panel shows the
"Pair strategy" card: the analysis, the plan and its tuned vs unseen test. Clicking any drawing asks the agent to explain it.

## The agent (`backend/app/agent/`)

- `system_prompt.py`: every pair's plan, analysis and test, generated from `pairs/config.py`.
- `agent.py`: builds the JSON the agent reads and answers in Darija / French / English: Strategy → Bias → Setup checklist → Plan (or NO TRADE + the missing rule) → Risk.
- `validator.py`: re-checks every signal before Telegram; it can only lower the score or reject.

## Backtest

`backend/app/backtest.py` replays the same strategy code bar by bar (`backend/app/strategies/replay.py`) with the
config's spread and slippage: `python -m app.backtest XAUUSD`.

## Review mode

Open the app with `?asOf=<unix seconds>` to see any past moment exactly as the strategy saw it.
