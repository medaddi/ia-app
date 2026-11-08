# The guide's strategies, measured

VERIFIED from the Dukascopy candles, 2025-11-05 → 2026-11-05 (split 2026-06-12). Every trade followed on M5, the stop before the target inside a candle, spread + slippage included. 1R = the risk of one trade (1 % of the account). A trade counts only when its checklist passed.

News: the guide's red-folder pause for every pair (US CPI, NFP, FOMC, BoE, RBA, BoC, SNB from the stored ForexFactory calendar + the EIA Wednesdays): no signal within 15 min of one, a pending limit pulled 15 min before one. Targets cut when ADR5 / ADR20 < 0.70. AUD/CHF: the S&P 500 / VIX / iron ore gate and its risk-off exit.

| pair | strategy | the guide says | trades | win rate | result | first 60 % | last 40 % | without the news rule | kept trades open through a release |
|---|---|---|---|---|---|---|---|---|---|
| XAUUSD | S1 Bullish Asian / London low sweep + M5 displacement & FVG | spec example: 61.9 % on 42 setups (90 days) | 6 | 50 % | +0.95R | 4 · win 50 % · +1.54R | 2 · win 50 % · -0.59R | 6 · win 50 % · +0.95R | 0 |
| XAUUSD | S2 Bearish Asian / London high sweep + M5 displacement & FVG · **OFF** | the spec gives no win rate: measured here | 6 | 33 % | -3.55R | 4 · win 25 % · -2.61R | 2 · win 50 % · -0.94R | 7 · win 43 % · -3.41R | 0 |
| XAUUSD | S3 NY COMEX momentum continuation pullback · **OFF** | the spec gives no win rate: measured here | 4 | 25 % | -0.89R | 3 · win 33 % · +0.15R | 1 · win 0 % · -1.03R | 5 · win 40 % · +1.3R | 0 |
| XAUUSD | S4 PDH / PDL rejection + M15 MSS · **OFF** | the spec gives no win rate: measured here | 21 | 38 % | +0.89R | 11 · win 45 % · +3.09R | 10 · win 30 % · -2.21R | 21 · win 38 % · +0.89R | 1 |
| EURUSD | S1 Bullish London / NY Judas into discount POI | the spec gives no win rate: measured here | 0 | — | +0.0R | 0 trades | 0 trades | 0 trades | 0 |
| EURUSD | S2 Bearish London / NY Judas into premium POI | the spec gives no win rate: measured here | 0 | — | +0.0R | 0 trades | 0 trades | 0 trades | 0 |
| EURUSD | S3 NY raid of the London extremes + OTE · **OFF** | the spec gives no win rate: measured here | 5 | 0 % | -5.74R | 4 · win 0 % · -4.56R | 1 · win 0 % · -1.18R | 6 · win 0 % · -6.83R | 0 |
| EURUSD | S4 Daily VWAP rotation · **OFF** | the spec gives no win rate: measured here | 7 | 29 % | -2.39R | 4 · win 50 % · +1.02R | 3 · win 0 % · -3.41R | 9 · win 33 % · -2.44R | 0 |
| EURUSD | SB SnapBack 3σ mean reversion (kept) | 62.0 % (SteadyPips, 79 trades, 1:1); 70 % on our 1-year test | 27 | 70 % | +9.68R | 14 · win 71 % · +5.31R | 13 · win 69 % · +4.37R | 27 · win 70 % · +9.68R | 4 |
| GBPUSD | S1 Bullish deep sweep + M15 reclaim + M5 breaker · **OFF** | the spec gives no win rate: measured here | 15 | 20 % | -6.83R | 10 · win 20 % · -5.07R | 5 · win 20 % · -1.76R | 16 · win 19 % · -7.91R | 3 |
| GBPUSD | S2 Bearish deep sweep + M15 reclaim + M5 breaker | the spec gives no win rate: measured here | 16 | 50 % | +7.91R | 9 · win 44 % · +6.19R | 7 · win 57 % · +1.72R | 16 · win 50 % · +7.91R | 3 |
| GBPUSD | S3 London open volatility squeeze · **OFF** | the spec gives no win rate: measured here | 15 | 33 % | -0.1R | 11 · win 27 % · -0.84R | 4 · win 50 % · +0.74R | 15 · win 33 % · -0.1R | 2 |
| GBPUSD | S4 NY overlap pullback to the H1 order block · **OFF** | the spec gives no win rate: measured here | 15 | 33 % | -6.67R | 9 · win 44 % · -3.04R | 6 · win 17 % · -3.63R | 15 · win 33 % · -6.67R | 3 |
| EURCHF | S1 Bullish extreme discount fade (Z <= -2.2) · **OFF** | spec example: 68.4 % on 2.2σ fades | 8 | 0 % | -10.14R | 6 · win 0 % · -7.87R | 2 · win 0 % · -2.27R | 9 · win 0 % · -11.27R | 3 |
| EURCHF | S2 Bearish extreme premium fade (Z >= +2.2) | the spec gives no win rate: measured here | 11 | 64 % | +6.31R | 9 · win 56 % · +2.82R | 2 · win 100 % · +3.48R | 11 · win 64 % · +6.31R | 2 |
| EURCHF | S3 VWAP ± 2.5σ European exhaustion · **OFF** | the spec gives no win rate: measured here | 13 | 31 % | -7.81R | 12 · win 25 % · -9.54R | 1 · win 100 % · +1.74R | 14 · win 29 % · -8.93R | 2 |
| AUDCAD | P Commodity range reversion (kept) | ~60 %+; 59 % on our 1-year test | 17 | 59 % | +5.94R | 6 · win 67 % · +2.19R | 11 · win 55 % · +3.75R | 17 · win 59 % · +5.94R | 5 |
| AUDCHF | S1 Risk-on trend pullback (OTE + H1 OB + M15 BOS) | the spec gives no win rate: measured here | 0 | — | +0.0R | 0 trades | 0 trades | 0 trades | 0 |
| AUDCHF | S2 Risk-off trend pullback (OTE + H1 OB + M15 BOS) | the spec gives no win rate: measured here | 0 | — | +0.0R | 0 trades | 0 trades | 0 trades | 0 |
| AUDCHF | S3 Bullish quiet-regime range fade | the spec gives no win rate: measured here | 0 | — | +0.0R | 0 trades | 0 trades | 0 trades | 0 |
| AUDCHF | S4 Bearish quiet-regime range fade | the spec gives no win rate: measured here | 0 | — | +0.0R | 0 trades | 0 trades | 0 trades | 0 |

Every strategy, each measured as if switched on: 186 trades, win rate 41 %, -12.44R.
Switched on only: 77 trades, win rate 61 %, +30.79R (chosen on this same year: an optimistic number, not a forecast).

Not applied here: the correlation cap (each pair alone). Under 30 trades a win rate can still be luck.
