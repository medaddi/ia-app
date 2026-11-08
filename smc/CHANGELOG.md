# Changelog

## v0.1 · 2026-11-05
- First version of the shared engine (`engine/smc.py`), taken from the app's SMC engine (git c262bdc), reduced to the
  brief's four strategies (S1 = A, S2 = B, S3 = D, S4 = E; the supply / demand flip strategy C dropped) and made
  configurable (sessions, news window, minimum Asian range, minimum stop / cost).
- Added the managed simulation (50 % at 1:3, BE after an M5 BOS) and the random-direction baseline.
- Data: Yahoo Finance, fetched 2026-11-05 (`tools/fetch_data.py`), checked by `tools/data_quality.py`.
- Parameter changes after seeing results: **none.** Tuning passes: 0.

## v0.1 decision · 2026-11-06
- Conflict found by the 60-day test (`LAST60.md`): question 1 (trade with the H1 trend) rejects the reversal strategies
  S2 and S4 almost always (122 of 136 setups failed it); over 60 days the gate took 1 trade (−1.19R).
- **The account owner chose to keep the rules strict:** all 7 questions stay as they are for every strategy. No rule
  changed. Options A (no question 1 for S2 / S4) and B (A + reward ≥ 1:2) are recorded in `LAST60.md` as untested
  exploration, to retest on fresh data only if the owner asks.
- Tuning passes: still 0.

## v0.2 · 2026-11-06 · the engine made to follow the brief (bugs found by the 60-day test, not tuning for results)
- **S1 had an extra step the brief does not have** (an M5 wick sweep inside the OB) and **lacked one it has** (the LTF
  IDM). Now, as the brief writes it: OB tapped in discount / premium → M5 CHoCH + FVG within 2 h → M5 IDM (first pullback
  swing after the CHoCH, in front of the entry) → limit at the FVG. Before: 0–1 S1 setups per pair in 60 days.
- **S2 / S3 took breakouts as sweeps.** The brief: "a wick sweep of a level that closes back inside". Now a sweep
  counts only if price closes back inside the level within 3 M5 candles (Team interpretation of "closes back inside").
- **Question 1 read the internal H1 structure**, so the pullback S1 waits for (the IDM taken by a body close) flipped
  the "trend" and blocked S1's own trades (8 of 9). The brief: "HTF bias (4H or 1H)". Question 1 now reads H4 structure
  built from H1 (Team interpretation: H4 = the external structure). The owner's strict choice stands: a reversal
  against the H4 trend still fails question 1.
- **Duplicate setups** (two zones leading to the same entry) are now one setup.
- Effect on the last 60 days (`LAST60.md`, VERIFIED): taken trades 1 → 3, result −1.19R → +0.62R (1 win of 3, gold
  only). Still statistically meaningless. Tuning passes on parameters: still 0 (no number was changed, only the steps).

## v0.3 · 2026-11-06 · the teams manage their trades like a trader
- **News (question 6) now checked live** with the app's ForexFactory calendar (this pair's currencies, high impact,
  15 minutes either side). The backtest still has no news history: there, question 6 checks the hours only.
- **Trailing added** (brief: "trailing under confirmed higher lows / lower highs"): once at break-even, the stop follows
  each newly confirmed M5 swing, one cost beyond it, only in favour. Same code in the backtest and live (`backend/app/smc/manage.py`).
- **Live trade manager** (`backend/app/smc/manager.py`): every sent setup is followed each minute — filled, 1:3 (close
  50 %), stop to break-even after an M5 BOS, trailing, closed (TP / stop / break-even / trailing stop / 4-hour exit),
  or expired / missed — and each step is sent once to Telegram and push. The outcome and R are saved: the dashboard's
  win rate is the teams' REAL result from the trades they sent.
- 60 days, all 62 setups (checklist ignored, for a bigger sample): plain −2.96R · 50 % at 1:3 + BE +3.58R · + trailing
  +0.59R. Management turns many losses into break-evens (win rate 39 % → 29–32 %, result up). Trailing as coded stops
  out early on this sample (HYPOTHESIS: it may need a wider buffer; not tuned, 62 trades is too few to decide).
- Tuning passes: still 0.

