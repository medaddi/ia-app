# Validation of Set & Forget · yahoo · 2026-11-11

Data: Yahoo Finance through the app's own feed code: M5 60 days, H1 2 years, D1 5 years (full W1 / D1 history for the structure and the zones); gold is COMEX GC=F futures; forex has no volume; closed candles only. Period 2026-09-02 → 2026-11-11; train until 2026-10-07, validation until 2026-10-25, test after. 29 instruments.

Fixed before the run (backend/app/smc/strategy.json): the four versions, the chronological 50 / 25 / 25 split, the rule that an instrument needs 100 out-of-sample trades and a 95 % interval above 0 R before it is called validated. Costs: the config's spread + slippage on every trade. News, session, rollover and Friday rules on. Nothing was tuned on these results.

Reading a cell: trades · win rate · net expectancy per trade with its 95 % bootstrap interval · profit factor · maximum drawdown. R are after costs. With 3R wins and 1R losses the break-even win rate is 25 % before costs (1 / (3 + 1)); with 4R wins, 20 %; costs raise both.

## All instruments together

| version | all trades | out of sample | trend-following | counter-trend (separate) | trades on a 4H fallback zone |
|---|---|---|---|---|---|
| baseline | 30 · 23 % · E +0.17R [-0.40, +0.82] · PF 1.31 · DD 4.6R | 14 · 21 % · E +0.10R [-0.56, +0.80] · PF 1.22 · DD 2.3R | 29 · 24 % · E +0.20R [-0.37, +0.92] · PF 1.39 · DD 4.6R | 1 · 0 % · E -1.01R · PF 0.0 · DD 1.01R | 0 |
| candidate | 29 · 24 % · E +0.20R [-0.37, +0.92] · PF 1.39 · DD 4.6R | 14 · 21 % · E +0.10R [-0.56, +0.80] · PF 1.22 · DD 2.3R | 29 · 24 % · E +0.20R [-0.37, +0.92] · PF 1.39 · DD 4.6R | 0 | 0 |
| candidate_rr3 | 17 · 12 % · E -0.07R [-0.79, +0.83] · PF 0.88 · DD 4.36R | 5 · 0 % · E -0.66R [-1.11, -0.21] · PF 0.01 · DD 3.32R | 17 · 12 % · E -0.07R [-0.79, +0.83] · PF 0.88 · DD 4.36R | 0 | 0 |
| candidate_rr4 | 8 · 12 % · E -0.07R [-1.04, +1.50] · PF 0.9 · DD 3.26R | 1 · 0 % · E -1.10R · PF 0.0 · DD 1.1R | 8 · 12 % · E -0.07R [-1.04, +1.50] · PF 0.9 · DD 3.26R | 0 | 0 |

## Per setup type (all instruments)

| version | SF_BR | SF_BOUNCE | SF_COUNTER |
|---|---|---|---|
| baseline | 28 · 21 % · E +0.14R [-0.46, +0.83] · PF 1.25 · DD 4.6R | 1 · 100 % · E +2.11R · PF — · DD 0.0R | 1 · 0 % · E -1.01R · PF 0.0 · DD 1.01R |
| candidate | 28 · 21 % · E +0.14R [-0.46, +0.83] · PF 1.25 · DD 4.6R | 1 · 100 % · E +2.11R · PF — · DD 0.0R | 0 |
| candidate_rr3 | 17 · 12 % · E -0.07R [-0.79, +0.83] · PF 0.88 · DD 4.36R | 0 | 0 |
| candidate_rr4 | 8 · 12 % · E -0.07R [-1.04, +1.50] · PF 0.9 · DD 3.26R | 0 | 0 |

## Per instrument (a pair with many trades never hides a losing one)

### baseline

