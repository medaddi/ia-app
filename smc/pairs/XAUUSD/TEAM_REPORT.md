# XAU/USD team report (v0.1)

Educational research. Not financial advice, not a signal service, no guarantee. Demo testing comes before any live use, and live use is the account owner's decision.

## 1. Executive summary

- **Data:** Yahoo Finance; LTF (M5) 2026-08-28 → 2026-11-06 (about 70 days), H1 2024-06-16 → 2026-11-06. M5 data verdict: **FIT**. See `../../DATA_QUALITY.md`.
- **Sample:** 41 setups across S1–S4; **4 passed all 7 questions** (the trades the playbook takes). Every strategy is far below 100 trades: **statistically weak, no conclusion possible.**
- **What works:** not known. No strategy has enough trades, in sample or out of sample, to say it has an edge.
- **What does not work:** not known either, for the same reason.
- **Key risks:** tiny sample; a single fixed cost (2.5 + 0.5 pips) that under-states news and rollover spreads; no news calendar for the test period; the source script was not available, so every rule is the brief's summary or a team interpretation.
- **Profile focus (from the brief, HYPOTHESIS):** S3 and S2 around the London and NY opens.

## 2. Rule book

Shared rule book `../../RULEBOOK.md` (v0.1, BUY and SELL), with this pair's config:

- pip 0.1 · contract 100 · pip value ≈ $10.0 per lot (verify with the broker)
- cost per trade: spread 2.5 + slippage 0.5 pips · commission $0.0 (none assumed)
- sessions (UTC, not DST-shifted): Asia [0, 6] · London [7, 10] · NY [12, 15]
- S3 minimum Asian range: 0.0 × H1 ATR(14) · minimum stop: 5.0 × cost

Pair notes:
- Very high volatility: the rules use structure levels (swings, OB, FVG), never fixed point distances; ATR only in the S3 range filter.
- Data is COMEX GC=F futures (Yahoo has no spot history): levels sit a few dollars above spot.
- USD, real yields and US data (NFP, CPI, FOMC) drive it: the news filter is mandatory live.
- Spreads widen at news and rollover: the test uses one fixed spread (an under-estimate there).

## Team and sign-off

The team's seven agents run live in the app on this pair (backend `app/smc/agents.py`), each on its own part of the same engine read:

| Role | Owns | Sign-off for v0.1 |
|---|---|---|
| Lead Strategist | decision, rule book, `CHANGELOG.md` | published v0.1; a setup is published only when its rules and all 7 questions pass |
| Structure Analyst | H4 bias (question 1), H1 swings, IDM, BOS / CHoCH, dealing range | signs when the H4 bias and range are defined |
| Liquidity & Session Analyst | PDH / PDL, Asian range, killzones, DST, news | objects: DST unverified, no news calendar |
| Entry Specialist | OB / FVG validity, LTF confirmation | signs a setup's zone; otherwise reports what each strategy waits for |
| Risk Manager | 1 % sizing, stop vs cost, BE, partials | signs only RR ≥ 1:3 and stop ≥ 5 × cost |
| Backtest Engineer | data, code, this report | objects: data verdict above, < 100 trades |
| Devil's Advocate | objections, hindsight, overfitting | lists every objection with each read |

The sign-offs are the code's checks, run on every read; no human has reviewed this version yet.

## 3. Definitions

`../../DEFINITIONS.md` (every interpretation flagged).

## 4. Backtest

In-sample: first 60 % of the M5 period (to 2026-10-09); out-of-sample: the rest. Rules were fixed before the run; 0 tuning passes. Results in R after costs. "Gated" = strategy rules + 7 questions (the trades taken); "all" = every setup of the strategy (checklist ignored, a bigger but untradeable sample). Baseline = random direction at the same moments with the same stop and target (500 runs).

**Data verdict FIT for M5, but the sample is far too small: statistically weak.**

| Strategy | setups | gated · in-sample | gated · out-of-sample | all · in-sample | all · out-of-sample | baseline (all, OOS) |
|---|---|---|---|---|---|---|
| S1 HTF trend continuation | 3 | 0 trades | 0 trades | 1 tr · win 0.0 % · exp -1.03R · PF 0.0 · DD 1.03R · streak 1 | 0 trades | — |
| S2 PDH / PDL & external liquidity sweep reversal | 3 | 0 trades | 0 trades | 1 tr · win 0.0 % · exp -1.03R · PF 0.0 · DD 1.03R · streak 1 | 2 tr · win 50.0 % · exp +0.81R · PF 2.53 · DD 1.06R · streak 1 | +0.79R |
| S3 Asian range sweep + killzone (Power of 3 / Judas swing) | 9 | 2 tr · win 0.0 % · exp -1.05R · PF 0.0 · DD 2.09R · streak 2 | 0 trades | 3 tr · win 33.3 % · exp +0.08R · PF 1.11 · DD 2.09R · streak 2 | 5 tr · win 0.0 % · exp -0.92R · PF 0.0 · DD 4.6R · streak 5 | -0.73R |
| S4 Single-candle OB & wick mitigation | 26 | 2 tr · win 50.0 % · exp +1.20R · PF 8.7 · DD 0.31R · streak 1 | 0 trades | 8 tr · win 50.0 % · exp +0.61R · PF 2.43 · DD 3.12R · streak 3 | 5 tr · win 60.0 % · exp +0.91R · PF 3.2 · DD 1.04R · streak 1 | +0.16R |

Managed (50 % at 1:3, BE after an M5 BOS), same trades:

| Strategy | gated · OOS | all · OOS |
|---|---|---|
| S1 | 0 trades | 0 trades |
| S2 | 0 trades | 2 tr · win 50.0 % · exp +0.52R · PF 1.98 · DD 1.06R · streak 1 |
| S3 | 0 trades | 5 tr · win 0.0 % · exp -0.64R · PF 0.0 · DD 3.17R · streak 5 |
| S4 | 0 trades | 5 tr · win 60.0 % · exp +1.16R · PF 6.38 · DD 1.04R · streak 1 |

Why setups were not taken (the 7 questions, across all 41 setups; one setup can fail several):

- HTF (H4) bias by a body-close break in the trade's direction: 26
- London / New York hours, no Friday evening or Monday morning, no high-impact news within the window: 20
- Reward ≥ 3R: 19
- Entry in discount of the H1 range: 3

Trades: `trades.csv` (every setup, its checklist answers and why it failed, its plain and managed result).

Statistical caveats: fewer than 100 trades per strategy means a win rate or expectancy can change sign with a handful of trades; the out-of-sample period is about 30 days; costs are a single fixed estimate; gold uses futures prices.

## 5. Journal and the first two weeks of demo

`../../JOURNAL_TEMPLATE.md` and `../../journal_template.csv`.

## 6. Open questions and next experiments

1. **The source script**: needed to check every SCRIPT (brief) rule and resolve the flagged interpretations.
2. **Data**: M5 / M1 history of at least 2 years from a clean source (broker MT5 export, or Dukascopy) to reach 100+ trades per strategy.
3. A high-impact news calendar CSV for the test period (`smc/news/high_impact.csv`, column `time_utc`).
4. DST-shifted killzones (London 06:00–09:00 UTC in summer) against the script's fixed UTC hours.
5. Not yet coded: IFVG entries, EQH / EQL, PWH / PWL, trendline liquidity, Extreme vs Decisional OB, trailing, 4H single candles.
6. Devil's advocate: questions 4 and 5 of the checklist never say no (built into the strategies); question 1 removes most reversals.
