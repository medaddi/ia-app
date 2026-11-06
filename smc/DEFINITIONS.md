# Definitions (v0.1)

**Source note.** The brief names a 10-episode Darija SMC masterclass script as the authority. **That script was not
provided to the team.** Every definition below comes from the brief's own summary of the script (marked **SCRIPT
(brief)**), or is a choice the team made where the brief is silent or vague (marked **Team interpretation**). When the
script is provided, each line must be checked against it; any difference goes through `CHANGELOG.md`.

Labels: **SCRIPT (brief)** = stated in the brief · **Team interpretation** = our operational choice · **HYPOTHESIS** = untested.
Code: `smc/engine/smc.py` (S1–S4, the checklist) and `smc/engine/manage.py` (management).

All times are UTC. A candle's time is its OPEN; it is "known" only at its close. Nothing below uses a later candle.

| Term | Operational definition (what the code does) | Source |
|---|---|---|
| Body close | The candle's close price. Only a close beyond a level breaks it. | SCRIPT (brief) |
| Wick sweep / liquidity sweep | High above a level (or low below) **and** close back on the other side. Not a BOS. After a sweep the level moves to the wick tip: only a close beyond the tip breaks structure. | SCRIPT (brief); the level moving to the tip is Team interpretation |
| Mother candle | In an up leg, the candle with the highest high so far (mirror: lowest low in a down leg). | SCRIPT (brief) |
| Inside bar | A candle whose high and low are both inside the mother candle's range. It never confirms a swing. | SCRIPT (brief) |
| Valid pullback | A later candle trades below the mother candle's LOW (up leg; mirror for a down leg), by wick or body. | SCRIPT (brief); "wick or body" is Team interpretation |
| Confirmed swing high / low | The mother candle's high (low), confirmed at the close of the candle that made the valid pullback. | SCRIPT (brief) |
| BOS | Body close beyond the last confirmed swing **in the direction of the current trend**. | SCRIPT (brief) |
| CHoCH | Body close beyond the last confirmed swing **against** the current trend (the trend flips). | SCRIPT (brief) |
| Internal vs external structure | **Team interpretation:** H1 structure = external (bias, dealing range, targets); M5 structure = internal (entry confirmation). The engine does not split internal / external swings on one timeframe. | Team interpretation |
| Fake CHoCH | **Not classified by the engine.** The brief says the script uses CHoCH for two ideas. Our rule: an M5 CHoCH counts only when it happens inside an HTF POI or right after a sweep (that is how S1–S4 use it); any other M5 CHoCH is ignored. | Team interpretation, flagged |
| IDM (inducement) | After an H1 break, the first internal swing (a swing low for a bullish leg) confirmed after the break and above the OB. It must be swept (wick through it) before price returns to the OB. Searched up to 60 H1 candles after the break. | SCRIPT (brief); the 60-candle window is Team interpretation |
| Displacement | A structure break (BOS / CHoCH) that leaves an FVG in the same direction. S4 additionally asks a body of at least 50 % of the candle's range. No ATR multiple is used. | Team interpretation, flagged |
| FVG | 3 candles: candle 1's high below candle 3's low with candle 2 bullish (bullish FVG); mirror for bearish. | SCRIPT (brief) |
| CE | 50 % of the FVG. **Not used by the entries** (entries use the FVG's near edge). | SCRIPT (brief); not used, flagged |
| IFVG | An FVG closed through by a body becomes an inverted FVG. **Not implemented.** | SCRIPT (brief); open item |
| Dealing range | From the last confirmed H1 swing low to the last confirmed H1 swing high. | SCRIPT (brief) |
| Premium / discount / equilibrium | Above / below / at 50 % of the dealing range. Buys only in discount, sells only in premium. | SCRIPT (brief) |
| OTE | 61.8–78.6 % of the dealing range. **Not used as a gate** (only the 50 % line is). | SCRIPT (brief); not used, flagged |
| Order Block (OB) | The last opposite candle (bearish for a bullish impulse) within 6 candles before the impulse's origin, that broke structure (BOS / CHoCH) on H1. | SCRIPT (brief); the 6-candle window is Team interpretation |
| OB four-point validity | (1) an FVG between the OB and the break, (2) the impulse broke structure, (3) unmitigated (the first return is the tap; a body close through it invalidates it), (4) an IDM in front of it, swept before the tap. | SCRIPT (brief) |
| Extreme vs Decisional OB | **Not separated.** The engine takes the last opposite candle nearest the impulse origin, which is the extreme one. A decisional OB variant is an open experiment. | Team interpretation, flagged |
| Breaker block / flip zone (S2D, D2S) | **Not in S1–S4 as tested.** (The earlier app engine had a flip strategy; it was dropped because the brief's four strategies do not include it.) | Open item |
| OB tap tolerance | Price within 10 % of the zone height of the OB counts as a tap. | Team interpretation |
| Entry zone | The limit sits at the ideal level moved toward price by max(cost, 10 % of the stop distance), so a near miss fills. | Team interpretation |
| Order life | A limit is valid 12 M5 candles (1 hour); a filled trade is closed at market after 48 M5 candles (4 hours). | Team interpretation |
| Asian range | High and low of the M5 candles 00:00–06:00 UTC (at least 80 % of them present). | SCRIPT (brief) |
| London / NY killzone | 07:00–10:00 / 12:00–15:00 UTC, **not shifted for DST.** | SCRIPT (brief); DST unverified |
| PDH / PDL | High / low of the previous UTC calendar day, from M5 candles. | SCRIPT (brief); the UTC day boundary is Team interpretation (a broker's day may start at 17:00 New York) |
| EQH / EQL | **Not used by S1–S4 as tested.** | Open item |
| PWH / PWL, trendline liquidity | **Not used.** | Open item |
| News window | No entry 15 min before or after a high-impact release, when a calendar CSV is loaded (`smc/news/high_impact.csv`). **No calendar was available for the test period.** | SCRIPT (brief); not tested |
| Cost | Spread + slippage (pips, per pair config), paid once per trade; the stop also sits one cost beyond the swing. | Team interpretation |
| Minimum stop | A setup whose stop is smaller than 5 × the cost is skipped (low-volatility pairs). | HYPOTHESIS (set before the test) |
| Risk | 1 % of equity per trade. Lots = (equity × 1 %) / (stop in pips × pip value per lot). | SCRIPT (brief) |
| Break-even | Stop to entry only after an M5 BOS (body close) in favour after the fill. Tested in the "managed" results only. | SCRIPT (brief) |
| Partials | 50 % at 1:3 (the brief says 25–50 %). Tested in the "managed" results only. | SCRIPT (brief); 50 % is Team interpretation |
| Trailing | **Not implemented** (the managed result keeps the rest to TP). | Open item |
| Master checklist | 7 yes / no questions, all must pass. See `RULEBOOK.md`. | SCRIPT (brief, Episode 10); exact wording unverified |
