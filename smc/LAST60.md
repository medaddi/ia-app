# The last 60 days with the app's exact rules

VERIFIED from the Yahoo candles (2026-09-07 → 2026-11-06). Money: 1 % risk per trade on $10,000 (1R = $100), costs included, not compounded. Research, not advice: a backtest this short proves nothing either way.

| Pair | setups found | taken (rules + 7 questions) | wins | result | $ at 1 % of $10k | managed result | every setup (checklist ignored) |
|---|---|---|---|---|---|---|---|
| XAU/USD | 37 | 3 | 1 | +0.62R | $+62 | +0.51R | 21 tr, +2.75R ($+275) |
| EUR/USD | 28 | 0 | 0 | +0.0R | $+0.0 | +0.0R | 19 tr, -2.94R ($-294) |
| GBP/USD | 38 | 0 | 0 | +0.0R | $+0.0 | +0.0R | 30 tr, -8.27R ($-827) |
| EUR/CHF | 3 | 0 | 0 | +0.0R | $+0.0 | +0.0R | 3 tr, -1.97R ($-197) |
| AUD/CAD | 1 | 0 | 0 | +0.0R | $+0.0 | +0.0R | 1 tr, -1.11R ($-111) |
| AUD/CHF | 2 | 0 | 0 | +0.0R | $+0.0 | +0.0R | 2 tr, +1.91R ($+191) |

**Total taken by the teams: 3 trades, +0.62R ($+62).**
**After the trader-skill risk check across the teams: 3 trades sent, 1 wins (win rate 33 %), +0.62R ($+62); 0 blocked.**

## Why setups were not taken (all pairs; one setup can fail several questions)

- 7: 68
- 1: 57
- 6: 52
- 3: 10

## The trades taken

- XAU/USD 09-11 07:35 UTC · S3 SELL · RR 1:4.74 · LOSS -1.03R (managed -1.03R)
- XAU/USD 10-07 07:35 UTC · S3 BUY · RR 1:7.71 · LOSS -1.06R (managed -1.06R)
- XAU/USD 10-05 10:00 UTC · S4 SELL · RR 1:4.9 · TIME +2.71R (managed +2.6R)

Engine v0.3 (see `CHANGELOG.md`): S1 as the brief writes it, S2 / S3 sweeps close back inside, question 1 on H4, duplicates
removed, trailing in the managed result. The owner's decision stands: the rules stay strict (all 7 questions).
