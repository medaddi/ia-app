# FX Alex G Set & Forget v2 — the blueprint's gates, measured (2026-11-20)

VERIFIED on the app's feed (Yahoo Finance forex; gold COMEX GC=F adjusted to spot), 29 pairs, spread + slippage, the stored
news calendar (-45 / +30 min), one trade per pair, Set & Forget (SL and TP never move). Two runs:
**60 days** = about the last 70 days of M5 (the SoS on M15 / M30 / H1, the engulfing on M30 / H1 / H2 / H4, trades followed on
M5) — the closest to the live app; **2 years** = H1 only (no M15 / M30 / M5 exists for that long on the feed, so no E2 and an
H1 SoS only, trades followed on H1). The blueprint's 24-month M5/M15 test is therefore NOT possible on this data.

## Gate 3 — the blueprint's KPIs

| KPI | Required (29 pairs) | 60 days (M5) | 2 years (H1 only) |
|---|---|---|---|
| Signals in the last 60 days | >= 5 (was 0) | **59 — met** | — |
| Signals over 24 months | 80 - 300 | — | 30 — not met (H1 only) |
| Win rate (A+, A, B+) | >= 55 % | 36 % — **not met** | 23 % — not met |
| Win rate A+ and A | >= 60 % | 36 % (58 trades) — not met | 23 % — not met |
| Average R of the winners | >= 2.10R | 2.45R — met | 2.93R — met |
| Expectancy | >= +0.55R | **+0.19R** — not met | -0.11R — not met |
| Profit factor | >= 2.00 | **1.28** — not met | 0.86 — not met |
| Max drawdown | <= 12.0R | 14.1R — not met | 9.3R — met |
| Out of sample (last 6 months) | E >= +0.35R, WR >= 52 % | not testable (60 days) | last 25 %: 11 trades, 27 %, +0.04R |

**Gates 1 and 4 (tests, types, speed): green** (153 backend tests, `tsc` clean, a 29-pair read in 12 s cold / 2 s cached).
**Gate 3 (quality): red.** Per the blueprint nothing is deployed and Phases 5-6 (cache, shards, chart builder) are not started.

## What the 60 days show (59 trades, +11.4R)

| split | trades | win | result | PF |
|---|---|---|---|---|
| model E1 (SoS, pullback, engulfing) | 38 | 45 % | +17.9R | 1.81 |
| model E2 (the engulfing is the SoS) | 19 | 16 % | **-9.1R** | 0.46 |
| model E3 (huge engulfing, 50 % limit) | 2 | 50 % | +2.6R | 3.33 |
| M1 full sync | 18 | 33 % | +3.8R | 1.30 |
| M2 HTF retracement | 28 | 32 % | +1.0R | 1.05 |
| M3 daily counter-weekly | 13 | 46 % | +6.6R | 1.89 |
| grade A+ | 31 | 39 % | +10.8R | 1.54 |
| grade A | 27 | 33 % | +1.6R | 1.09 |
| first 75 % of the period | 43 | 40 % | +12.8R | 1.47 |
| last 25 % of the period | 16 | 25 % | -1.4R | 0.89 |

Vetoes on the 278 candidates: WEEKLY_TRAP 143, PAIR_LOCKED 36, SESSION_BLACKOUT 24, SCORE_TOO_LOW 17, NEWS_BLACKOUT 10,
EXTENDED_ENTRY 4, SL_TOO_WIDE 3, DATA_OR_SPREAD_UNSAFE 1.

## Diagnosis and the one structural correction tried

E2 is the loss maker (19 trades, 16 % win). The blueprint says E2 is "an engulfing printed FROM the AOI": the engulfing candle or
one of the 3 before it must touch the AOI. That condition was added; the result did not change (the same 19 trades already
came from the AOI). No threshold was tuned on these 59 trades (that would be curve-fitting on a tiny sample).

## Reading

The v2 rules fix the frequency (59 trades in 60 days against 0 before) and the structure is sound (E1, M3 and A+ trades have
a positive expectancy), but the quality targets (win >= 55 %, PF >= 2.0, E >= +0.55R) are NOT reached, and the last quarter
of the period loses. 59 trades over 70 days in a single market regime is a small sample; it neither proves nor disproves the edge.
Honest options: (1) run it live as signals only and let the history / win rate measure it, (2) drop E2 (the 16 % model) and
re-test, (3) keep calibrating on structural filters with more data (Dukascopy M5 for 24 months would allow the blueprint's real test).

## Re-audit against the blueprint (2026-11-20)

The blueprint file was re-read line by line against the code. Three gaps were fixed:

- **S13**: a data hole now vetoes only above 3 missing H1 bars (it vetoed any hole).
- **E3**: the limit goes to the SoS neckline instead of the 50 % of the body when the neckline lies inside the engulfing's body and gives the higher R:R ("ou au niveau de la neckline SoS si meilleur").
- `manager.py` said limits expire after 6 h; the code and the blueprint use 8 h (text only).

E2 stays disabled (16 % win in the 60-day test). After the fixes: 60 days 51 trades, win 37 %, +10.8R, PF 1.32; 2 years (H1) 29 trades, win 24 %, -2.2R, PF 0.90. The quality gates are still not met. 155 tests pass.
