# EUR/USD team report (v0.1)

Educational research. Not financial advice, not a signal service, no guarantee. Demo testing comes before any live use, and live use is the account owner's decision.

## 1. Executive summary

- **Data:** Yahoo Finance; LTF (M5) 2026-08-13 → 2026-11-05 (about 84 days), H1 2024-01-19 → 2026-11-05. M5 data verdict: **NOT FIT** (flat candles, opening jumps). See `../../DATA_QUALITY.md`.
- **Sample:** 44 setups across S1–S4; **1 passed all 7 questions** (the trades the playbook takes). Every strategy is far below 100 trades: **statistically weak, no conclusion possible.**
- **What works:** not known. No strategy has enough trades, in sample or out of sample, to say it has an edge. The M5 candles also fail the data check, so even these few results are **NOT VALID**.
- **What does not work:** not known either, for the same reason.
- **Key risks:** tiny sample; a single fixed cost (1.0 + 0.2 pips) that under-states news and rollover spreads; no news calendar for the test period; the source script was not available, so every rule is the brief's summary or a team interpretation.
- **Profile focus (from the brief, HYPOTHESIS):** S2 (frequent PDH / PDL sweeps).

## 2. Rule book

Shared rule book `../../RULEBOOK.md` (v0.1, BUY and SELL), with this pair's config:

- pip 0.0001 · contract 100000 · pip value ≈ $10.0 per lot (verify with the broker)
- cost per trade: spread 1.0 + slippage 0.2 pips · commission $0.0 (none assumed)
- sessions (UTC, not DST-shifted): Asia [0, 6] · London [7, 10] · NY [12, 15]
- S3 minimum Asian range: 0.0 × H1 ATR(14) · minimum stop: 5.0 × cost

Pair notes:
- Most liquid major: the most samples for the rules.
- DXY as a context filter is not in the data (open experiment).
- Asian session often quiet: S3 compared with and without a minimum Asian range (open experiment).

## Team and sign-off

The team's seven agents run live in the app on this pair (backend `app/smc/agents.py`), each on its own part of the same engine read:

| Role | Owns | Sign-off for v0.1 |
|---|---|---|
| Lead Strategist | decision, rule book, `CHANGELOG.md` | published v0.1; a setup is published only when its rules and all 7 questions pass |
| Structure Analyst | H1 swings, IDM, BOS / CHoCH, dealing range | signs when the H1 bias and range are defined |
| Liquidity & Session Analyst | PDH / PDL, Asian range, killzones, DST, news | objects: DST unverified, no news calendar |
| Entry Specialist | OB / FVG validity, LTF confirmation | signs a setup's zone; otherwise reports what each strategy waits for |
| Risk Manager | 1 % sizing, stop vs cost, BE, partials | signs only RR ≥ 1:3 and stop ≥ 5 × cost |
| Backtest Engineer | data, code, this report | objects: data verdict above, < 100 trades |
| Devil's Advocate | objections, hindsight, overfitting | lists every objection with each read |

The sign-offs are the code's checks, run on every read; no human has reviewed this version yet.

## 3. Definitions

`../../DEFINITIONS.md` (every interpretation flagged).

## 4. Backtest

In-sample: first 60 % of the M5 period (to 2026-10-03); out-of-sample: the rest. Rules were fixed before the run; 0 tuning passes. Results in R after costs. "Gated" = strategy rules + 7 questions (the trades taken); "all" = every setup of the strategy (checklist ignored, a bigger but untradeable sample). Baseline = random direction at the same moments with the same stop and target (500 runs).

**Data verdict NOT FIT: the numbers below are kept for transparency only. They are NOT VALID.**

| Strategy | setups | gated · in-sample | gated · out-of-sample | all · in-sample | all · out-of-sample | baseline (all, OOS) |
|---|---|---|---|---|---|---|
| S1 HTF trend continuation | 0 | 0 trades | 0 trades | 0 trades | 0 trades | — |
| S2 PDH / PDL & external liquidity sweep reversal | 10 | 0 trades | 0 trades | 3 tr · win 0.0 % · exp -1.13R · PF 0.0 · DD 3.4R · streak 3 | 5 tr · win 0.0 % · exp -0.96R · PF 0.0 · DD 4.8R · streak 5 | +0.01R |
| S3 Asian range sweep + killzone (Power of 3 / Judas swing) | 6 | 0 trades | 1 tr · win 0.0 % · exp -1.20R · PF 0.0 · DD 1.19R · streak 1 | 1 tr · win 100.0 % · exp +0.79R · PF ∞ · DD 0.0R · streak 0 | 4 tr · win 25.0 % · exp -0.49R · PF 0.43 · DD 2.36R · streak 2 | +0.37R |
| S4 Single-candle OB & wick mitigation | 28 | 0 trades | 0 trades | 10 tr · win 60.0 % · exp +0.09R · PF 1.19 · DD 2.39R · streak 2 | 8 tr · win 37.5 % · exp +0.09R · PF 1.14 · DD 3.94R · streak 4 | -0.45R |

Managed (50 % at 1:3, BE after an M5 BOS), same trades:

| Strategy | gated · OOS | all · OOS |
|---|---|---|
| S1 | 0 trades | 0 trades |
| S2 | 0 trades | 5 tr · win 0.0 % · exp -0.76R · PF 0.0 · DD 3.8R · streak 5 |
| S3 | 1 tr · win 0.0 % · exp -1.20R · PF 0.0 · DD 1.19R · streak 1 | 4 tr · win 25.0 % · exp -0.24R · PF 0.6 · DD 2.36R · streak 2 |
| S4 | 0 trades | 8 tr · win 37.5 % · exp +0.42R · PF 2.12 · DD 1.94R · streak 4 |

Why setups were not taken (the 7 questions, across all 44 setups; one setup can fail several):

- H1 bias by a body-close break in the trade's direction: 40
- Reward ≥ 3R: 29
- London / New York hours, no Friday evening or Monday morning, no high-impact news within the window: 20
- Entry in discount of the H1 range: 1
- Entry in premium of the H1 range: 1

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