| instrument | all | train | validation | test | avg win / loss / cost (R) | evidence |
|---|---|---|---|---|---|---|
| XAUUSD | 2 · 50 % · E +0.84R [-1.01, +2.68] · PF 2.66 · DD 1.01R | 1 · 0 % · E -1.01R · PF 0.0 · DD 1.01R | 0 | 1 · 100 % · E +2.68R · PF — · DD 0.0R | 2.682 / 1.009 / 0.008 | insufficient data (1 OOS) |
| EURUSD | 2 · 50 % · E +0.90R [-1.04, +2.83] · PF 2.72 · DD 1.04R | 2 · 50 % · E +0.90R [-1.04, +2.83] · PF 2.72 · DD 1.04R | 0 | 0 | 2.83 / 1.04 / 0.033 | insufficient data (0 OOS) |
| GBPUSD | 3 · 0 % · E -0.53R [-1.28, +0.02] · PF 0.01 · DD 1.59R | 2 · 0 % · E -0.63R [-1.28, +0.02] · PF 0.02 · DD 1.28R | 1 · 0 % · E -0.33R · PF 0.0 · DD 0.33R | 0 | — / 0.531 / 0.167 | insufficient data (1 OOS) |
| USDJPY | 1 · 0 % · E -1.01R · PF 0.0 · DD 1.01R | 1 · 0 % · E -1.01R · PF 0.0 · DD 1.01R | 0 | 0 | — / 1.014 / 0.014 | insufficient data (0 OOS) |
| USDCAD | 0 | 0 | 0 | 0 | — | insufficient data (0 OOS) |
| USDCHF | 0 | 0 | 0 | 0 | — | insufficient data (0 OOS) |
| AUDUSD | 2 · 0 % · E -0.57R [-1.16, +0.02] · PF 0.02 · DD 1.16R | 1 · 0 % · E -1.16R · PF 0.0 · DD 1.16R | 0 | 1 · 0 % · E +0.02R · PF — · DD 0.0R | — / 0.57 / 0.113 | insufficient data (1 OOS) |
| NZDUSD | 0 | 0 | 0 | 0 | — | insufficient data (0 OOS) |
| GBPJPY | 1 · 0 % · E -1.05R · PF 0.0 · DD 1.05R | 0 | 0 | 1 · 0 % · E -1.05R · PF 0.0 · DD 1.05R | — / 1.048 / 0.048 | insufficient data (1 OOS) |
| GBPAUD | 1 · 0 % · E -0.04R · PF 0.0 · DD 0.04R | 0 | 1 · 0 % · E -0.04R · PF 0.0 · DD 0.04R | 0 | — / 0.038 / 0.089 | insufficient data (1 OOS) |
| GBPNZD | 0 | 0 | 0 | 0 | — | insufficient data (0 OOS) |
| GBPCAD | 2 · 0 % · E -1.14R [-1.14, -1.14] · PF 0.0 · DD 2.27R | 1 · 0 % · E -1.14R · PF 0.0 · DD 1.14R | 0 | 1 · 0 % · E -1.14R · PF 0.0 · DD 1.14R | — / 1.137 / 0.137 | insufficient data (1 OOS) |
| GBPCHF | 0 | 0 | 0 | 0 | — | insufficient data (0 OOS) |
| EURGBP | 0 | 0 | 0 | 0 | — | insufficient data (0 OOS) |
| EURJPY | 1 · 100 % · E +3.74R · PF — · DD 0.0R | 1 · 100 % · E +3.74R · PF — · DD 0.0R | 0 | 0 | 3.738 / — / 0.062 | insufficient data (0 OOS) |
| EURAUD | 0 | 0 | 0 | 0 | — | insufficient data (0 OOS) |
| EURNZD | 0 | 0 | 0 | 0 | — | insufficient data (0 OOS) |
| EURCAD | 2 · 50 % · E +0.97R [-0.03, +1.97] · PF 75.81 · DD 0.03R | 1 · 100 % · E +1.97R · PF — · DD 0.0R | 1 · 0 % · E -0.03R · PF 0.0 · DD 0.03R | 0 | 1.974 / 0.026 / 0.108 | insufficient data (1 OOS) |
| EURCHF | 2 · 0 % · E -1.12R [-1.13, -1.12] · PF 0.0 · DD 2.25R | 2 · 0 % · E -1.12R [-1.13, -1.12] · PF 0.0 · DD 2.25R | 0 | 0 | — / 1.125 / 0.125 | insufficient data (0 OOS) |
| AUDJPY | 3 · 0 % · E -1.11R [-1.13, -1.08] · PF 0.0 · DD 3.32R | 0 | 2 · 0 % · E -1.12R [-1.13, -1.10] · PF 0.0 · DD 2.23R | 1 · 0 % · E -1.08R · PF 0.0 · DD 1.08R | — / 1.107 / 0.107 | insufficient data (3 OOS) |
| AUDCAD | 0 | 0 | 0 | 0 | — | insufficient data (0 OOS) |
| AUDCHF | 1 · 0 % · E -0.01R · PF 0.0 · DD 0.01R | 0 | 0 | 1 · 0 % · E -0.01R · PF 0.0 · DD 0.01R | — / 0.014 / 0.108 | insufficient data (1 OOS) |
| AUDNZD | 0 | 0 | 0 | 0 | — | insufficient data (0 OOS) |
| NZDJPY | 1 · 100 % · E +5.13R · PF — · DD 0.0R | 1 · 100 % · E +5.13R · PF — · DD 0.0R | 0 | 0 | 5.13 / — / 0.244 | insufficient data (0 OOS) |
| NZDCAD | 2 · 50 % · E +0.48R [-1.15, +2.11] · PF 1.84 · DD 1.15R | 1 · 0 % · E -1.15R · PF 0.0 · DD 1.15R | 1 · 100 % · E +2.11R · PF — · DD 0.0R | 0 | 2.108 / 1.145 / 0.173 | insufficient data (1 OOS) |
| NZDCHF | 2 · 0 % · E -0.06R [-0.08, -0.04] · PF 0.0 · DD 0.13R | 1 · 0 % · E -0.04R · PF 0.0 · DD 0.04R | 0 | 1 · 0 % · E -0.08R · PF 0.0 · DD 0.08R | — / 0.064 / 0.15 | insufficient data (1 OOS) |
| CADJPY | 0 | 0 | 0 | 0 | — | insufficient data (0 OOS) |
| CADCHF | 0 | 0 | 0 | 0 | — | insufficient data (0 OOS) |
| CHFJPY | 2 · 50 % · E +1.26R [-0.02, +2.53] · PF 119.76 · DD 0.02R | 1 · 0 % · E -0.02R · PF 0.0 · DD 0.02R | 1 · 100 % · E +2.53R · PF — · DD 0.0R | 0 | 2.534 / 0.021 / 0.058 | insufficient data (1 OOS) |

