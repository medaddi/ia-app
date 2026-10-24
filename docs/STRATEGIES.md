# EXUNU — the two strategies

The app runs **exactly two** rule-based strategies, one per instrument. Nothing else creates
signals or sends Telegram messages. Every rule below is code; every parameter lives in the
strategy's config file. Same closed candles → same result, every time.

| | XAUUSD (Gold) | EURUSD |
|---|---|---|
| Name | Liquidity Sweep + MSS + FVG | Trend Pullback + London Breakout Filter |
| Code | `server/strategies/xauusd/strategy.ts` | `server/strategies/eurusd/strategy.ts` |
| Config | `server/strategies/xauusd/config.ts` | `server/strategies/eurusd/config.ts` |
| Timeframes | Bias H4 + H1 · Setup M15 · Entry M5 | Bias D1 + H4 · Zones H1 · Entry M15 |
| Order | LIMIT (FVG / OB 50%) | MARKET (close of the confirmation candle) |

## Shared definitions (`server/strategies/shared/`)

- **Swing high/low**: fractal with 3 candles on each side, strictly higher/lower; confirmed only after the 3 right-side candles close. Labelled HH / LH / HL / LL against the previous swing of the same kind.
- **BOS**: a candle **close** beyond the last confirmed swing, in the trend direction.
- **CHoCH / MSS**: the first candle **close** beyond the last confirmed swing **against** the current trend.
- **Liquidity sweep**: the first candle that trades beyond a key level wicks through it and **closes back inside**. A close beyond it is a break, not a sweep.
- **Key levels**: PDH/PDL and PWH/PWL (trading day rolls at 17:00 New York), Asian high/low (00:00–06:00 London), previous session high/low, equal highs/lows within 0.1 × ATR ("$$$"), and for gold $10 / $50 round numbers.
- **FVG**: candle 1 high < candle 3 low (bullish) or candle 1 low > candle 3 high (bearish); ignored below 0.25 × ATR(14); mitigated once 50% is filled.
- **Order block**: the last opposite-coloured candle before the displacement that caused a BOS/CHoCH; valid only if the displacement body > 1.5 × the 20-candle average body.
- **Sessions**: defined in Europe/London and America/New_York local time and converted to UTC with the real DST offset of each date (tests cover the March and October clock changes).
- **Score**: weighted checklist 0–100. **≥ 75 = SIGNAL** (sent to Telegram once), **60–74 = WATCH** (chart only), **< 60 = ignored**. Any failed *required* rule = **NO TRADE**.

## Strategy 1 — XAUUSD "Liquidity Sweep + MSS + FVG"

1. **Bias (H4 + H1)** — bullish if the H1 close is above EMA 200 (H1) **and** the last H4 structure break is bullish; bearish is the mirror. If H4 and H1 disagree → **NO TRADE**.
2. **Kill zones** — London 08:00–11:00 (London time) and New York 08:30–11:30 (New York time). Outside them: no new signals. The Asian session only builds the Asian range.
3. **Sequence on M5 (all required, in this order)**
   1. A sweep of a key level **against** the bias. Buys: Asian low, PDL, PWL, London low, sell-side equal lows, round number. Sells: the mirror.
   2. Within **6 M5 candles**: an M5 MSS/CHoCH in the bias direction with displacement (body > 1.5 × average body). The sweep extreme must not be broken before the MSS.
   3. The displacement leaves an **FVG** (if none, the **order block**).
   4. **LIMIT entry** at the FVG 50% (or OB 50%).
4. **Risk**
   - SL = sweep wick ± (0.2 × ATR(14, M5) + spread). Must be **$2–$8**, else skip.
   - TP1 = 1R → close 50%, move SL to breakeven. TP2 = nearest opposing liquidity (Asian high/low, session high/low, PDH/PDL, PWH/PWL, EQH/EQL); R:R to TP2 must be ≥ 1:2, else skip. TP3 = next H1 swing beyond TP2, or 3R.
   - Pending order cancelled after **45 minutes**, or if price reaches TP1 before the fill.
5. **Filters** — no trade 30 minutes before/after high-impact USD news (CPI, NFP, FOMC, Fed Chair, PCE, GDP); spread ≤ $0.40; ATR(14, H1) between 50% and 250% of its 20-day average; max 2 trades per day; stop after 2 losses.
6. **Score weights** — bias 15, kill zone 10, sweep quality 15, displacement 15, FVG/OB quality 15, R:R 15, room to the next H1 level 10, volatility 5.

## Strategy 2 — EURUSD "Trend Pullback + London Breakout Filter"

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

## On the chart (`src/chart-overlays/drawingsPrimitive.ts`)

Drawn on the chart canvas (a Lightweight Charts series primitive), toggleable by layer:
session shading (Asia / London / NY), Asian range box, PDH/PDL/PWH/PWL dashed lines, BOS
(solid) and CHoCH (dashed) from the broken swing to the breaking candle, HH/HL/LH/LL labels,
liquidity lines and "$$$" equal highs/lows, ✕ Sweep markers, FVG boxes with a dotted 50% line
(faded once mitigated), demand/supply OBs (faded once mitigated), Fib 0.5 / 0.618 with the
shaded zone (EURUSD), EMA 50 / 200, and the TradingView-style position box (red SL zone,
green TP zone, Entry / TP1 / TP3 lines, R:R and lot size). The entry candle has an arrow;
hovering it shows the score and checklist. Clicking any drawing asks the agent to explain it.
Higher-timeframe objects stay visible on lower timeframes and are labelled ("H1 OB").
Overlapping zones keep only the newest, max 5 per type.

## The agent (`server/agent/`)

- `systemPrompt.ts` — both strategies' rules, generated from the config files.
- `context.ts` — the JSON the agent reads (detector output only).
- `validator.ts` — re-checks every signal before Telegram; it can only lower the score or reject.
- `agent.ts` — answers in Darija / French / English with Bias → Key levels → Setup checklist → Plan (or NO TRADE + the missing rule) → Risk. With `GEMINI_API_KEY`, Gemini writes the answer and any reply quoting a price not in the data is discarded; without a key, the answer is generated from the data directly.

## Backtest (`npm run backtest`)

`server/backtest/engine.ts` replays the same strategy code bar by bar (`server/strategies/replay.ts`)
with the config's spread and slippage, and writes `backtest-reports/XAUUSD.md` / `EURUSD.md`.
Limits: Yahoo provides ~60 days of 5m/15m history, past news is not in the free calendar, and
spread is a fixed value. A real 2–3 year test needs broker (MT5) history.

## Review mode

Open the app with `?asOf=<unix seconds>` to see any past moment exactly as the strategy saw it.
Example: the EURUSD sell signal of 2026-09-29 08:00 UTC → `/?asOf=1790668920`.
