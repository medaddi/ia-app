# Trade journal template (demo only)

One row per trade, in `journal.csv` next to the pair's report (the header is in `journal_template.csv`). Times in UTC.
Write the row before the result is known (setup, entry, SL, TP, lots, risk), then the result.

| Field | What to write |
|---|---|
| date_time_utc | entry time, `YYYY-MM-DD HH:MM` UTC |
| pair | e.g. EUR/USD |
| strategy | S1 / S2 / S3 / S4 |
| htf_bias | BULLISH / BEARISH + the H1 break that set it (time, level) |
| idm_hit | Y / N + level |
| zone | OB / FVG used: type, timeframe, top, bottom |
| ltf_confirmation | M5 sweep (time, level), M5 CHoCH (time, level), FVG (top, bottom) |
| checklist | the 7 answers, e.g. `Y Y Y Y Y Y Y` |
| entry, sl, tp | prices |
| lots, risk_pct, risk_usd | lots from the formula, 1 % unless the owner set another value in writing |
| outcome_r | result in R after costs |
| chart_ref | screenshot file name, or chart coordinates (time + price of the key candles) |
| rule_violations | every rule not followed, or "none" |
| emotional_note | one line: state before / during / after |

## The first two weeks of demo
1. Only setups the engine marks `checklist_7_pass = True` (`trades.csv`, or the pair's live check when it exists).
2. 1 % risk, one trade per pair at a time, no manual changes to SL / TP except the managed rules (BE after BOS, 50 % at 1:3).
3. Every trade journaled the same day, even a skipped one (write why it was skipped).
4. No new rule during the two weeks; ideas go to the weekly review as "to test next".
5. After two weeks: compare the journal with what the engine says it would have done on the same days.
