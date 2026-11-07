# Each pair: which strategy, chosen on the first part, held up on the unseen part?

VERIFIED from the Yahoo candles. In-sample 2026-08-28 → 2026-10-09, out-of-sample 2026-10-09 → 2026-11-06. Results with the management (50 % at 1:3 + break-even after an M5 BOS), costs included, in R (1R = $100 at 1 % of $10,000).

Rule written BEFORE the run: a strategy is chosen for a pair when its in-sample expectancy is > 0 R with at least 3 trades. Only the out-of-sample column tests that choice.

## XAUUSD

| strategy | gate | in-sample | chosen? | out-of-sample |
|---|---|---|---|---|
| S1 | strict | 0 tr | no | 0 tr |
| S1 | A | 0 tr | no | 0 tr |
| S1 | B | 1 tr · win 0 % · -0.03R | no | 0 tr |
| S2 | strict | 0 tr | no | 0 tr |
| S2 | A | 1 tr · win 0 % · -1.03R | no | 0 tr |
| S2 | B | 1 tr · win 0 % · -1.03R | no | 0 tr |
| S3 | strict | 2 tr · win 0 % · -2.09R | no | 0 tr |
| S3 | A | 2 tr · win 0 % · -2.09R | no | 0 tr |
| S3 | B | 2 tr · win 0 % · -2.09R | no | 1 tr · win 0 % · -1.03R |
| S4 | strict | 2 tr · win 50 % · +2.8R | no | 0 tr |
| S4 | A | 3 tr · win 67 % · +5.34R | **yes** | 0 tr |
| S4 | B | 3 tr · win 67 % · +5.34R | **yes** | 0 tr |

## EURUSD

| strategy | gate | in-sample | chosen? | out-of-sample |
|---|---|---|---|---|
| S1 | strict | 0 tr | no | 0 tr |
| S1 | A | 0 tr | no | 0 tr |
| S1 | B | 0 tr | no | 0 tr |
| S2 | strict | 0 tr | no | 0 tr |
| S2 | A | 0 tr | no | 0 tr |
| S2 | B | 0 tr | no | 1 tr · win 0 % · -1.16R |
| S3 | strict | 0 tr | no | 0 tr |
| S3 | A | 0 tr | no | 0 tr |
| S3 | B | 0 tr | no | 1 tr · win 0 % · -1.16R |
| S4 | strict | 1 tr · win 100 % · +0.91R | no | 0 tr |
| S4 | A | 1 tr · win 100 % · +0.91R | no | 0 tr |
| S4 | B | 3 tr · win 33 % · -1.4R | no | 2 tr · win 100 % · +4.32R |

## GBPUSD

| strategy | gate | in-sample | chosen? | out-of-sample |
|---|---|---|---|---|
| S1 | strict | 0 tr | no | 0 tr |
| S1 | A | 0 tr | no | 0 tr |
| S1 | B | 0 tr | no | 0 tr |
| S2 | strict | 0 tr | no | 0 tr |
| S2 | A | 0 tr | no | 0 tr |
| S2 | B | 1 tr · win 0 % · -1.2R | no | 2 tr · win 50 % · -0.42R |
| S3 | strict | 0 tr | no | 0 tr |
| S3 | A | 0 tr | no | 0 tr |
| S3 | B | 0 tr | no | 0 tr |
| S4 | strict | 0 tr | no | 0 tr |
| S4 | A | 0 tr | no | 0 tr |
| S4 | B | 0 tr | no | 0 tr |

## EURCHF

| strategy | gate | in-sample | chosen? | out-of-sample |
|---|---|---|---|---|
| S1 | strict | 0 tr | no | 0 tr |
| S1 | A | 0 tr | no | 0 tr |
| S1 | B | 0 tr | no | 0 tr |
| S2 | strict | 0 tr | no | 0 tr |
| S2 | A | 0 tr | no | 0 tr |
| S2 | B | 0 tr | no | 0 tr |
| S3 | strict | 0 tr | no | 0 tr |
| S3 | A | 0 tr | no | 0 tr |
| S3 | B | 0 tr | no | 0 tr |
| S4 | strict | 0 tr | no | 0 tr |
| S4 | A | 0 tr | no | 0 tr |
| S4 | B | 0 tr | no | 0 tr |

## AUDCAD

| strategy | gate | in-sample | chosen? | out-of-sample |
|---|---|---|---|---|
| S1 | strict | 0 tr | no | 0 tr |
| S1 | A | 0 tr | no | 0 tr |
| S1 | B | 0 tr | no | 0 tr |
| S2 | strict | 0 tr | no | 0 tr |
| S2 | A | 0 tr | no | 0 tr |
| S2 | B | 0 tr | no | 0 tr |
| S3 | strict | 0 tr | no | 0 tr |
| S3 | A | 0 tr | no | 0 tr |
| S3 | B | 0 tr | no | 0 tr |
| S4 | strict | 0 tr | no | 0 tr |
| S4 | A | 0 tr | no | 0 tr |
| S4 | B | 0 tr | no | 0 tr |

## AUDCHF

| strategy | gate | in-sample | chosen? | out-of-sample |
|---|---|---|---|---|
| S1 | strict | 0 tr | no | 0 tr |
| S1 | A | 0 tr | no | 0 tr |
| S1 | B | 0 tr | no | 0 tr |
| S2 | strict | 0 tr | no | 0 tr |
| S2 | A | 0 tr | no | 0 tr |
| S2 | B | 0 tr | no | 0 tr |
| S3 | strict | 0 tr | no | 0 tr |
| S3 | A | 0 tr | no | 0 tr |
| S3 | B | 0 tr | no | 0 tr |
| S4 | strict | 0 tr | no | 0 tr |
| S4 | A | 0 tr | no | 0 tr |
| S4 | B | 0 tr | no | 0 tr |

## What the choices did on the unseen part

| gate | strategies chosen (pair · strategy) | out-of-sample trades | win rate | result |
|---|---|---|---|---|
| strict | — | 0 | — | +0.0R ($+0) |
| A | — | 0 | — | +0.0R ($+0) |
| B | — | 0 | — | +0.0R ($+0) |

Every out-of-sample count here is tiny (about 30 days of M5). A positive number is a hint to keep testing, not proof.
