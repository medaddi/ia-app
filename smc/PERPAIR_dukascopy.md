# Each pair: which strategy, chosen on the first part, held up on the unseen part?

VERIFIED from the Dukascopy candles. In-sample 2025-11-05 → 2026-06-12, out-of-sample 2026-06-12 → 2026-11-05. Results with the management (50 % at 1:3 + break-even after an M5 BOS), costs included, in R (1R = $100 at 1 % of $10,000).

Rule written BEFORE the run: a strategy is chosen for a pair when its in-sample expectancy is > 0 R with at least 3 trades. Only the out-of-sample column tests that choice.

## XAUUSD

| strategy | gate | in-sample | chosen? | out-of-sample |
|---|---|---|---|---|
| S1 | strict | 0 tr | no | 0 tr |
| S1 | A | 0 tr | no | 0 tr |
| S1 | B | 1 tr · win 0 % · -1.02R | no | 1 tr · win 0 % · -0.03R |
| S1 | rules | 2 tr · win 50 % · -0.39R | no | 1 tr · win 0 % · -0.03R |
| S2 | strict | 0 tr | no | 0 tr |
| S2 | A | 3 tr · win 67 % · +2.98R | **yes** | 2 tr · win 50 % · +1.89R |
| S2 | B | 3 tr · win 67 % · +2.98R | **yes** | 3 tr · win 33 % · +1.87R |
| S2 | rules | 8 tr · win 38 % · +1.73R | **yes** | 5 tr · win 40 % · +4.2R |
| S3 | strict | 3 tr · win 33 % · +0.88R | **yes** | 5 tr · win 0 % · -4.19R |
| S3 | A | 3 tr · win 33 % · +0.88R | **yes** | 5 tr · win 0 % · -4.19R |
| S3 | B | 7 tr · win 14 % · -2.19R | no | 7 tr · win 14 % · -3.64R |
| S3 | rules | 27 tr · win 26 % · -1.96R | no | 20 tr · win 25 % · -2.43R |
| S4 | strict | 2 tr · win 50 % · +0.65R | no | 1 tr · win 100 % · +2.78R |
| S4 | A | 4 tr · win 25 % · -0.43R | no | 2 tr · win 100 % · +5.38R |
| S4 | B | 16 tr · win 19 % · -5.49R | no | 3 tr · win 67 % · +4.34R |
| S4 | rules | 47 tr · win 19 % · -17.09R | no | 27 tr · win 22 % · -0.53R |

## EURUSD

| strategy | gate | in-sample | chosen? | out-of-sample |
|---|---|---|---|---|
| S1 | strict | 0 tr | no | 1 tr · win 100 % · +1.15R |
| S1 | A | 0 tr | no | 1 tr · win 100 % · +1.15R |
| S1 | B | 1 tr · win 0 % · -1.11R | no | 1 tr · win 100 % · +1.15R |
| S1 | rules | 2 tr · win 0 % · -1.22R | no | 2 tr · win 100 % · +3.69R |
| S2 | strict | 0 tr | no | 0 tr |
| S2 | A | 1 tr · win 0 % · -1.17R | no | 1 tr · win 0 % · -1.14R |
| S2 | B | 3 tr · win 0 % · -2.44R | no | 3 tr · win 0 % · -2.37R |
| S2 | rules | 14 tr · win 29 % · -1.05R | no | 9 tr · win 22 % · -2.98R |
| S3 | strict | 1 tr · win 0 % · -1.18R | no | 0 tr |
| S3 | A | 1 tr · win 0 % · -1.18R | no | 0 tr |
| S3 | B | 4 tr · win 75 % · +4.88R | **yes** | 1 tr · win 0 % · -0.11R |
| S3 | rules | 13 tr · win 46 % · +6.55R | **yes** | 4 tr · win 0 % · -1.41R |
| S4 | strict | 2 tr · win 0 % · -2.19R | no | 1 tr · win 100 % · +2.36R |
| S4 | A | 4 tr · win 25 % · -2.04R | no | 2 tr · win 50 % · +2.2R |
| S4 | B | 12 tr · win 33 % · -0.63R | no | 5 tr · win 40 % · +0.25R |
| S4 | rules | 43 tr · win 30 % · -11.86R | no | 19 tr · win 37 % · -1.39R |

## GBPUSD

| strategy | gate | in-sample | chosen? | out-of-sample |
|---|---|---|---|---|
| S1 | strict | 0 tr | no | 0 tr |
| S1 | A | 0 tr | no | 0 tr |
| S1 | B | 1 tr · win 0 % · -1.09R | no | 0 tr |
| S1 | rules | 4 tr · win 0 % · -3.72R | no | 1 tr · win 0 % · -0.68R |
| S2 | strict | 0 tr | no | 0 tr |
| S2 | A | 0 tr | no | 0 tr |
| S2 | B | 2 tr · win 0 % · -1.19R | no | 3 tr · win 0 % · -1.41R |
| S2 | rules | 3 tr · win 0 % · -1.36R | no | 8 tr · win 25 % · -0.94R |
| S3 | strict | 3 tr · win 33 % · +1.06R | **yes** | 0 tr |
| S3 | A | 3 tr · win 33 % · +1.06R | **yes** | 0 tr |
| S3 | B | 5 tr · win 20 % · -1.24R | no | 1 tr · win 0 % · -0.17R |
| S3 | rules | 14 tr · win 36 % · +2.16R | **yes** | 4 tr · win 0 % · -2.61R |
| S4 | strict | 2 tr · win 50 % · +0.24R | no | 0 tr |
| S4 | A | 3 tr · win 33 % · +0.12R | **yes** | 0 tr |
| S4 | B | 11 tr · win 18 % · -5.95R | no | 4 tr · win 50 % · -0.2R |
| S4 | rules | 38 tr · win 13 % · -21.19R | no | 16 tr · win 19 % · -3.43R |