## v0.4 · 2026-11-06 · one year of Dukascopy candles, the win-rate search
- Data: one year (2025-11-05 → 2026-11-05) of Dukascopy BID M1 for the six pairs, built into M5 / H1
  (`tools/fetch_dukascopy.py`, into `pairs/<PAIR>/data/dukascopy/`, not in git). Every pair's M5 passes the data check
  (flat ≤ 0.2 %, jumps ≤ 1.2 %); Yahoo's EUR/USD M5 had 15 % flat candles and 32 % jumps. Gold here is spot.
- `tools/search.py`: per pair, S1–S4 × 4 gates × 2 exits; chosen on the first 60 % (≥ 8 trades, win ≥ 45 %,
  expectancy > 0), confirmed on the last 40 % (≥ 4 trades, expectancy > 0, win ≥ 40 %). Rule written before the run.
- Result (`SEARCH_dukascopy.md`): **nothing confirmed on any pair.** One choice made (EUR/USD S3, rules only: 13 trades,
  win 46 %, +6.55R in-sample) lost all 4 out-of-sample trades. Gold S2 is positive in both halves but under 45 % win.
- Across the six pairs: S4 on its own rules loses on 6/6 pairs (232 trades, −66.6R); with the 7 questions it is
  +4.9R on 10 trades. The checklist removes the losing S4 trades; the strict team takes about 25 trades a year in all.
- Entry shown as a zone (the limit at its near edge, as the engine already filled it); the agents speak as decisions.
- Parameter changes after seeing results: **none.** No strategy switched on or off (nothing passed the rule).

## v0.5 · 2026-11-07 · each team trades its pair's playbook strategy
- The user's playbook ("الدليل الاحترافي الدقيق: تشريح الأزواج الـ 6") replaces S1–S4 in the live teams: one strategy per
  pair, coded rule by rule in `backend/app/smc/playbook.py` (gold Asian range sweep + MSS + FVG, EUR/USD OB + EMA 200,
  GBP/USD Judas swing + SMT, EUR/CHF Bollinger + RSI + ADX, AUD/CAD S&D + class-A divergence, AUD/CHF EMA + Fib + S/R flip).
  Its 5-question checklist replaces the 7 questions (RR ≥ 1:2, EUR/CHF 1:1.5; news 30 min; one open trade per currency).
- CHOICE (written in the code): gold's dollar numbers (Asian range < $15, sweep 20–60 pips, stop $1.5) are for gold near
  $2,650; at $4,000+ no Asian range was under $15 in a year, so they are the same shares of the ADR.
- Measured on one year of Dukascopy candles (`tools/playbook_test.py`, `PLAYBOOK.md`), costs in: 56 trades, win 30 %,
  −15.05R. Claimed 70–82 % win: **not confirmed** on any pair (EUR/CHF 64 % on 11 trades, −0.06R; gold 0 trades).
- The card and the agents show the claimed and the measured win rate side by side. Parameter changes after seeing
  results: one, the gold scaling, made after the literal rule gave 0 setups in the year (no Asian range under $15); no other change.

## v0.6 · 2026-11-07 · the second guide replaces every earlier strategy
- The user's guide "Istratijiyat Tadawoul L-Azwaj O D-Dhab" (section 6a, the master execution table) is now the only
  source of the teams' strategies; S1–S4 and the first playbook are not traded any more (`backend/app/smc/playbook.py`):
  gold ICT Silver Bullet / NY killzone (P) · EUR/USD London Judas swing (P1) + SnapBack 3σ (P2) · GBP/USD London / NY
  overlap sweep (P1) + EMA 20/50/200 pullback (P2) · EUR/CHF and AUD/CAD time-filtered 3σ mean reversion · AUD/CHF
  risk-on carry swing (longs; its macro gate S&P 500 / VIX / iron ore is not checked: no such data in the app).
- The guide's risk rules are the checklist: red-folder news ±15 min, each strategy's reward, 1 %, the correlation cap
  (EUR/USD + GBP/USD, AUD/CAD + AUD/CHF, EUR/CHF + AUD/CHF; replaces "one trade per currency"), the ADR regime.
- Each chart shows only its pair's strategy: levels, time windows, Bollinger 3σ / EMA lines, the setup's zones.
- Measured on one year of Dukascopy candles (`PLAYBOOK.md`), costs in. Holds up: **EUR/USD SnapBack 3σ, 27 trades, win
  70 %, +9.68R, 71 % / 69 % in the two halves** (the guide: 62 %). Not confirmed: gold 31 % on 13 (−4.7R), GBP/USD sweep
  50 % on 78 (−2.1R), AUD/CHF 43 % on 61 (−12.8R); too few to judge: EUR/USD Judas 2, EUR/CHF 3, AUD/CAD 3, GBP/USD EMA 0.
