# Validation of Set & Forget · dukascopy · 2026-11-11

Data: stored Dukascopy candles (M5 and H1, one year); D1 and W1 are built from that same year, so the weekly structure and the zones see less history than the live app does. Period 2025-11-05 → 2026-11-05; train until 2026-05-06, validation until 2026-08-06, test after. 6 instruments.

Fixed before the run (backend/app/smc/strategy.json): the four versions, the chronological 50 / 25 / 25 split, the rule that an instrument needs 100 out-of-sample trades and a 95 % interval above 0 R before it is called validated. Costs: the config's spread + slippage on every trade. News, session, rollover and Friday rules on. Nothing was tuned on these results.

Reading a cell: trades · win rate · net expectancy per trade with its 95 % bootstrap interval · profit factor · maximum drawdown. R are after costs. With 3R wins and 1R losses the break-even win rate is 25 % before costs (1 / (3 + 1)); with 4R wins, 20 %; costs raise both.

## All instruments together

| version | all trades | out of sample | trend-following | counter-trend (separate) | trades on a 4H fallback zone |
|---|---|---|---|---|---|
| baseline | 16 · 19 % · E -0.20R [-0.95, +0.77] · PF 0.76 · DD 6.51R | 11 · 27 % · E +0.20R [-0.89, +1.54] · PF 1.28 · DD 5.52R | 11 · 27 % · E +0.10R [-1.09, +1.43] · PF 1.13 · DD 5.4R | 5 · 0 % · E -0.85R [-1.10, -0.42] · PF 0.0 · DD 4.29R | 0 |
| candidate | 13 · 23 % · E -0.08R [-1.08, +1.08] · PF 0.9 · DD 6.51R | 8 · 38 % · E +0.53R [-0.74, +2.22] · PF 1.75 · DD 3.45R | 11 · 27 % · E +0.10R [-1.09, +1.43] · PF 1.13 · DD 5.4R | 2 · 0 % · E -1.11R [-1.11, -1.11] · PF 0.0 · DD 2.22R | 0 |
| candidate_rr3 | 3 · 67 % · E +2.53R [-1.05, +5.04] · PF 8.26 · DD 1.05R | 2 · 100 % · E +4.32R [+3.61, +5.04] · PF — · DD 0.0R | 3 · 67 % · E +2.53R [-1.05, +5.04] · PF 8.26 · DD 1.05R | 0 | 0 |
| candidate_rr4 | 1 · 100 % · E +5.04R · PF — · DD 0.0R | 1 · 100 % · E +5.04R · PF — · DD 0.0R | 1 · 100 % · E +5.04R · PF — · DD 0.0R | 0 | 0 |

## Per setup type (all instruments)

| version | SF_BR | SF_BOUNCE | SF_COUNTER |
|---|---|---|---|
| baseline | 11 · 27 % · E +0.10R [-1.09, +1.43] · PF 1.13 · DD 5.4R | 0 | 5 · 0 % · E -0.85R [-1.10, -0.42] · PF 0.0 · DD 4.29R |
| candidate | 11 · 27 % · E +0.10R [-1.09, +1.43] · PF 1.13 · DD 5.4R | 0 | 2 · 0 % · E -1.11R [-1.11, -1.11] · PF 0.0 · DD 2.22R |
| candidate_rr3 | 3 · 67 % · E +2.53R [-1.05, +5.04] · PF 8.26 · DD 1.05R | 0 | 0 |
| candidate_rr4 | 1 · 100 % · E +5.04R · PF — · DD 0.0R | 0 | 0 |

## Per instrument (a pair with many trades never hides a losing one)

### baseline

| instrument | all | train | validation | test | avg win / loss / cost (R) | evidence |
|---|---|---|---|---|---|---|
| XAUUSD | 1 · 0 % · E -1.01R · PF 0.0 · DD 1.01R | 0 | 1 · 0 % · E -1.01R · PF 0.0 · DD 1.01R | 0 | — / 1.009 / 0.009 | insufficient data (1 OOS) |
| EURUSD | 4 · 25 % · E -0.10R [-1.06, +1.79] · PF 0.87 · DD 3.15R | 2 · 0 % · E -1.04R [-1.05, -1.04] · PF 0.0 · DD 2.09R | 1 · 0 % · E -1.06R · PF 0.0 · DD 1.06R | 1 · 100 % · E +2.74R · PF — · DD 0.0R | 2.736 / 1.05 / 0.044 | insufficient data (2 OOS) |
| GBPUSD | 6 · 33 % · E +0.66R [-0.91, +2.71] · PF 2.22 · DD 2.23R | 1 · 0 % · E -1.04R · PF 0.0 · DD 1.04R | 2 · 100 % · E +3.62R [+2.21, +5.04] · PF — · DD 0.0R | 3 · 0 % · E -0.74R [-1.14, +0.01] · PF 0.01 · DD 2.23R | 3.624 / 0.816 / 0.091 | insufficient data (5 OOS) |
| EURCHF | 1 · 0 % · E -1.11R · PF 0.0 · DD 1.11R | 1 · 0 % · E -1.11R · PF 0.0 · DD 1.11R | 0 | 0 | — / 1.108 / 0.108 | insufficient data (0 OOS) |
| AUDCAD | 3 · 0 % · E -1.13R [-1.16, -1.11] · PF 0.0 · DD 3.39R | 1 · 0 % · E -1.11R · PF 0.0 · DD 1.11R | 2 · 0 % · E -1.14R [-1.16, -1.11] · PF 0.0 · DD 2.27R | 0 | — / 1.129 / 0.129 | insufficient data (2 OOS) |
| AUDCHF | 1 · 0 % · E -1.20R · PF 0.0 · DD 1.2R | 0 | 1 · 0 % · E -1.20R · PF 0.0 · DD 1.2R | 0 | — / 1.203 / 0.203 | insufficient data (1 OOS) |