## EURCHF

| strategy | gate | in-sample | chosen? | out-of-sample |
|---|---|---|---|---|
| S1 | strict | 0 tr | no | 0 tr |
| S1 | A | 0 tr | no | 0 tr |
| S1 | B | 0 tr | no | 0 tr |
| S1 | rules | 0 tr | no | 0 tr |
| S2 | strict | 0 tr | no | 0 tr |
| S2 | A | 0 tr | no | 0 tr |
| S2 | B | 0 tr | no | 0 tr |
| S2 | rules | 0 tr | no | 0 tr |
| S3 | strict | 0 tr | no | 0 tr |
| S3 | A | 0 tr | no | 0 tr |
| S3 | B | 1 tr · win 100 % · +0.54R | no | 0 tr |
| S3 | rules | 2 tr · win 100 % · +2.23R | no | 2 tr · win 0 % · -1.38R |
| S4 | strict | 0 tr | no | 0 tr |
| S4 | A | 0 tr | no | 0 tr |
| S4 | B | 2 tr · win 0 % · -1.36R | no | 0 tr |
| S4 | rules | 5 tr · win 0 % · -4.2R | no | 7 tr · win 29 % · +0.31R |

## AUDCAD

| strategy | gate | in-sample | chosen? | out-of-sample |
|---|---|---|---|---|
| S1 | strict | 0 tr | no | 1 tr · win 0 % · -0.2R |
| S1 | A | 0 tr | no | 1 tr · win 0 % · -0.2R |
| S1 | B | 0 tr | no | 1 tr · win 0 % · -0.2R |
| S1 | rules | 0 tr | no | 1 tr · win 0 % · -0.2R |
| S2 | strict | 0 tr | no | 0 tr |
| S2 | A | 0 tr | no | 0 tr |
| S2 | B | 0 tr | no | 0 tr |
| S2 | rules | 6 tr · win 0 % · -3.96R | no | 2 tr · win 0 % · -1.35R |
| S3 | strict | 1 tr · win 0 % · -1.2R | no | 0 tr |
| S3 | A | 1 tr · win 0 % · -1.2R | no | 0 tr |
| S3 | B | 3 tr · win 33 % · -0.06R | no | 0 tr |
| S3 | rules | 6 tr · win 50 % · +2.96R | **yes** | 1 tr · win 0 % · -0.14R |
| S4 | strict | 1 tr · win 100 % · +2.23R | no | 0 tr |
| S4 | A | 1 tr · win 100 % · +2.23R | no | 0 tr |
| S4 | B | 3 tr · win 67 % · +1.21R | **yes** | 0 tr |
| S4 | rules | 20 tr · win 30 % · -2.44R | no | 5 tr · win 0 % · -2.93R |

## AUDCHF

| strategy | gate | in-sample | chosen? | out-of-sample |
|---|---|---|---|---|
| S1 | strict | 0 tr | no | 0 tr |
| S1 | A | 0 tr | no | 0 tr |
| S1 | B | 0 tr | no | 0 tr |
| S1 | rules | 2 tr · win 0 % · -0.69R | no | 0 tr |
| S2 | strict | 0 tr | no | 0 tr |
| S2 | A | 0 tr | no | 0 tr |
| S2 | B | 0 tr | no | 0 tr |
| S2 | rules | 2 tr · win 0 % · -1.3R | no | 1 tr · win 100 % · +0.94R |
| S3 | strict | 0 tr | no | 0 tr |
| S3 | A | 0 tr | no | 0 tr |
| S3 | B | 0 tr | no | 0 tr |
| S3 | rules | 1 tr · win 100 % · +1.08R | no | 0 tr |
| S4 | strict | 0 tr | no | 1 tr · win 0 % · -1.19R |
| S4 | A | 0 tr | no | 2 tr · win 50 % · +0.01R |
| S4 | B | 1 tr · win 0 % · -0.2R | no | 2 tr · win 50 % · +0.01R |
| S4 | rules | 3 tr · win 0 % · -1.87R | no | 2 tr · win 50 % · +0.01R |

## What the choices did on the unseen part

| gate | strategies chosen (pair · strategy) | out-of-sample trades | win rate | result |
|---|---|---|---|---|
| strict | XAUUSD S3 | 5 | 0 % | -4.19R ($-419) |
| A | XAUUSD S2, XAUUSD S3 | 7 | 14 % | -2.31R ($-231) |
| B | EURUSD S3, XAUUSD S2 | 4 | 25 % | +1.75R ($+175) |
| rules | AUDCAD S3, EURUSD S3, GBPUSD S3, XAUUSD S2 | 14 | 14 % | +0.04R ($+4) |

Under 30 out-of-sample trades, a positive number is a hint to keep testing, not proof.
