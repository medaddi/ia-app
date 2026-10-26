# LiquidityDissection — the two strategies

The app runs **exactly two** rule-based strategies, one per instrument. Nothing else creates
signals or sends Telegram messages. Every rule below is code; every parameter lives in the
strategy's config file. Same closed candles → same result, every time.

| | XAUUSD (Gold) | EURUSD and GBPUSD (same rules) |
|---|---|---|
| Name | H1 Trend Breakout | Trend Pullback + London Breakout Filter |
| Code | `backend/app/strategies/xauusd/strategy.py` | `backend/app/strategies/eurusd/strategy.py` |
| Config | `backend/app/strategies/xauusd/config.py` | `backend/app/strategies/eurusd/config.py` |
| Timeframes | Trend, setup and entry on H1 | Bias D1 + H4 · Zones H1 · Entry M15 |
| Order | MARKET (close of the breakout candle) | MARKET (close of the confirmation candle) |

## Shared definitions (`backend/app/strategies/shared/`)

- **Swing high/low**: fractal with 3 candles on each side, strictly higher/lower; confirmed only after the 3 right-side candles close. Labelled HH / LH / HL / LL against the previous swing of the same kind.
- **BOS**: a candle **close** beyond the last confirmed swing, in the trend direction.
- **CHoCH / MSS**: the first candle **close** beyond the last confirmed swing **against** the current trend.
- **Liquidity sweep**: the first candle that trades beyond a key level wicks through it and **closes back inside**. A close beyond it is a break, not a sweep.
- **Key levels**: PDH/PDL and PWH/PWL (trading day rolls at 17:00 New York), Asian high/low (00:00–06:00 London), previous session high/low, equal highs/lows within 0.1 × ATR ("$$$"), and for gold $10 / $50 round numbers.
- **FVG**: candle 1 high < candle 3 low (bullish) or candle 1 low > candle 3 high (bearish); ignored below 0.25 × ATR(14); mitigated once 50% is filled.
- **Order block**: the last opposite-coloured candle before the displacement that caused a BOS/CHoCH; valid only if the displacement body > 1.5 × the 20-candle average body.
- **Sessions**: defined in Europe/London and America/New_York local time and converted to UTC with the real DST offset of each date (tests cover the March and October clock changes).
- **Score**: weighted checklist 0–100. **≥ 75 = SIGNAL** (sent to Telegram once), **60–74 = WATCH** (chart only), **< 60 = ignored**. Any failed *required* rule = **NO TRADE**.

## Strategy 1 — XAUUSD "H1 Trend Breakout"

1. **Trend (H1)**: BUY only if EMA 50 > EMA 200 **and** the H1 close is above EMA 200. SELL only on the mirror. Otherwise **NO TRADE**.
2. **Entry**: an H1 candle **closes** above the highest high (buys) / below the lowest low (sells) of the **previous 20 H1 candles**, with a body > **0.5 × ATR(14, H1)**. **MARKET entry** at that close; do not enter more than 30 minutes later.
3. **Stop**: beyond the lowest low (buys) / highest high (sells) of the last 4 candles, plus 0.2 × ATR. It must be at least **1 × ATR** from the entry. If it would be wider than **3 × ATR**, there is no trade.
4. **Targets**: TP1 = **1R** → close 50%, move the stop to the entry. TP2 = **2R** → close 25%. TP3 = **3R** → close the rest. TP distances are computed from the rounded entry and stop, so they are exactly 1R / 2R / 3R as printed.
5. **One gold trade at a time**: candles are replayed in order, and a new breakout only counts after the previous trade closed.
6. **Filters**: no trade 30 minutes before/after high-impact USD news (CPI, NFP, FOMC, Fed Chair, PCE, GDP); spread ≤ $0.50; max 3 trades per day; stop after 2 losses.
7. **Score weights**: trend 25, breakout 25, momentum (body / ATR) 20, stop 10, targets 20.

**Why this strategy.** The earlier gold model (sweep + MSS + FVG on M5) gave 0 signals in 68 days; 25+ looser variants added only losing trades. This model was chosen from a 2-year H1 test (Oct 2024 – Oct 2026, 11,466 candles, spread $0.25, slippage $0.05) among models fixed in advance:

| Test | Trades | Win rate | Total | Profit factor | Max drawdown |
|---|---|---|---|---|---|
| Research, all | 149 | 58% | +36.5R | 1.57 | 7.8R |
| 1st year / 2nd year | 79 / 70 | 57% / 59% | +17.4R / +19.2R | 1.50 / 1.66 | 7.8R / 3.8R |
| Buys / sells | 98 / 51 | 56% / 61% | +24.7R / +11.9R | 1.57 / 1.59 | — |
| Costs × 3 | 149 | 57% | +32.6R | 1.50 | 8.0R |
| App engine (replay, Dec 2024 – Oct 2026) | 144 | 57.6% | +35.3R | 1.57 | 7.85R |

7 of 9 quarters were positive (2025-Q2 −4.1R). Median stop $34 (10–90%: $14–$65), about 6 trades per month. Past results do not guarantee future results.