- Every rule the guide leaves open is marked CHOICE in the code. Parameter changes after seeing results: **none.**

## v0.6.1 · 2026-11-07 · review + the news filter in the test
- Review of the six strategies against the guide, with trades checked by hand on the candles (SnapBack, Silver Bullet):
  the rules, the costs and the R are right; no look-ahead (the test cuts the data and finds the same earlier setups).
- Fixed: a pending limit could fill inside a news release (only the signal time was checked). Now the limit is pulled
  from 15 min before a red-folder release to 15 min after, in the test, in the team, and in the live trade manager.
- News history: `smc/news/high_impact.csv`, 13 months (Nov 2025 → Nov 2026) of ForexFactory high-impact events for USD,
  EUR, GBP, CHF, AUD, CAD (from its month pages, times in UTC, checked against FOMC / ECB official dates). Each pair
  counts its own currencies (gold: USD).
- Test with the news rule (`PLAYBOOK.md`): EUR/USD SnapBack 3σ **22 trades, win 68 %, +6.94R, 70 % / 67 % in the two
  halves** (27 trades, +9.68R without the rule: the 5 removed were at a release). Gold 13 trades 31 % −4.7R, GBP/USD
  sweep 74 trades 50 % −2.1R, AUD/CHF 61 trades 43 % −12.8R, the others too few. All: 178 trades, 48 %, −11.34R.
- Parameter changes after seeing results: **none.**

## v0.7 · 2026-11-07 · the guide's algorithm summary applied
- News: the guide's red-folder pause for EVERY pair: US CPI, NFP, FOMC, BoE, RBA, BoC, SNB (`playbook.red_folder`) +
  the EIA crude oil inventories every Wednesday 10:30 New York (`eia_times`); live, in the test and in the manager.
- Correlation: EUR/USD + GBP/USD the same way → 0.5 % each (the alert halves the lot and says to cut the other);
  AUD/CAD + AUD/CHF the same way → blocked. EUR/CHF + AUD/CHF is no longer capped (not in the summary).
- ADR rescaling: ADR5 / ADR20 < 0.70 cuts the sweep / trend targets to that share (it blocked them before);
  > 1.40 still stops the mean reversion.
- EUR/CHF: daily pivots (P, S1, S2, R1, R2) as levels next to the 3-touch levels; EUR/CHF and AUD/CAD: the RSI
  divergence trigger at the level next to the BB 3σ close.
- AUD/CHF: the 3-pillar macro gate (S&P 500 up, VIX calm, iron ore up, from Yahoo daily closes: `tools/fetch_macro.py`,
  live cached 6 h) and the risk-off exit (VIX +10 % or S&P −1.5 % on a day: the long is closed at 22:00 UTC).
