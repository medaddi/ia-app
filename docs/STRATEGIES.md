# LiquidityDissection — the strategies

Every pair runs **one** rule-based strategy designed from the pair's own behaviour, and only where that strategy held up
on history it was never tuned on. The pairs where nothing held up (USD/CAD, NZD/USD, EUR/CHF, NZD/CAD, AUD/CAD) were
**removed from the app**. Nothing else creates signals or sends Telegram messages. Every rule below is code
(`backend/app/strategies/pairs/`); every parameter lives in `pairs/config.py`. Same closed candles → same result.

| Pair | Strategy | Timeframe | Unseen 40 % of 2 years | Status |
|---|---|---|---|---|
| **XAU/USD** | Channel breakout in the trend | H1 | 87 trades · 47 % winners · **+31.3R** · 42 % reached 2R | 🟢 live |
| **EUR/USD** | Agent 1 · Asian_Sweep_FVG_Engine | M5 | new: replayed on the feed's 60 days of M5 | 🟢 live |
| **GBP/USD** | Agent 2 · London_Judas_SMT_Engine (+ EUR/USD SMT) | M5 | new: replayed on the feed's 60 days of M5 | 🟢 live |
| **AUD/CHF** | Agent 3 · Mean_Reversion_Range_Engine | H4 → H1 | new: replayed on 2 years of H1 | 🟢 live |
| USD/CAD, NZD/USD, EUR/CHF, NZD/CAD, AUD/CAD | — | — | nothing held up | ✖ removed from the app |

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

## The three pair agents (EUR/USD, GBP/USD, AUD/CHF)

Each of these pairs is run by **its own agent** that reads **its own strategy** (`backend/app/strategies/engines/`,
plans in `engines/config.py`). Each strategy is a state machine on closed candles; the sessions follow **London's clock**
(DST included): that is Morocco's clock (UTC+1) in summer, and one hour behind Morocco in winter, when London opens at
09:00 Morocco time. The building blocks (`engines/primitives.py`):

| Term | Rule in the code |
|---|---|
| Swing high / low (fractal 5) | `High[k]` above the 2 candles on each side (low: below); known at `k + 2` |
| Sweep | price trades beyond the level, the strategy waits for the close back inside |
| MSS | a candle **close** beyond the last swing formed before the sweep |
| FVG | bullish `Low[k] > High[k-2]`, bearish `High[k] < Low[k-2]`; 50 % = middle of the gap |

### Agent 1 · EUR/USD — `Asian_Sweep_FVG_Engine` (M5)

1. **07:00** Asian_High / Asian_Low of 00:00–07:00 (M5 extremes = M15 extremes). Range outside **12–45 pips** → no trade today.
2. **08:00–11:00** (London) and **13:30–16:00** (New York): the Asian high (low) taken by **at most 20 pips** (more = a real breakout, that side is dead for the session).
3. **MSS on M5**: a close below (above) the last swing low (high) formed before the sweep, with an FVG **> 2.5 pips** in the leg (the last one is used).
4. **LIMIT at the FVG's 50 %**; deleted after **12 M5 candles**, if the target is reached first, or 15 min before red news.
   SL = sweep extreme ± **3 pips** (max **18 pips**). TP = the other side of the Asian range, **R:R ≥ 2**. Stop to
   break-even at the Asian 50 % or 1R, whichever comes first. One setup per session window.

### Agent 2 · GBP/USD — `London_Judas_SMT_Engine` (M5, + EUR/USD M5)

1. Before 08:00: **PDH / PDL** and the **Asian high / low (00:00–07:30)** of GBP/USD **and** EUR/USD.
2. **08:00–10:00**: GBP/USD takes a level by **5–30 pips** while **EUR/USD does not take its matching level** (SMT
   divergence). The opposite divergence (EUR/USD breaks, GBP/USD does not) gives no GBP/USD fakeout and is not traded.
3. **MSS on M5**: a close back inside the level and beyond the last swing; the leg longer than **1.5 × ATR(14) M5**.
4. **Order block** = the last up (down) candle before the leg; **LIMIT at its open** (`obEntry: "mid"` = 50 % of the body).
   SL = fakeout extreme ± **4 pips**, **15–28 pips** (a tighter stop is widened to 15; wider than 28: no trade).
   TP **3R**, stop to break-even at **1.5R**; deleted after 12 M5 candles or if 3R comes first.

### Agent 3 · AUD/CHF — `Mean_Reversion_Range_Engine` (H4 → H1)

1. **H4** (built from H1): **ADX(14) < 28**. Zones on the last 60 H4: resistance `Highest − 0.8 × ATR_H4` → `Highest`,
   support `Lowest` → `Lowest + 0.8 × ATR_H4`.
2. **RSI divergence on H1**: the current swing low in the support zone, a previous swing low 5–30 H1 candles before:
   `Low_now ≤ Low_prev`, `RSI_now > RSI_prev + 3`, `RSI_prev < 35` (mirror at resistance with `RSI_prev > 65`).
3. **Engulfing H1** after the divergence is confirmed (within 8 candles, the swing not broken): body covers the previous
   body, range **> 0.7 × ATR_H1(14)**.
4. **MARKET** at the engulfing close. SL = extreme ∓ **1.2 × ATR_H1**. **TP1** the range's middle (close 50 %, stop to
   break-even), **TP2** the start of the opposite zone, blended **R:R ≥ 1.8**.

### Global Risk & Execution Manager (`backend/app/agent/risk_manager.py`)

Checked by the risk agent before any order leaves the app:

- **Lot** sized for **1 %** of the account on every order (never a fixed lot).
- **Spread guard**: no entry above **1.5** pips (EUR/USD), **2.2** (GBP/USD), **3.0** (AUD/CHF).
- **USD correlation**: while EUR/USD or GBP/USD has an order not yet at break-even (PENDING / OPEN), a new order on the
  other one in the same dollar direction is refused (USD exposure ≤ 1 %).
- **News**: no new trade **30 min before / after** a red event of the pair's currencies; pending limits deleted **15 min before**.
- **Circuit breaker**: **2 trades per pair a day**; once the day's closed trades reach **−2.5 %**, every agent is locked
  until **00:00 London**.

These agents are new: they have no 2-year test yet (the M5 history of the feed is 60 days). The app shows their own
replayed record on that history (the same code as live), not a tuned/unseen split.

## The pairs removed from the app

| Pair | Why no strategy |
|---|---|
| USD/CAD | Trending on H4, but no breakout or pullback held up on the unseen 40 % (the best, a previous-day-high break in New York, +4R on 37 trades with most neighbours losing) |
| NZD/USD | No lean either way (34 % follow vs 33 % fade): no design held up (a fade that made +22R in the tuning lost −11R) |
| EUR/CHF | Reverting, but the fades that won in the tuning lost on the unseen 40 % (−5R to −37R) |
| NZD/CAD | Reverting, but no fade or sweep held up on the unseen 40 % |
| AUD/CAD | The strongest fade profile (43 %), but every fade lost on the unseen 40 % once costs are counted |

They are no longer analysed, charted or sent to Telegram. EUR/CHF is still read as a price feed only, to convert AUD/CHF's profit from francs to dollars.

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
