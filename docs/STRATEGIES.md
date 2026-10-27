# LiquidityDissection — the two strategies

The app runs **exactly two** rule-based strategies: one for gold and one for every forex pair. Nothing else creates
signals or sends Telegram messages. Every rule below is code; every parameter lives in the
strategy's config file. Same closed candles → same result, every time.

| | XAUUSD (Gold) | Forex: EUR/USD, GBP/USD, USD/CAD, NZD/USD, EUR/CHF, NZD/CAD, AUD/CAD, AUD/CHF |
|---|---|---|
| Name | H1 Trend Breakout | FXAlexG Set & Forget GPA |
| Code | `backend/app/strategies/xauusd/strategy.py` | `backend/app/strategies/alexg/strategy.py` |
| Config | `backend/app/strategies/xauusd/config.py` | `backend/app/strategies/alexg/config.py` |
| Timeframes | Trend, setup and entry on H1 | Trend W1 + D1 + H4 · AOI W1 / D1 · Pattern & EMA 1H · Entry 30m |
| Order | MARKET (close of the breakout candle) | MARKET (close of the 30m engulfing), one target at the next W1 / D1 zone (≥ 1:2) |

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

## Strategy 2 — Forex "FXAlexG Set & Forget GPA" (8 pairs, same rules)

The user's written rules of the fxalexg Set and Forget strategy, as code, on EUR/USD, GBP/USD, USD/CAD, NZD/USD,
EUR/CHF, NZD/CAD, AUD/CAD and AUD/CHF (`backend/app/strategies/alexg/`). One config per pair: only the instrument,
the assumed spread and the news currencies differ.

1. **Trend — 3 sync rule** — W1, D1 and H4 by market structure: HH/HL bullish, LL/LH bearish; the trend only shifts on a
   candle **body close** beyond the last confirmed swing. Trade the majority (≥ 2 of 3), ideally all 3. Below H4 = entries only.
2. **AOI** — zones from W1 / D1 swing points only (points within 0.3 × ATR(D1) of each other), valid with **≥ 3 touches**.
   Buys only above the AOI with a bullish majority, sells only below it with a bearish majority.
3. **GPA — 10 confluences × 10%**: W1 trend · D1 trend · H4 trend · price at a valid AOI · H4 50 EMA rejection ·
   H4 structure rejection · H4 rejection candle (pin bar / wick / engulfing) · 1H H&S / inverse H&S / double top-bottom ·
   1H 50 EMA rejection · 30m engulfing at the London (07:00–10:00) or New York (13:00–16:00 London) open.
   **A+ 80–100% · B 70–79% · C+ 60–69% (minimum)** · below 60% = no trade.
4. **Entry** — only after the AOI touch, an H4 rejection and the 30m engulfing at the open: MARKET at its close.
5. **SL** beyond the pattern's head (conservative), otherwise beyond the last 12 H1 candles (10–90 pips).
   **TP** at the next W1 / D1 zone (≥ 3 touches), 2 pips before it, pulled in front of a round level (every 50 pips).
   **Minimum 1:2**, else no trade. Set & forget: one target, no partials, no breakeven. One trade per pair at a time.
6. **Filters** — 30 min around high-impact news of the pair's currencies, spread ≤ 4 pips, 2 trades / 1 loss per day.

The live read (chart, dashboard, agent) grades the last 30m candle even without a trade ("Grade now"), and the agent
answers forex questions in the 5 parts of the rules: trend sync · AOI · grade · verdict · parameters.

### Backtest

Yahoo serves only 60 days of 30m, so the 2-year test uses **1H candles for the entry** (rule 4 allows 30m or 1H).
Costs: assumed spread + 0.2 pip slippage; "costs ×2" doubles both.

| Pair | Trades | Win rate | Total (TP at the next zone) | Costs ×2 |
|---|---|---|---|---|
| AUD/CAD | 5 | 40% | +1.5R | +1.2R |
| USD/CAD | 33 | 18% | −5.6R | −11.0R |
| NZD/USD | 21 | 24% | −5.7R | −8.0R |
| EUR/USD | 13 | 8% | −6.9R | −7.5R |
| AUD/CHF | 20 | 20% | −8.0R | −9.8R |
| NZD/CAD | 8 | 0% | −8.7R | −9.3R |
| EUR/CHF | 25 | 16% | −10.7R | −12.1R |
| GBP/USD | 22 | 5% | −19.4R | −20.4R |

The next W1 / D1 zone is usually 1:3 to 1:6 away, so it is rarely reached: as written, the rules lose on 7 of 8 pairs,
and A+ setups did not win more often than C+ ones. Capping the TP at 3R does not fix it (still negative on 6 of 8).
Last 60 days with real 30m candles: 42 trades over the 8 pairs, about +5R in total (far too few trades to judge).
`risk.maxRr` in the config caps the TP (off by default, to follow the rules as written).

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