### candidate

| instrument | all | train | validation | test | avg win / loss / cost (R) | evidence |
|---|---|---|---|---|---|---|
| XAUUSD | 0 | 0 | 0 | 0 | — | insufficient data (0 OOS) |
| EURUSD | 3 · 33 % · E +0.21R [-1.05, +2.74] · PF 1.31 · DD 2.09R | 2 · 0 % · E -1.04R [-1.05, -1.04] · PF 0.0 · DD 2.09R | 0 | 1 · 100 % · E +2.74R · PF — · DD 0.0R | 2.736 / 1.045 / 0.038 | insufficient data (1 OOS) |
| GBPUSD | 5 · 40 % · E +0.79R [-1.10, +3.24] · PF 2.21 · DD 2.24R | 1 · 0 % · E -1.04R · PF 0.0 · DD 1.04R | 2 · 100 % · E +3.62R [+2.21, +5.04] · PF — · DD 0.0R | 2 · 0 % · E -1.12R [-1.14, -1.10] · PF 0.0 · DD 2.24R | 3.624 / 1.092 / 0.088 | insufficient data (4 OOS) |
| EURCHF | 1 · 0 % · E -1.11R · PF 0.0 · DD 1.11R | 1 · 0 % · E -1.11R · PF 0.0 · DD 1.11R | 0 | 0 | — / 1.108 / 0.108 | insufficient data (0 OOS) |
| AUDCAD | 3 · 0 % · E -1.13R [-1.16, -1.11] · PF 0.0 · DD 3.39R | 1 · 0 % · E -1.11R · PF 0.0 · DD 1.11R | 2 · 0 % · E -1.14R [-1.16, -1.11] · PF 0.0 · DD 2.27R | 0 | — / 1.129 / 0.129 | insufficient data (2 OOS) |
| AUDCHF | 1 · 0 % · E -1.20R · PF 0.0 · DD 1.2R | 0 | 1 · 0 % · E -1.20R · PF 0.0 · DD 1.2R | 0 | — / 1.203 / 0.203 | insufficient data (1 OOS) |

### candidate_rr3

| instrument | all | train | validation | test | avg win / loss / cost (R) | evidence |
|---|---|---|---|---|---|---|
| XAUUSD | 0 | 0 | 0 | 0 | — | insufficient data (0 OOS) |
| EURUSD | 2 · 50 % · E +1.28R [-1.05, +3.61] · PF 3.45 · DD 1.05R | 1 · 0 % · E -1.05R · PF 0.0 · DD 1.05R | 0 | 1 · 100 % · E +3.61R · PF — · DD 0.0R | 3.606 / 1.046 / 0.042 | insufficient data (1 OOS) |
| GBPUSD | 1 · 100 % · E +5.04R · PF — · DD 0.0R | 0 | 1 · 100 % · E +5.04R · PF — · DD 0.0R | 0 | 5.036 / — / 0.109 | insufficient data (1 OOS) |
| EURCHF | 0 | 0 | 0 | 0 | — | insufficient data (0 OOS) |
| AUDCAD | 0 | 0 | 0 | 0 | — | insufficient data (0 OOS) |
| AUDCHF | 0 | 0 | 0 | 0 | — | insufficient data (0 OOS) |

### candidate_rr4

| instrument | all | train | validation | test | avg win / loss / cost (R) | evidence |
|---|---|---|---|---|---|---|
| XAUUSD | 0 | 0 | 0 | 0 | — | insufficient data (0 OOS) |
| EURUSD | 0 | 0 | 0 | 0 | — | insufficient data (0 OOS) |
| GBPUSD | 1 · 100 % · E +5.04R · PF — · DD 0.0R | 0 | 1 · 100 % · E +5.04R · PF — · DD 0.0R | 0 | 5.036 / — / 0.109 | insufficient data (1 OOS) |
| EURCHF | 0 | 0 | 0 | 0 | — | insufficient data (0 OOS) |
| AUDCAD | 0 | 0 | 0 | 0 | — | insufficient data (0 OOS) |
| AUDCHF | 0 | 0 | 0 | 0 | — | insufficient data (0 OOS) |

## What this shows

- The most out-of-sample trades any instrument has on the candidate is 4; the requirement is 100. No instrument is validated: the evidence is insufficient.
- A positive or negative total on a handful of trades is not a result: the intervals above are wide and most cross 0.
- Nothing here says the strategy is profitable.
