# Rule book (v0.1): BUY and SELL

Shared by the six pair teams; only the config differs (`pairs/<PAIR>/config.json`: pip size, cost, sessions, minimum
Asian range). Every rule is a yes / no test, coded in `engine/smc.py`. The SELL rule is the exact mirror of the BUY rule
(highs ↔ lows, premium ↔ discount, above ↔ below) unless a line says otherwise.

**Status of every number below: SCRIPT (brief) or Team interpretation (see `DEFINITIONS.md`). No rule has a verified
edge: see each pair's `TEAM_REPORT.md`.** The source script itself was not provided.

Timeframes: HTF = H1 (bias, dealing range, OB, targets) · LTF = M5 (entry). LTF is read only once the HTF condition is
met. 4H / D1 are context only (not coded).

## The 7-question master checklist (every trade, every strategy: one "no" = no trade)

| # | Question (BUY) | Yes when |
|---|---|---|
| 1 | Is the H1 bias bullish by a body-close break? | the last H1 BOS / CHoCH was up (H1 trend = +1 at entry time) |
| 2 | Was IDM or external liquidity swept? | the setup's steps include a sweep (IDM, Asian / previous-day level, H1 swing) |
| 3 | Is the entry in discount? | entry < 50 % of the H1 dealing range |
| 4 | Is there a fresh FVG / OB at the entry? | by construction: every strategy places its limit at an untouched FVG / OB |
| 5 | Was there an LTF change of character with displacement? | by construction: M5 CHoCH with FVG (S4: one H1 candle sweeping and closing back) |
| 6 | Is it London / NY hours, not Friday late or Monday open, with no high-impact news within 15 min? | 07:00–16:00 UTC, not Friday ≥ 15:00, not Monday < 07:00, no listed release within ±15 min (news only when a calendar is loaded) |
| 7 | Is the reward at least 1:3? | (TP − entry) / (entry − SL) ≥ 3 |

Devil's advocate notes: questions 4 and 5 are always "yes" because the strategies only produce setups that have them;
they add no filtering. Question 1 rejects every S2 / S3 reversal taken against the H1 trend.

## S1 · HTF trend continuation (BUY)
1. H1 body close breaks a confirmed swing high (BOS or CHoCH up).
2. The H1 OB of that impulse is valid (FVG after it, unmitigated, IDM in front).
3. The IDM (first H1 swing low confirmed after the break, above the OB) is swept by a wick.
4. Price then taps the OB (within 10 % of its height), and the OB top is below 50 % of the impulse (discount).
5. Within 24 M5 candles of the tap: an M5 wick sweep of a low inside the OB.
6. Within 24 M5 candles of that sweep: an M5 body-close break up (CHoCH) with a bullish M5 FVG.
7. **Entry:** buy limit at the FVG's top edge (minus the entry tolerance). **SL:** the lowest M5 low since the tap, minus one cost.
   **TP:** the H1 external high of the impulse. Candidate only if RR ≥ 2; traded only if the checklist passes (RR ≥ 3).
- **Invalidation:** an M5 body close below the OB before the entry; the impulse high taken before the IDM sweep; the limit not filled within 1 hour.

## S2 · PDH / PDL sweep reversal (BUY = after a PDL sweep)
1. Mark the previous UTC day's high, low and 50 % (EQ).
2. Between 06:00 and 20:00 UTC, an M5 candle wicks below PDL (first time today).
3. Within 12 M5 candles: an M5 body-close break up with a bullish FVG (a close below the sweep low first cancels it).
4. The entry is below the previous day's EQ (discount).
5. **Entry:** buy limit at the FVG top. **SL:** below the sweep low minus one cost. **TP:** the previous day's EQ (50 %). Candidate if RR ≥ 1.5.
- **Invalidation:** the sweep low closed through; no M5 break with FVG within 1 hour; the limit not filled within 1 hour.
- Differs from the brief: no IFVG entry, no EQH / EQL levels, TP is the 50 % only (not the opposing liquidity).

## S3 · Asian range sweep + killzone (BUY = after an Asian-low sweep)
1. Asian range = M5 high / low 00:00–06:00 UTC (pairs with `s3_min_asia_range_atr` > 0: the range must be at least that many H1 ATR(14)).
2. In London (07–10 UTC) or NY (12–15 UTC), an M5 candle wicks below the Asian low (first time today).
3. The sweep low is in discount of the H1 dealing range (the HTF POI).
4. Within 12 M5 candles: an M5 body-close break up with a bullish FVG.
5. **Entry:** buy limit at the FVG top. **SL:** the lowest low since the sweep minus one cost. **TP1:** the Asian high. Candidate if RR ≥ 1.5.
- Differs from the brief: no TP2 at PDH / PDL; "against the HTF bias" is read as "the sweep goes into discount / premium", and question 1 then asks the trade to be WITH the H1 trend.

## S4 · Single-candle OB & wick mitigation (BUY)
1. One H1 candle wicks below the last confirmed H1 swing low and closes above it, bullish, in the upper half of its range, with a body ≥ 50 % of its range.
2. An M5 bullish FVG inside that H1 candle overlaps its 50 % level (± 10 % of the candle's range).
3. **Entry:** buy limit at the candle's 50 %. **SL:** below the H1 candle's low minus one cost. **TP:** the last confirmed H1 swing high. Candidate if RR ≥ 1.5.
- Differs from the brief: 4H single candles not tested; no trailing.

## Risk and management (all strategies)
- Risk 1 % of equity, defined before entry. Lots = (equity × 0.01) / (SL distance in pips × pip value per lot), rounded down to 0.01.
- A setup whose stop is smaller than 5 × the cost is skipped.
- Plain (main result): full size to TP or SL; the stop first if both sit in one candle; closed at market after 4 h.
- Managed (second result): 50 % at 1:3; stop to break-even only after an M5 BOS in favour; the rest to TP.
- Not coded: trailing under confirmed HL / LH, a drawdown stop, news spread widening.
