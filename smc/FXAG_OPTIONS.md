# FX Alex G (2026-11-20 spec): why so few trades, and what loosening a rule does

VERIFIED on the app's feed (Yahoo Finance; gold COMEX GC=F): 2 years of H1 (2024-11-19 → 2026-11-19, the SoS read on
H1 only, trades followed on H1) and the last 60 days with M5 (the SoS on M15 / M30 / H1, trades followed on M5), 29 pairs,
spread + slippage, news (stored calendar), one trade per pair. Each option alone, the md's rules everywhere else.
Research only: the live engine runs the md as written.

| option | 2 years | first 60 % | last 40 % | last 60 days |
|---|---|---|---|---|
| the md as written | 1 trade · -1.0R | 0 | 1 · -1.0R | 0 |
| zone proximity 15 pips (md: 5) | 1 · -1.0R | 0 | 1 · -1.0R | 0 |
| broken-zone check on the last 10 D / 4 W candles (my CHOICE was 60 / 20) | 1 · -1.0R | 0 | 1 · -1.0R | 0 |
| score >= 70 % (md: 80 %) | 4 · all lost · -4.1R | 2 · -2.1R | 2 · -2.0R | 0 |
| SoS valid 24 h (md: 12 h) | 1 · -1.0R | 0 | 1 · -1.0R | 0 |
| D + 4H enough when W is not aligned | 1 · -1.0R | 0 | 1 · -1.0R | 0 |
| all five together | 6 · all lost · -6.2R | 2 · -2.1R | 4 · -4.1R | 0 |

Where it stops (6 pairs, 2 years, 15,989 engulfing closes): 10,408 not aligned, 3,256 no AOI visited, 1,413 at a
broken AOI, 618 under the score, 278 at Tier 1 without a SoS, 12 under R:R 2.0, 2 approved. At Tier 1 without a SoS:
in 201 cases the H1 had not yet closed a body beyond its last LH / HL, in 75 it had done so more than 12 hours before.

Reading: the rare trades come from the md's two-step entry (a body-close SoS, then an engulfing, both at the zone),
not from any single gate; loosening the gates one by one or together adds a handful of trades, and on this data those
trades lost.
