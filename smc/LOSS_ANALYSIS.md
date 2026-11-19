# Why the md's FXAlexG loses (2026-11-19)

VERIFIED on the same backtest as `PLAYBOOK.md`: 2 years of H1 from the app's feed, 29 pairs, triggers read on H1 and
followed on H1. 6,450 SoS + Engulfing triggers at an AOI; 5,173 followed to an end; 195 passed the md's gate
(36 % win, -45.2R, PF 0.66). Every trigger was followed the same way, passed or not, so the rules can be compared.
Nothing in the engine was changed.

## 1. The entry has no edge (the main cause)
From the entry, price reaches +1R before -1R (the trade's own stop distance, no costs) on **45 %** of all triggers and
**45 %** of the passed ones. A coin flip is 50 %. With 5,170 cases this is not luck: after the engulfing closes, price
more often goes back against the trade than on. +1.5R before -1R: 35 % (40 % is needed to break even at that target).
No filter on top can make money from an entry that is worse than random.

## 2. The score does not pick the better trades
- Expectancy by S_AlexG: 40-59 % +0.11R, 60-79 % -0.01R, **80-99 % -0.09R**, 100-119 % -0.05R. The 80 % gate keeps the worse group.
- Some items are true on almost every trigger, so they add points without telling anything: the round level (98 % of
  triggers: a 50-pip grid with ±8 pips almost always falls in a zone whose median width is 56 pips), D1 AOI (92 %),
  D1 elbow (90 %), H4 elbow (85 %). Several "with" groups do worse than "without" (H4 elbow, W1 candle, D1 / H4 pattern).
- Only W1 50 EMA (+0.07R) and the W1 pattern (+0.11R, 112 cases) help.

## 3. The stops are too tight for H1 noise, and costs eat them
- Passed trades by stop size: under 20 pips -0.32R, **20-40 pips -0.37R** (124 of 195 trades), 40-80 pips +0.13R, 80+ +0.15R.
- Passed losers got only 0.41R in their favour (median) before the stop; half were stopped within 24 H1 candles.
- Spread + slippage as a share of the risk: under 0.05R +0.09R per trade, 0.05-0.1R -0.31R, over 0.1R -0.45R.

## 4. Which setups lose
- S&F-DAY (D1 + H4, no W1): 55 trades, 25 % win, **-35.2R**. S&F-SWING: 140 trades, -10.0R. Full W1 + D1 + H4 sync: 54 trades, +0.4R (flat).
- Buys -37.6R (89 trades), sells -7.6R (106). Market entries -38.8R (126), limits -6.4R (69).

## Checked and NOT the cause
- The data: D1 candles at 23:00 / 00:00 UTC, no H1 gaps for forex; gold's futures day is shifted but gold took no trade.
- The H1 follow: no losing trade had its stop candle also reach the target, so the "stop first" rule changed nothing.
- Look-ahead: the test that cuts the history and compares (tests/test_alexg.py) passes.

## What could change it (each departs from the md; each must be tested on the first 60 % and confirmed on the last 40 %)
1. A better entry: the tests show the engulfing close itself is the weak point, e.g. enter on the retest of the SoS
   neckline (the md's limit idea) for every trade instead of at the close.
2. Wider stops: a floor (e.g. 1 x ATR14 of D1, or 40 pips) so the stop sits outside H1 noise and costs fall under 0.05R.
3. Drop S&F-DAY, or ask for the full W1 + D1 + H4 sync.
4. Make the score mean something: score only items that are not almost always true (the round level within the zone,
   not ±8 pips of a 50-pip grid; the elbows that are not the zone's own).

## The fixes, tested (smc/tools/fix_test.py, results in smc/fix_test.json)
81 combinations of the 4 fixes (entry: md / always the 50 % limit / a limit at the SoS neckline · stop floor: none /
0.5 / 0.8 ADR20 · sync: md / S&F-SWING only / full W1 + D1 + H4 · score gate: md 80 % / none / 50 % without the
near-always items), the same 2 years, 29 pairs. The rule was fixed before any result: choose on the first 60 %, keep
only if the last 40 % also has PF > 1.5 and win >= 50 %.

- **No combination passes.** Chosen on the first 60 % (limit entry, S&F-SWING only, strict score): PF 1.24 there,
  **PF 0.70 and -12.5R on the last 40 %.**
- Of 81 combinations, **none** made money on both halves; 3 had PF just above 1 on the last 40 % (1.01-1.05, 12-23
  trades), all three losing on the first 60 %. None reached PF 1.5 on the last 40 %.
- One fix at a time (whole period, the md: 195 trades, -45.2R, PF 0.66):
  S&F-SWING only -9.6R (PF 0.89) · full sync -0.6R (PF 0.98, 55 trades) · 50 % limit -31.2R · neckline limit -49.4R ·
  stop floor 0.5 ADR -48.8R · 0.8 ADR -27.2R · no score gate -43.6R · strict score -42.0R.
- The best whole period (limit entry, stop 0.8 ADR, S&F-SWING only): +6.4R on 65 trades, but +15.2R then -8.8R: the
  first part carries it, the last 40 % loses (25 % win).

**Conclusion:** on this data, the md's strategy has no edge that these fixes can bring back; removing the losing parts
(S&F-DAY, then everything but the full sync) only brings the loss toward zero. The switches stay in the code
(alexg.VARIANT) at the md's values; the live app is unchanged.
