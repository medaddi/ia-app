# Data quality

VERIFIED from the CSV files (Yahoo Finance). NOT FIT: flat >= 2 % or opening jumps >= 5 % (defects of the candles). SUSPECT (HYPOTHESIS): a cross whose median range is above EUR/USD's on the same timeframe. FIT otherwise.

| pair | TF | rows | flat | jumps | median range (pips) | verdict |
|---|---|---|---|---|---|---|
| XAUUSD | H1 | 13766 | 0.1% | 1.0% | 124.0 | FIT |
| XAUUSD | M15 | 4518 | 0.1% | 0.6% | 69.0 | FIT |
| XAUUSD | M5 | 13521 | 0.0% | 0.4% | 39.0 | FIT |
| EURUSD | H1 | 17286 | 0.7% | 3.9% | 9.2 | FIT |
| EURUSD | M15 | 5643 | 1.4% | 13.3% | 3.8 | NOT FIT: opening jumps |
| EURUSD | M5 | 16927 | 15.0% | 32.2% | 1.3 | NOT FIT: flat candles, opening jumps |
| GBPUSD | H1 | 17288 | 0.8% | 4.0% | 11.4 | FIT |
| GBPUSD | M15 | 5644 | 0.4% | 9.4% | 4.2 | NOT FIT: opening jumps |
| GBPUSD | M5 | 16930 | 0.5% | 34.2% | 1.8 | NOT FIT: opening jumps |
| EURCHF | H1 | 17294 | 0.5% | 1.6% | 10.9 | SUSPECT: range above EUR/USD (9.2) |
| EURCHF | M15 | 5644 | 0.4% | 1.3% | 7.2 | SUSPECT: range above EUR/USD (3.8) |
| EURCHF | M5 | 16928 | 0.4% | 2.0% | 5.9 | SUSPECT: range above EUR/USD (1.3) |
| AUDCAD | H1 | 17352 | 0.8% | 1.2% | 17.4 | SUSPECT: range above EUR/USD (9.2) |
| AUDCAD | M15 | 5650 | 0.5% | 1.8% | 12.4 | SUSPECT: range above EUR/USD (3.8) |
| AUDCAD | M5 | 16937 | 0.4% | 0.9% | 10.6 | SUSPECT: range above EUR/USD (1.3) |
| AUDCHF | H1 | 17341 | 0.2% | 1.8% | 13.4 | SUSPECT: range above EUR/USD (9.2) |
| AUDCHF | M15 | 5657 | 0.5% | 2.4% | 9.4 | SUSPECT: range above EUR/USD (3.8) |
| AUDCHF | M5 | 16944 | 0.4% | 1.4% | 8.1 | SUSPECT: range above EUR/USD (1.3) |

Gold (GC=F) is COMEX futures, not spot: its candles are clean, its levels are not spot prices.
