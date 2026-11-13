# FXAlexG Set & Forget, measured

VERIFIED from the Dukascopy candles, 2025-11-05 → 2026-11-05 (split 2026-06-12), 6 pairs with stored data. Every trade followed on M5: at +1.5 R the stop goes to the entry + 2 pips; a trade not in profit is closed on Friday 20:00 UTC; the stop before the target inside a candle; spread + slippage included. 1R = the risk of one trade.

A win = a result above +0.05 R; a close at entry + 2 pips after +1.5 R is a small win. The exits column shows full targets / closes between 0 and 1 R / stops apart.

| pair | closed confirmations at an AOI | executed (SF_BR · SF_BOUNCE · SF_COUNTER) | win rate | result | PF | first 60 % | last 40 % | without the news rule | exits (TP / BE / SL) |
|---|---|---|---|---|---|---|---|---|---|
| XAUUSD | 130 | 1 (SF_BR 0 · SF_BOUNCE 0 · SF_COUNTER 1) | 0 % | -1.01R | 0.0 | 0 trades | 1 · win 0 % · -1.01R | 1 · win 0 % · -1.01R | 0 / 0 / 1 |
| EURUSD | 162 | 4 (SF_BR 3 · SF_BOUNCE 0 · SF_COUNTER 1) | 25 % | -0.41R | 0.87 | 2 · win 0 % · -2.09R | 2 · win 50 % · +1.67R | 4 · win 25 % · -0.41R | 1 / 0 / 3 |
| GBPUSD | 193 | 6 (SF_BR 5 · SF_BOUNCE 0 · SF_COUNTER 1) | 33 % | +3.98R | 2.22 | 2 · win 50 % · +4.0R | 4 · win 25 % · -0.02R | 7 · win 29 % · +2.91R | 2 / 1 / 3 |
| EURCHF | 75 | 1 (SF_BR 0 · SF_BOUNCE 0 · SF_COUNTER 1) | 0 % | -1.11R | 0.0 | 1 · win 0 % · -1.11R | 0 trades | 1 · win 0 % · -1.11R | 0 / 0 / 1 |
| AUDCAD | 140 | 3 (SF_BR 2 · SF_BOUNCE 0 · SF_COUNTER 1) | 0 % | -3.39R | 0.0 | 2 · win 0 % · -2.28R | 1 · win 0 % · -1.11R | 3 · win 0 % · -3.39R | 0 / 0 / 3 |
| AUDCHF | 78 | 1 (SF_BR 1 · SF_BOUNCE 0 · SF_COUNTER 0) | 0 % | -1.2R | 0.0 | 0 trades | 1 · win 0 % · -1.2R | 1 · win 0 % · -1.2R | 0 / 0 / 1 |
| all · SF_BR | | 11 | 27 % | +1.14R | | | | | |
| all · SF_BOUNCE | | 0 | — % | +0.00R | | | | | |
| all · SF_COUNTER | | 5 | 0 % | -4.28R | | | | | |

All pairs: 16 · win 19 % · -3.14R, PF 0.76, expectancy -0.196 R per trade. First 60 %: 7 · win 14 % · -1.48R. Last 40 %: 9 · win 22 % · -1.66R. Without the news rule: 17 · win 18 % · -4.21R.

Under 30 trades a win rate can still be luck. The portfolio cap is not applied here (each pair alone).