### candidate

| instrument | all | train | validation | test | avg win / loss / cost (R) | evidence |
|---|---|---|---|---|---|---|
| XAUUSD | 2 · 50 % · E +0.84R [-1.01, +2.68] · PF 2.66 · DD 1.01R | 1 · 0 % · E -1.01R · PF 0.0 · DD 1.01R | 0 | 1 · 100 % · E +2.68R · PF — · DD 0.0R | 2.682 / 1.009 / 0.008 | insufficient data (1 OOS) |
| EURUSD | 2 · 50 % · E +0.90R [-1.04, +2.83] · PF 2.72 · DD 1.04R | 2 · 50 % · E +0.90R [-1.04, +2.83] · PF 2.72 · DD 1.04R | 0 | 0 | 2.83 / 1.04 / 0.033 | insufficient data (0 OOS) |
| GBPUSD | 3 · 0 % · E -0.53R [-1.28, +0.02] · PF 0.01 · DD 1.59R | 2 · 0 % · E -0.63R [-1.28, +0.02] · PF 0.02 · DD 1.28R | 1 · 0 % · E -0.33R · PF 0.0 · DD 0.33R | 0 | — / 0.531 / 0.167 | insufficient data (1 OOS) |
| USDJPY | 0 | 0 | 0 | 0 | — | insufficient data (0 OOS) |
| USDCAD | 0 | 0 | 0 | 0 | — | insufficient data (0 OOS) |
| USDCHF | 0 | 0 | 0 | 0 | — | insufficient data (0 OOS) |
| AUDUSD | 2 · 0 % · E -0.57R [-1.16, +0.02] · PF 0.02 · DD 1.16R | 1 · 0 % · E -1.16R · PF 0.0 · DD 1.16R | 0 | 1 · 0 % · E +0.02R · PF — · DD 0.0R | — / 0.57 / 0.113 | insufficient data (1 OOS) |
| NZDUSD | 0 | 0 | 0 | 0 | — | insufficient data (0 OOS) |
| GBPJPY | 1 · 0 % · E -1.05R · PF 0.0 · DD 1.05R | 0 | 0 | 1 · 0 % · E -1.05R · PF 0.0 · DD 1.05R | — / 1.048 / 0.048 | insufficient data (1 OOS) |
| GBPAUD | 1 · 0 % · E -0.04R · PF 0.0 · DD 0.04R | 0 | 1 · 0 % · E -0.04R · PF 0.0 · DD 0.04R | 0 | — / 0.038 / 0.089 | insufficient data (1 OOS) |
| GBPNZD | 0 | 0 | 0 | 0 | — | insufficient data (0 OOS) |
| GBPCAD | 2 · 0 % · E -1.14R [-1.14, -1.14] · PF 0.0 · DD 2.27R | 1 · 0 % · E -1.14R · PF 0.0 · DD 1.14R | 0 | 1 · 0 % · E -1.14R · PF 0.0 · DD 1.14R | — / 1.137 / 0.137 | insufficient data (1 OOS) |
| GBPCHF | 0 | 0 | 0 | 0 | — | insufficient data (0 OOS) |
| EURGBP | 0 | 0 | 0 | 0 | — | insufficient data (0 OOS) |
| EURJPY | 1 · 100 % · E +3.74R · PF — · DD 0.0R | 1 · 100 % · E +3.74R · PF — · DD 0.0R | 0 | 0 | 3.738 / — / 0.062 | insufficient data (0 OOS) |
| EURAUD | 0 | 0 | 0 | 0 | — | insufficient data (0 OOS) |
| EURNZD | 0 | 0 | 0 | 0 | — | insufficient data (0 OOS) |
| EURCAD | 2 · 50 % · E +0.97R [-0.03, +1.97] · PF 75.81 · DD 0.03R | 1 · 100 % · E +1.97R · PF — · DD 0.0R | 1 · 0 % · E -0.03R · PF 0.0 · DD 0.03R | 0 | 1.974 / 0.026 / 0.108 | insufficient data (1 OOS) |
| EURCHF | 2 · 0 % · E -1.12R [-1.13, -1.12] · PF 0.0 · DD 2.25R | 2 · 0 % · E -1.12R [-1.13, -1.12] · PF 0.0 · DD 2.25R | 0 | 0 | — / 1.125 / 0.125 | insufficient data (0 OOS) |
| AUDJPY | 3 · 0 % · E -1.11R [-1.13, -1.08] · PF 0.0 · DD 3.32R | 0 | 2 · 0 % · E -1.12R [-1.13, -1.10] · PF 0.0 · DD 2.23R | 1 · 0 % · E -1.08R · PF 0.0 · DD 1.08R | — / 1.107 / 0.107 | insufficient data (3 OOS) |
| AUDCAD | 0 | 0 | 0 | 0 | — | insufficient data (0 OOS) |
| AUDCHF | 1 · 0 % · E -0.01R · PF 0.0 · DD 0.01R | 0 | 0 | 1 · 0 % · E -0.01R · PF 0.0 · DD 0.01R | — / 0.014 / 0.108 | insufficient data (1 OOS) |
| AUDNZD | 0 | 0 | 0 | 0 | — | insufficient data (0 OOS) |
| NZDJPY | 1 · 100 % · E +5.13R · PF — · DD 0.0R | 1 · 100 % · E +5.13R · PF — · DD 0.0R | 0 | 0 | 5.13 / — / 0.244 | insufficient data (0 OOS) |
| NZDCAD | 2 · 50 % · E +0.48R [-1.15, +2.11] · PF 1.84 · DD 1.15R | 1 · 0 % · E -1.15R · PF 0.0 · DD 1.15R | 1 · 100 % · E +2.11R · PF — · DD 0.0R | 0 | 2.108 / 1.145 / 0.173 | insufficient data (1 OOS) |
| NZDCHF | 2 · 0 % · E -0.06R [-0.08, -0.04] · PF 0.0 · DD 0.13R | 1 · 0 % · E -0.04R · PF 0.0 · DD 0.04R | 0 | 1 · 0 % · E -0.08R · PF 0.0 · DD 0.08R | — / 0.064 / 0.15 | insufficient data (1 OOS) |
| CADJPY | 0 | 0 | 0 | 0 | — | insufficient data (0 OOS) |
| CADCHF | 0 | 0 | 0 | 0 | — | insufficient data (0 OOS) |
| CHFJPY | 2 · 50 % · E +1.26R [-0.02, +2.53] · PF 119.76 · DD 0.02R | 1 · 0 % · E -0.02R · PF 0.0 · DD 0.02R | 1 · 100 % · E +2.53R · PF — · DD 0.0R | 0 | 2.534 / 0.021 / 0.058 | insufficient data (1 OOS) |

