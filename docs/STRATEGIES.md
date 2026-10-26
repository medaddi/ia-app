# LiquidityDissection — the two strategies

The app runs **exactly two** rule-based strategies: one for gold and one for every forex pair. Nothing else creates
signals or sends Telegram messages. Every rule below is code; every parameter lives in the
strategy's config file. Same closed candles → same result, every time.

| | XAUUSD (Gold) | Forex: EUR/USD, GBP/USD, USD/CAD, NZD/USD, EUR/CHF, NZD/CAD, AUD/CAD, AUD/CHF |
|---|---|---|
| Name | H1 Trend Breakout | FXAlexG Set & Forget Break & Retest |
| Code | `backend/app/strategies/xauusd/strategy.py` | `backend/app/strategies/alexg/strategy.py` |
| Config | `backend/app/strategies/xauusd/config.py` | `backend/app/strategies/alexg/config.py` |
| Timeframes | Trend, setup and entry on H1 | Bias W1 + D1 · Setup and entry H4 |
| Order | MARKET (close of the breakout candle) | MARKET (close of the retest candle), one 3R target |

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

## Strategy 2 — Forex "FXAlexG Set & Forget Break & Retest" (8 pairs, same rules)

The method the forex trader FXAlexG shows in his videos, written as code: EUR/USD, GBP/USD, USD/CAD,
NZD/USD, EUR/CHF, NZD/CAD, AUD/CAD, AUD/CHF (the pairs he trades). One config per pair
(`backend/app/strategies/alexg/config.py`): only the instrument, the assumed spread and the news currencies differ.
The agent answers forex questions with his thinking (top-down, pro-trend, no anticipation, set & forget) but never claims to be him.

1. **Top-down** — weekly bias = last closed weekly close vs EMA 20 (weekly); the last closed daily close vs EMA 20 (daily) must agree.
   Pro-trend only: weekly and daily disagree = no trade (FXAlexG calls counter-trend trades high risk).
2. **Look left** — areas of interest are H4 swing highs (buys) / lows (sells) of the last 120 H4 candles that price touched at least twice
   (within 0.3 × ATR). "If it happened here before, it will likely happen again."
3. **Break** — an H4 candle CLOSES beyond the level in the trend direction (within the last 30 H4 candles), price moves ≥ 1.5 × ATR(14, H4)
   away, and no H4 close comes back through the level by more than 0.5 × ATR.
4. **Retest, no anticipation** — an H4 candle comes back to the level (± 0.5 × ATR), closes on the right side and is a bullish / bearish
   engulfing or a pin bar (wick ≥ 2 × body and ≥ 60% of the candle). **MARKET entry** at that close (valid 60 min).
5. **Set & forget** — SL beyond the confirmation and previous candle ± 0.5 × ATR (15–120 pips, else no trade). **One target at 3R**:
   TP1 (1R) and TP2 (2R) are progress marks only — no partial close, no breakeven, no management. One trade per pair at a time.
6. **Filters** — no trade 30 min around high-impact news of the pair's two currencies; spread ≤ 4 pips; max 2 trades per day per pair, stop after 1 loss.
7. **Score weights** — trend 25, area of interest 20, break 20, retest 20, stop 5, target 10.

D1 and W1 are built from H1 with the 22:00 UTC rollover; H4 is aggregated from H1 (same Yahoo request).

### Backtest (Oct 2024 – Oct 2026, 2 years H1 → H4, spread + 0.2 pip slippage)

| Pair | Trades | Win rate | Total | 1st / 2nd half | Costs ×2 |
|---|---|---|---|---|---|
| **GBP/USD** | 38 | 39% | **+20.8R** | +16.5 / +4.3 | +15.6R |
| USD/CAD | 31 | 26% | −0.3R | −0.7 / +0.4 | −1.6R |
| NZD/CAD | 35 | 26% | −0.4R | −5.8 / +5.4 | −5.8R |
| EUR/USD | 46 | 24% | −3.3R | +11.4 / −14.7 | −4.6R |
| NZD/USD | 28 | 21% | −5.2R | +3.3 / −8.5 | −6.5R |
| AUD/CHF | 36 | 19% | −10.3R | −0.5 / −9.8 | −17.7R |
| EUR/CHF | 39 | 18% | −12.5R | −10.5 / −2.0 | −14.1R |
| AUD/CAD | 51 | 12% | −29.9R | −13.2 / −16.8 | −32.9R |

Only GBP/USD was profitable and robust. The other seven pairs were added and send signals on the user's explicit request.
His real trading is discretionary (head & shoulders, "4 weekly candles then a slowdown"…); this mechanical version cannot
capture everything he sees, which is one reason the results differ from his. The earlier EUR/USD "Trend Pullback + London Breakout"
code is kept in `backend/app/strategies/eurusd/` (parity tests) but no longer used.

## Risk (both)

Each user chooses the lot they took on a signal in the app; P&L = price move × lots × contract size (gold 100 oz,
forex 100,000 units), converted to USD for CAD- and CHF-quoted pairs with the latest USD/CAD, EUR/USD and EUR/CHF prices.
Each user's daily loss limit blocks new trades for the rest of the trading day.

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
