# FXAlexG Set & Forget, measured

VERIFIED from the app's feed (Yahoo Finance forex, COMEX GC=F adjusted to spot for gold) candles, 2024-11-19 → 2026-11-19 (split at 60 %), 29 pairs. The trigger is read on H1 only and every trade is followed on H1 candles (a candle reaching both the stop and the target counts as the stop). At +1.5 R the stop goes to the entry and 25 % is banked (+0.375 R); spread + slippage included. 1R = the risk of one trade.

A win = a result above +0.05 R (a break-even close after +1.5 R is a small win). Exits: full targets / break-even after +1.5 R / stops.

| pair | two-step triggers at an AOI | executed (S&F-SWING · S&F-DAY) | win rate | result | PF | first 60 % | last 40 % | exits (TP / BE / SL) |
|---|---|---|---|---|---|---|---|---|
| XAUUSD | 1 | 0 (0 · 0) | — | +0.0R | — | 0 trades | 0 trades | 0 / 0 / 0 |
| EURUSD | 202 | 10 (5 · 5) | 50 % | -0.84R | 0.84 | 6 · win 50 % · -2.09R | 4 · win 50 % · +1.25R | 1 / 4 / 5 |
| GBPUSD | 210 | 3 (2 · 1) | 67 % | +2.2R | 3.12 | 3 · win 67 % · +2.2R | 0 trades | 1 / 1 / 1 |
| USDJPY | 208 | 11 (10 · 1) | 45 % | -0.68R | 0.89 | 9 · win 33 % · -5.18R | 2 · win 100 % · +4.49R | 2 / 3 / 6 |
| USDCAD | 258 | 10 (3 · 7) | 30 % | -3.89R | 0.48 | 6 · win 33 % · -0.94R | 4 · win 25 % · -2.96R | 1 / 2 / 7 |
| USDCHF | 215 | 8 (6 · 2) | 50 % | +4.33R | 2.02 | 6 · win 50 % · +5.07R | 2 · win 50 % · -0.74R | 3 / 1 / 4 |
| AUDUSD | 237 | 4 (3 · 1) | 25 % | -2.83R | 0.11 | 3 · win 33 % · -1.78R | 1 · win 0 % · -1.05R | 0 / 1 / 3 |
| NZDUSD | 265 | 9 (7 · 2) | 22 % | -4.08R | 0.45 | 5 · win 40 % · +0.11R | 4 · win 0 % · -4.19R | 1 / 1 / 7 |
| GBPJPY | 178 | 5 (5 · 0) | 80 % | +4.4R | 5.04 | 4 · win 100 % · +5.48R | 1 · win 0 % · -1.09R | 2 / 2 / 1 |
| GBPAUD | 175 | 7 (7 · 0) | 57 % | +2.18R | 1.67 | 1 · win 100 % · +2.59R | 6 · win 50 % · -0.41R | 2 / 2 / 3 |
| GBPNZD | 148 | 1 (0 · 1) | 0 % | -1.12R | 0.0 | 1 · win 0 % · -1.12R | 0 trades | 0 / 0 / 1 |
| GBPCAD | 224 | 4 (3 · 1) | 75 % | +1.74R | 2.68 | 1 · win 0 % · -1.04R | 3 · win 100 % · +2.78R | 1 / 2 / 1 |
| GBPCHF | 260 | 5 (5 · 0) | 20 % | -4.14R | 0.06 | 3 · win 33 % · -1.96R | 2 · win 0 % · -2.18R | 0 / 1 / 4 |
| EURGBP | 283 | 14 (8 · 6) | 21 % | -4.52R | 0.62 | 10 · win 30 % · -0.2R | 4 · win 0 % · -4.32R | 3 / 0 / 11 |
| EURJPY | 182 | 2 (2 · 0) | 50 % | -0.74R | 0.31 | 1 · win 100 % · +0.34R | 1 · win 0 % · -1.08R | 0 / 1 / 1 |
| EURAUD | 183 | 3 (2 · 1) | 33 % | -0.02R | 0.99 | 1 · win 0 % · -1.14R | 2 · win 50 % · +1.12R | 1 / 0 / 2 |
| EURNZD | 132 | 2 (2 · 0) | 0 % | -2.14R | 0.0 | 2 · win 0 % · -2.14R | 0 trades | 0 / 0 / 2 |
| EURCAD | 266 | 10 (8 · 2) | 20 % | -5.54R | 0.37 | 4 · win 0 % · -4.39R | 6 · win 33 % · -1.16R | 1 / 1 / 8 |
| EURCHF | 339 | 15 (7 · 8) | 27 % | -8.65R | 0.27 | 7 · win 43 % · -1.46R | 8 · win 12 % · -7.19R | 1 / 3 / 11 |
| AUDJPY | 203 | 6 (6 · 0) | 17 % | -2.87R | 0.46 | 3 · win 0 % · -3.19R | 3 · win 33 % · +0.32R | 1 / 0 / 5 |
| AUDCAD | 287 | 8 (5 · 3) | 25 % | -3.68R | 0.43 | 6 · win 17 % · -3.18R | 2 · win 50 % · -0.5R | 1 / 1 / 6 |
| AUDCHF | 285 | 11 (10 · 1) | 36 % | -3.91R | 0.5 | 7 · win 29 % · -2.24R | 4 · win 50 % · -1.67R | 1 / 3 / 7 |
| AUDNZD | 220 | 4 (3 · 1) | 75 % | +2.19R | 2.92 | 4 · win 75 % · +2.19R | 0 trades | 1 / 2 / 1 |
| NZDJPY | 260 | 5 (4 · 1) | 40 % | -2.75R | 0.17 | 3 · win 33 % · -1.92R | 2 · win 50 % · -0.84R | 0 / 2 / 3 |
| NZDCAD | 316 | 7 (4 · 3) | 43 % | -1.74R | 0.61 | 6 · win 33 % · -1.99R | 1 · win 100 % · +0.25R | 1 / 2 / 4 |
| NZDCHF | 227 | 11 (6 · 5) | 36 % | -1.59R | 0.8 | 5 · win 60 % · +3.77R | 6 · win 17 % · -5.36R | 2 / 2 / 7 |
| CADJPY | 240 | 3 (3 · 0) | 67 % | +0.48R | 1.43 | 1 · win 100 % · +1.36R | 2 · win 50 % · -0.88R | 1 / 1 / 1 |
| CADCHF | 317 | 16 (13 · 3) | 25 % | -7.28R | 0.44 | 9 · win 33 % · -1.0R | 7 · win 14 % · -6.28R | 2 / 2 / 12 |
| CHFJPY | 129 | 1 (1 · 0) | 100 % | +0.3R | — | 0 trades | 1 · win 100 % · +0.3R | 0 / 1 / 0 |

**All pairs: 195 · win 36 % · -45.2R, PF 0.66, expectancy -0.232 R per trade.** First 60 %: 117 · win 38 % · -13.84R. Last 40 %: 78 · win 33 % · -31.36R.

The spec's target is PF > 1.5 and a win rate >= 50 %: NOT met on this sample.
Under 30 trades a win rate can still be luck. The portfolio check is not applied here (each pair alone).
