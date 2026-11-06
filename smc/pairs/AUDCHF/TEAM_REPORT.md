# AUD/CHF team report (v0.1)

Educational research. Not financial advice, not a signal service, no guarantee. Demo testing comes before any live use, and live use is the account owner's decision.

## 1. Executive summary

- **Data:** Yahoo Finance; LTF (M5) 2026-08-16 → 2026-11-06 (about 82 days), H1 2024-01-22 → 2026-11-06. M5 data verdict: **SUSPECT** (range above EUR/USD (1.3)). See `../../DATA_QUALITY.md`.
- **Sample:** 3 setups across S1–S4; **0 passed all 7 questions** (the trades the playbook takes). Every strategy is far below 100 trades: **statistically weak, no conclusion possible.**
- **What works:** not known. No strategy has enough trades, in sample or out of sample, to say it has an edge. The M5 candles also fail the data check, so even these few results are **NOT VALID**.
- **What does not work:** not known either, for the same reason.
- **Key risks:** tiny sample; a single fixed cost (2.0 + 0.3 pips) that under-states news and rollover spreads; no news calendar for the test period; the source script was not available, so every rule is the brief's summary or a team interpretation.
- **Profile focus (from the brief, HYPOTHESIS):** S1 on 1H / 15M, S2 around PDH / PDL.

## 2. Rule book

Shared rule book `../../RULEBOOK.md` (v0.1, BUY and SELL), with this pair's config:

- pip 0.0001 · contract 100000 · pip value ≈ $12.5 per lot (verify with the broker)
- cost per trade: spread 2.0 + slippage 0.3 pips · commission $0.0 (none assumed)
- sessions (UTC, not DST-shifted): Asia [0, 6] · London [7, 10] · NY [12, 15]
- S3 minimum Asian range: 1.0 × H1 ATR(14) · minimum stop: 5.0 × cost

Pair notes:
- Risk-on (AUD) vs safe haven (CHF): a risk-sentiment filter is an open experiment (no equity data here).
- Low Asian volume: S3 needs an Asian range of at least 1 H1 ATR (HYPOTHESIS).
- Pip value in USD depends on USD/CHF (about 12.5 per lot here): verify with the broker.

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

In-sample: first 60 % of the M5 period (to 2026-10-04); out-of-sample: the rest. Rules were fixed before the run; 0 tuning passes. Results in R after costs. "Gated" = strategy rules + 7 questions (the trades taken); "all" = every setup of the strategy (checklist ignored, a bigger but untradeable sample). Baseline = random direction at the same moments with the same stop and target (500 runs).

**Data verdict NOT FIT: the numbers below are kept for transparency only. They are NOT VALID.**

| Strategy | setups | gated · in-sample | gated · out-of-sample | all · in-sample | all · out-of-sample | baseline (all, OOS) |
|---|---|---|---|---|---|---|
| S1 HTF trend continuation | 0 | 0 trades | 0 trades | 0 trades | 0 trades | — |
| S2 PDH / PDL & external liquidity sweep reversal | 2 | 0 trades | 0 trades | 1 tr · win 100.0 % · exp +1.82R · PF ∞ · DD 0.0R · streak 0 | 1 tr · win 0.0 % · exp -1.16R · PF 0.0 · DD 1.16R · streak 1 | -0.40R |
| S3 Asian range sweep + killzone (Power of 3 / Judas swing) | 1 | 0 trades | 0 trades | 0 trades | 1 tr · win 100.0 % · exp +0.10R · PF ∞ · DD 0.0R · streak 0 | -0.11R |
| S4 Single-candle OB & wick mitigation | 0 | 0 trades | 0 trades | 0 trades | 0 trades | — |

Managed (50 % at 1:3, BE after an M5 BOS), same trades:

| Strategy | gated · OOS | all · OOS |
|---|---|---|
| S1 | 0 trades | 0 trades |
| S2 | 0 trades | 1 tr · win 0.0 % · exp -1.16R · PF 0.0 · DD 1.16R · streak 1 |
| S3 | 0 trades | 1 tr · win 0.0 % · exp -0.10R · PF 0.0 · DD 0.1R · streak 1 |
| S4 | 0 trades | 0 trades |

Why setups were not taken (the 7 questions, across all 3 setups; one setup can fail several):

- H1 bias by a body-close break in the trade's direction: 3
- Reward ≥ 3R: 2
- London / New York hours, no Friday evening or Monday morning, no high-impact news within the window: 1

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