### candidate_rr3

| instrument | all | train | validation | test | avg win / loss / cost (R) | evidence |
|---|---|---|---|---|---|---|
| XAUUSD | 0 | 0 | 0 | 0 | — | insufficient data (0 OOS) |
| EURUSD | 3 · 0 % · E -0.69R [-1.04, +0.02] · PF 0.01 · DD 2.06R | 3 · 0 % · E -0.69R [-1.04, +0.02] · PF 0.01 · DD 2.06R | 0 | 0 | — / 0.685 / 0.037 | insufficient data (0 OOS) |
| GBPUSD | 2 · 0 % · E -0.63R [-1.28, +0.02] · PF 0.02 · DD 1.28R | 2 · 0 % · E -0.63R [-1.28, +0.02] · PF 0.02 · DD 1.28R | 0 | 0 | — / 0.63 / 0.235 | insufficient data (0 OOS) |
| USDJPY | 0 | 0 | 0 | 0 | — | insufficient data (0 OOS) |
| USDCAD | 0 | 0 | 0 | 0 | — | insufficient data (0 OOS) |
| USDCHF | 0 | 0 | 0 | 0 | — | insufficient data (0 OOS) |
| AUDUSD | 2 · 0 % · E -0.57R [-1.16, +0.02] · PF 0.02 · DD 1.16R | 1 · 0 % · E -1.16R · PF 0.0 · DD 1.16R | 0 | 1 · 0 % · E +0.02R · PF — · DD 0.0R | — / 0.57 / 0.113 | insufficient data (1 OOS) |
| NZDUSD | 0 | 0 | 0 | 0 | — | insufficient data (0 OOS) |
| GBPJPY | 0 | 0 | 0 | 0 | — | insufficient data (0 OOS) |
| GBPAUD | 0 | 0 | 0 | 0 | — | insufficient data (0 OOS) |
| GBPNZD | 0 | 0 | 0 | 0 | — | insufficient data (0 OOS) |
| GBPCAD | 1 · 0 % · E -1.14R · PF 0.0 · DD 1.14R | 0 | 0 | 1 · 0 % · E -1.14R · PF 0.0 · DD 1.14R | — / 1.136 / 0.136 | insufficient data (1 OOS) |
| GBPCHF | 0 | 0 | 0 | 0 | — | insufficient data (0 OOS) |
| EURGBP | 0 | 0 | 0 | 0 | — | insufficient data (0 OOS) |
| EURJPY | 1 · 100 % · E +3.74R · PF — · DD 0.0R | 1 · 100 % · E +3.74R · PF — · DD 0.0R | 0 | 0 | 3.738 / — / 0.062 | insufficient data (0 OOS) |
| EURAUD | 0 | 0 | 0 | 0 | — | insufficient data (0 OOS) |
| EURNZD | 0 | 0 | 0 | 0 | — | insufficient data (0 OOS) |
| EURCAD | 0 | 0 | 0 | 0 | — | insufficient data (0 OOS) |
| EURCHF | 2 · 0 % · E -1.12R [-1.13, -1.12] · PF 0.0 · DD 2.25R | 2 · 0 % · E -1.12R [-1.13, -1.12] · PF 0.0 · DD 2.25R | 0 | 0 | — / 1.125 / 0.125 | insufficient data (0 OOS) |
| AUDJPY | 2 · 0 % · E -1.09R [-1.10, -1.08] · PF 0.0 · DD 2.19R | 0 | 1 · 0 % · E -1.10R · PF 0.0 · DD 1.1R | 1 · 0 % · E -1.08R · PF 0.0 · DD 1.08R | — / 1.095 / 0.095 | insufficient data (2 OOS) |
| AUDCAD | 0 | 0 | 0 | 0 | — | insufficient data (0 OOS) |
| AUDCHF | 1 · 0 % · E -0.01R · PF 0.0 · DD 0.01R | 0 | 0 | 1 · 0 % · E -0.01R · PF 0.0 · DD 0.01R | — / 0.014 / 0.108 | insufficient data (1 OOS) |
| AUDNZD | 0 | 0 | 0 | 0 | — | insufficient data (0 OOS) |
| NZDJPY | 1 · 100 % · E +5.13R · PF — · DD 0.0R | 1 · 100 % · E +5.13R · PF — · DD 0.0R | 0 | 0 | 5.13 / — / 0.244 | insufficient data (0 OOS) |
| NZDCAD | 0 | 0 | 0 | 0 | — | insufficient data (0 OOS) |
| NZDCHF | 1 · 0 % · E -0.04R · PF 0.0 · DD 0.04R | 1 · 0 % · E -0.04R · PF 0.0 · DD 0.04R | 0 | 0 | — / 0.045 / 0.104 | insufficient data (0 OOS) |
| CADJPY | 0 | 0 | 0 | 0 | — | insufficient data (0 OOS) |
| CADCHF | 0 | 0 | 0 | 0 | — | insufficient data (0 OOS) |
| CHFJPY | 1 · 0 % · E -0.02R · PF 0.0 · DD 0.02R | 1 · 0 % · E -0.02R · PF 0.0 · DD 0.02R | 0 | 0 | — / 0.021 / 0.063 | insufficient data (0 OOS) |