- CHF pip value: 10 CHF in dollars at the live USD/CHF (12.19 today), not a fixed 12.5.
- Fixed in the test: two trades could be open on one pair at once; now one per pair at a time (the app's rule).
- Result (`PLAYBOOK.md`, one year, costs in): all strategies 142 trades, win 53 %, **+6.40R**. EUR/USD SnapBack 27 tr,
  70 %, +9.68R; AUD/CAD 17 tr, 59 %, +5.94R (both positive in both halves); EUR/CHF 10 tr, 50 %, +1.77R; GBP/USD sweep
  70 tr, 53 %, −0.58R; gold 10 tr, 30 %, −3.16R; AUD/CHF 7 tr, 14 %, −6.13R.
- Parameter changes after seeing results: **none** (every new rule is the summary's; choices marked CHOICE).

## v0.8 · 2026-11-08 · the master spec's pair engines (quantitative_trading_teams_claude_master_prompt.md)
- The user's rule: strategies with a high win rate stay, the others are replaced (CHOICE, written: kept = win >= 55 % and
  profitable in both halves). Kept: EUR/USD SnapBack 3σ (SB) and AUD/CAD range reversion (P). Replaced by the spec's
  engines (`backend/app/smc/engines.py`): XAU/USD GOLD-QUANT S1–S4, EUR/USD INST-AMD S1–S4 (next to SB), GBP/USD
  CABLE-RAID S1–S4, EUR/CHF SWISS-REV S1–S3, AUD/CHF RISK-REGIME S1–S4 (ADX + Kaufman ER regime switch).
- The spec's indicators: daily VWAP ± σ (volume-weighted; a TWAP on a feed without volume), Z-score on EMA 50, Kaufman
  ER 30, the dealing-range %, displacement (1.5 ATR, body 65 %), the true FVG (consecutive candles, opens within
  0.35 ATR), the true sweep (not in 21:50-22:15 UTC rollover, not a 3-ATR spike), the live feed check (missing bars,
  abnormal opens: FEED_GAP_IGNORED), the data fitness tiers FIT / LIMITED SAMPLE / NOT FIT (N >= 30 / 15-29 / < 15).
- Agents per pair: the header badge (e.g. "H1 range · Z -1.8σ · discount 18 %"), the AMD phase, the regime, the Z-score
  waits, REGIME BREAK VETO, Backtest Engineer N / win / EV / fitness per strategy, Devil's Advocate on the live feed
  (the old "M5 NOT FIT: artefacts of the feed" verdict replaced by the measured gaps). Gold risks 0.75 %.
- Charts per pair: VWAP ± σ, Z ±2.2σ bands, the dealing range + EQ, the killzones / AMD windows, OB / breaker / OTE boxes.
- One year (`PLAYBOOK.md`): 175 trades, win 43 %, −2.60R. Positive in both halves: SB 27 tr 70 % +9.68R, AUD/CAD 17 tr
  59 % +5.94R, EUR/CHF S2 11 tr 64 % +6.31R, GBP/USD S2 16 tr 50 % +7.91R, gold S1 5 tr 60 % +1.98R. Losing: GBP S1
  (20 %, −6.8R), S4 (−6.7R), EUR/CHF S1 (0 %, −7.8R), S3, EUR/USD S3 (0 %, −5.7R), S4, gold S2, S3. No trade: EUR/USD
  S1/S2 (RR never 1:2), AUD/CHF S1–S4 (the M15 CHoCH / OTE conditions).
- Parameter changes after seeing results: **none.** Every rule the spec leaves open is marked CHOICE in the code.

## v0.8.1 · 2026-11-08 · losing sub-strategies turned off (the user: "Yes, turn them off")
- Off (net loss or a loss in either half, one-year test): gold S2, S3, S4 · EUR/USD S3, S4 · GBP/USD S1, S3, S4 ·
  EUR/CHF S1, S3 (`playbook.DISABLED`: status OFF, never sent, still measured in `PLAYBOOK.md`).
- On: gold S1 · EUR/USD S1, S2, SnapBack · GBP/USD S2 · EUR/CHF S2 · AUD/CAD · AUD/CHF S1–S4 (no trade in the year:
  nothing to judge). Switched on only: 77 trades, win 61 %, +30.79R — chosen on the same year, so optimistic.
- Note: with gold S4 off, gold S1 takes one more trade (6), and its second half is −0.59R; not re-filtered (no
  repeated selection on the same data).

## v0.9 · 2026-11-08 · only the profitable, high-win-rate strategies stay (the user's request)
- EUR/USD INST-AMD re-coded by the spec's own logic first (no displacement asked for EUR/USD, the sweep's EXTREME must
  reach VWAP ∓ 1.5σ / an H1 FVG, distribution: TP1 the daily VWAP, TP2 the opposite session extreme): S1 2 trades
  −0.69R, S2 0, S3 17 trades 24 % (second half a loss), S4 −2.39R. Still no profit: removed.
- Removed from the code (git history keeps them): GOLD-QUANT S1–S4, INST-AMD S1–S4, CABLE-RAID S1–S4, SWISS-REV S1 and
  S3, RISK-REGIME S1–S4. The rule: kept = win rate >= 55 % and profit in both halves of the one-year test.
- Kept: EUR/USD SnapBack 3σ (27 tr, 70 %, +9.68R), EUR/CHF SWISS-REV S2 (11 tr, 64 %, +6.31R), AUD/CAD range
  reversion (17 tr, 59 %, +5.94R). Together 55 trades, 65 %, +21.93R — selected on the same year: optimistic.
- XAU/USD, GBP/USD and AUD/CHF have no strategy that passed: their teams keep the analysis (charts, badges, agents,
  data checks) and send nothing; the card says so.