## Strategy 2 — EURUSD and GBPUSD "Trend Pullback + London Breakout Filter"

One forex strategy for both pairs: GBPUSD uses exactly the EURUSD rules and parameters
(`backend/app/strategies/gbpusd/config.py`); only the instrument and the news currencies (GBP + USD:
BoE, Bailey, MPC…) differ. Backtest on the same 74 days (Aug–Oct 2026, M15): EURUSD 3 signals, 3 wins,
+1.42R; GBPUSD 3 signals, 3 losses, −3.1R. Far too few trades to judge either pair; GBPUSD is
followed separately in the Performance page and in the bot's /stats.

1. **Bias (H4, with a Daily filter)** — bullish if the H4 close > EMA 200, EMA 50 > EMA 200, and the H4 swings are HH/HL; bearish is the mirror. Daily filter: no buy within 15 pips of daily resistance / PWH (no sell within 15 pips of daily support / PWL).
2. **Windows** — London 07:00–10:30 and the London/NY overlap 13:00–16:00 (London time). No new trades on Friday after 14:00 London.
3. **Setup A — trend pullback (main)**
   1. Trend confirmed (bias above).
   2. Pullback into **at least 2 of 3**: H1 order block, Fib 50–61.8% of the last H1 impulse leg, EMA 50 (M15).
   3. RSI(14, M15) at the pullback between 40–50 for buys, 50–60 for sells.
   4. Confirmation candle on M15: engulfing, pin bar (wick ≥ 2 × body), or M15 CHoCH.
   5. **MARKET entry** at the close of the confirmation candle.
4. **Setup B — Asian range false breakout (secondary)**
   1. Asian range 00:00–06:00 London, between 12 and 40 pips.
   2. In the London window, a candle breaks one side and **closes back inside**.
   3. Trade toward the other side **only if it matches the H4 bias**. TP2 = the opposite side of the range (R:R ≥ 1:2, else skip).
5. **Risk**
   - SL beyond the zone/swing + 3 pips, or 1.5 × ATR(14, M15), **whichever is wider**; must be **8–25 pips**.
   - TP1 = 1R (close 50%, SL to breakeven). TP2 = next H1 level at ≥ 2R, else 2R. TP3 = trail behind confirmed M15 swings (3R shown as a reference). Minimum R:R 1:2.
6. **Filters** — no trade 30 minutes around high-impact EUR/USD news (ECB, Lagarde, EU/US CPI, NFP, FOMC); spread ≤ 1.5 pips; max 3 trades per day; stop after 2 losses.
7. **Score weights** — bias 15, window 10, zone confluence 20, trigger 15, momentum (RSI) 10, R:R 15, room to the next H1 level 10, volatility 5.

## Risk (both)

1% of equity per trade. Lot = (equity × risk%) / (SL distance × contract size), rounded **down**
to the lot step (gold = 100 oz per lot, EURUSD = 100,000 units). If even 0.01 lot would risk
more than 1%, the lot shows 0.

## On the chart (`frontend/src/chart-overlays/drawingsPrimitive.ts`)

Drawn on the chart canvas (a Lightweight Charts series primitive), toggleable by layer:
session shading (Asia / London / NY), Asian range box, PDH/PDL/PWH/PWL dashed lines, BOS
(solid) and CHoCH (dashed) from the broken swing to the breaking candle, HH/HL/LH/LL labels,
liquidity lines and "$$$" equal highs/lows, ✕ Sweep markers, FVG boxes with a dotted 50% line
(faded once mitigated), demand/supply OBs (faded once mitigated), Fib 0.5 / 0.618 with the
shaded zone (EURUSD), the gold 20-hour high/low and breakout line, EMA 50 / 200, and the TradingView-style position box (red SL zone,
green TP zone, Entry / TP1 / TP3 lines, R:R and lot size). The entry candle has an arrow;
hovering it shows the score and checklist. Clicking any drawing asks the agent to explain it.
Higher-timeframe objects stay visible on lower timeframes and are labelled ("H1 OB").
Overlapping zones keep only the newest, max 5 per type.

## The agent (`backend/app/agent/`)

- `system_prompt.py`: both strategies' rules, generated from the config files.
- `agent.py`: builds the JSON the agent reads (detector output only) and answers in Darija / French / English with Bias → Key levels → Setup checklist → Plan (or NO TRADE + the missing rule) → Risk. With `GEMINI_API_KEY`, Gemini writes the answer and any reply quoting a price not in the data is discarded.
- `validator.py`: re-checks every signal before Telegram; it can only lower the score or reject.

## Backtest

`backend/app/backtest.py` replays the same strategy code bar by bar (`backend/app/strategies/replay.py`)
with the config's spread and slippage: `python -m app.backtest XAUUSD`. Yahoo provides ~2 years of
H1 (gold) and ~60 days of M15 (EURUSD) history; past news is not in the free calendar.

## Review mode

Open the app with `?asOf=<unix seconds>` to see any past moment exactly as the strategy saw it.
Example: the EURUSD sell signal of 2026-09-29 08:00 UTC → `/?asOf=1790668920`.