### candidate_rr4

| instrument | all | train | validation | test | avg win / loss / cost (R) | evidence |
|---|---|---|---|---|---|---|
| XAUUSD | 0 | 0 | 0 | 0 | — | insufficient data (0 OOS) |
| EURUSD | 1 · 0 % · E -1.04R · PF 0.0 · DD 1.04R | 1 · 0 % · E -1.04R · PF 0.0 · DD 1.04R | 0 | 0 | — / 1.04 / 0.04 | insufficient data (0 OOS) |
| GBPUSD | 2 · 0 % · E -0.63R [-1.28, +0.02] · PF 0.02 · DD 1.28R | 2 · 0 % · E -0.63R [-1.28, +0.02] · PF 0.02 · DD 1.28R | 0 | 0 | — / 0.63 / 0.235 | insufficient data (0 OOS) |
| USDJPY | 0 | 0 | 0 | 0 | — | insufficient data (0 OOS) |
| USDCAD | 0 | 0 | 0 | 0 | — | insufficient data (0 OOS) |
| USDCHF | 0 | 0 | 0 | 0 | — | insufficient data (0 OOS) |
| AUDUSD | 1 · 0 % · E -1.16R · PF 0.0 · DD 1.16R | 1 · 0 % · E -1.16R · PF 0.0 · DD 1.16R | 0 | 0 | — / 1.161 / 0.161 | insufficient data (0 OOS) |
| NZDUSD | 0 | 0 | 0 | 0 | — | insufficient data (0 OOS) |
| GBPJPY | 0 | 0 | 0 | 0 | — | insufficient data (0 OOS) |
| GBPAUD | 0 | 0 | 0 | 0 | — | insufficient data (0 OOS) |
| GBPNZD | 0 | 0 | 0 | 0 | — | insufficient data (0 OOS) |
| GBPCAD | 0 | 0 | 0 | 0 | — | insufficient data (0 OOS) |
| GBPCHF | 0 | 0 | 0 | 0 | — | insufficient data (0 OOS) |
| EURGBP | 0 | 0 | 0 | 0 | — | insufficient data (0 OOS) |
| EURJPY | 0 | 0 | 0 | 0 | — | insufficient data (0 OOS) |
| EURAUD | 0 | 0 | 0 | 0 | — | insufficient data (0 OOS) |
| EURNZD | 0 | 0 | 0 | 0 | — | insufficient data (0 OOS) |
| EURCAD | 0 | 0 | 0 | 0 | — | insufficient data (0 OOS) |
| EURCHF | 1 · 0 % · E -1.12R · PF 0.0 · DD 1.12R | 1 · 0 % · E -1.12R · PF 0.0 · DD 1.12R | 0 | 0 | — / 1.117 / 0.117 | insufficient data (0 OOS) |
| AUDJPY | 1 · 0 % · E -1.10R · PF 0.0 · DD 1.1R | 0 | 1 · 0 % · E -1.10R · PF 0.0 · DD 1.1R | 0 | — / 1.104 / 0.104 | insufficient data (1 OOS) |
| AUDCAD | 0 | 0 | 0 | 0 | — | insufficient data (0 OOS) |
| AUDCHF | 0 | 0 | 0 | 0 | — | insufficient data (0 OOS) |
| AUDNZD | 0 | 0 | 0 | 0 | — | insufficient data (0 OOS) |
| NZDJPY | 1 · 100 % · E +5.13R · PF — · DD 0.0R | 1 · 100 % · E +5.13R · PF — · DD 0.0R | 0 | 0 | 5.13 / — / 0.244 | insufficient data (0 OOS) |
| NZDCAD | 0 | 0 | 0 | 0 | — | insufficient data (0 OOS) |
| NZDCHF | 0 | 0 | 0 | 0 | — | insufficient data (0 OOS) |
| CADJPY | 0 | 0 | 0 | 0 | — | insufficient data (0 OOS) |
| CADCHF | 0 | 0 | 0 | 0 | — | insufficient data (0 OOS) |
| CHFJPY | 1 · 0 % · E -0.02R · PF 0.0 · DD 0.02R | 1 · 0 % · E -0.02R · PF 0.0 · DD 0.02R | 0 | 0 | — / 0.021 / 0.063 | insufficient data (0 OOS) |

## What this shows

- The most out-of-sample trades any instrument has on the candidate is 3; the requirement is 100. No instrument is validated: the evidence is insufficient.
- A positive or negative total on a handful of trades is not a result: the intervals above are wide and most cross 0.
- Nothing here says the strategy is profitable.
