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

## v1.0 · 2026-11-09 · gold: the user's spec xau_usd_gold_multi_agent_quantitative_strategy_claude_prompt.md
- Replaces everything earlier for XAU/USD (`backend/app/smc/gold.py`): "London-NY Fix Liquidity Sweep & ATR Displacement
  (ICT/Quant)", Scenario A (H4 = H1 BOS + EMA 50, killzone sweep of L_Asia / M15 EQL in discount, displacement MSS + FVG +
  OB on M15 / M5, CE in the OTE, SL sweep - 0.35 ATR M15, TP1 internal liquidity / 1.8 R with BE + 0.1 R, TP2 an external
  pool at RR >= 3, risk 1 % or 0.5 % in high ATR), Scenario B (>= 85 % ADR by 12:30, PDH / PDL sweep 12:30-14:15 with
  RVOL >= 1.8, M15 engulfing + CHoCH, M5 FVG retest to the session VWAP, risk 0.5 %, RR >= 2.5), Scenario C (Tier-1 USD
  lockout -30 / +15 min, limits pulled 15 min before, post-news FVG outside the news candle's 50 %), Scenario D (chop:
  NO_TRADE with the BSL / SSL wake-up levels).
- The section 3 math: Wilder ATR, 3-bar fractals, BOS / CHoCH at 0.10 ATR, the M15 sweep (0.10-1.25 ATR, rejection close,
  WDR >= 0.45), displacement (1.35 x the 20-candle body, 68 % of range), FVG >= 0.25 ATR M15, CE, E_eq, OTE.
- The 7 agents in the spec's DAG and its JSON contract (`goldReport`): badges <= 55 characters, the Devil's failure
  probability (hard veto >= 65 %, CHOICE weights, with DXY / US10Y from Yahoo), the Lead's consensus score >= 78 with the
  Risk Manager's approval; the Backtest Engineer rejects a subset with N < 30 or E[R] < +0.45R (the spec's 2023-2026
  table shown as its claim). UI: a VETO status icon.
- Fixed: M15 candles built from M5 carried no volume (RVOL was always 0).
- One year (Dukascopy): Scenario A 1 trade (a loss), Scenario B 0 — the spec's conditions are strict; its benchmark
  (A 418 trades, 58.4 %) is not reproduced on this data. Parameter changes after seeing results: none.

## v1.1 · 2026-11-09 · GBP/USD: the user's spec gbp_usd_multi_agent_quantitative_strategy_claude_prompt.md
- Replaces everything earlier for GBP/USD (`backend/app/smc/cable.py`): "London Judas Swing & Unicorn Breaker-FVG
  Strategy". Scenario A (Asian box 00:00-06:30 valid at 15-48 pips and <= 0.42 ADR; Judas 0.20-0.85 ATR H1 in 06:45-09:15
  into an H1 POI; displacement back inside beyond SH_pre; Unicorn = breaker ∩ FVG, else OB + FVG; limit at the proximal
  edge; SL L_Judas - 3 pips or the breaker + 0.25 ATR M15 when the wick > 35 pips; TP1 the opposite box edge, TP2
  TP_ADR 75 % or PDH at >= 3 R), Scenario B (H1 BOS London, 45-68 % ADR, NY pullback into 50-70.5 % of the London leg,
  MSS + FVG, TP the remaining 0.85 ADR), Scenario C (>= 105 % ADR, H4 / D1 sweep 15:00-16:00, M5 CHoCH + FVG, 38.2 %
  target, risk 0.5 %), Scenario D (Asian box > 55 pips, UK CPI / BOE MPC ±30 min: NO_TRADE).
- Risk Manager: SL 8-32 pips, RR >= 2.60 to TP2, 1 % / 0.5 %. Devil: box too wide, two full-body M15 closes outside,
  EUR/GBP cross-flow (EUR/USD / GBP/USD) — hard veto >= 65 %. The JSON contract (`pairReport`), badges <= 55.
- One year (Dukascopy): A 6 trades, 67 %, +1.58R (both halves positive); B and C 0 trades. The spec's benchmark (A 346
  trades, 60.4 %) is shown as its claim. Parameter changes after seeing results: none.

## v1.2 · 2026-11-09 · EUR/USD: the user's spec eur_usd_multi_agent_quantitative_strategy_claude_prompt.md
- Replaces everything earlier for EUR/USD, SnapBack 3σ included (git history keeps it) (`backend/app/smc/fiber.py`):
  "London-NY Killzone VWAP Orderblock & SMT Divergence". Scenario A (γ_Asia <= 0.38; 06:45-09:30 sweep of the Asian
  side with the H1 bias touching VWAP ∓ 1.5σ; M15 MSS + unmitigated OB [L_ob, O_ob] + FVG >= 0.20 ATR; limit at O_ob or
  the 50 % FVG inside it; SL sweep - max(2 pips, 0.30 ATR M15); TP1 the session VWAP 40 %, TP2 the opposing Asian side /
  PDH at >= 2.8 R; entries 07:00-10:00), Scenario B (London >= 35 pips with an H1 BOS; 12:00-14:30 pullback to the
  discount, the session VWAP and a London M15 OB; M5 rejection WDR >= 0.40; TP the 1.272 / 1.618 extension), Scenario C
  (ECB / Fed / NFP / CPI: orders pulled 20 min before, then only B with the H4 structure), Scenario D (after 16:30 UTC or
  >= 85 % ADR: NO_TRADE).
- Section 3: the 00:00 and 12:00 anchored VWAPs with volume-weighted σ bands (TWAP on a feed without volume, CHOICE),
  SMT against GBP/USD, γ_Asia. Risk: 2-pip buffer, SL 6-28 pips, RR >= 2.4, 1 % (0.5 % over 65 % ADR). Devil: γ > 0.50,
  no GBP/USD confirmation, after 15:30, H4 OB before 1.5 R — veto >= 65 %. Lead: >= 78 in a killzone. `pairReport`.
- Fixed while building: the OB freshness check looked at candles after the setup (a look-ahead).
- One year (Dukascopy): A 0 trades, B 0 trades — of 262 days, 128 fail γ <= 0.38, 73 have no sweep, 56 no OB + FVG,
  the 5 left miss 2.8 R. The spec's benchmark (A 382 trades, 61.2 %) is shown as its claim. No parameter changed.

## v1.3 · 2026-11-09 · EUR/CHF: the user's spec eur_chf_multi_agent_quantitative_strategy_claude_prompt.md
- Replaces everything earlier for EUR/CHF, SWISS-REV S2 included (git history keeps it) (`backend/app/smc/swissy.py`):
  "Ornstein-Uhlenbeck Z-Score & Range Sweep Mean Reversion". Section 3 as written: Z on M15 (SMA 50, sample std N - 1),
  R/S Hurst over 100 H1 log returns, ADX 14 H1, the OLS half-life (window 200 M15, CHOICE; valid 4-28 bars).
- Scenario A (H < 0.46, ADX < 28, 06:30-15:30; a pierce of ±2.2σ that sweeps an intact M15 / H1 swing, the close back
  inside ±2.0σ with WDR >= 0.45 or an M15 CHoCH; market at the M15 close; SL extreme ∓ 0.5 ATR M15; TP1 μ 60 %, TP2 the
  opposing 1.25σ band / PDH-PDL / the H1 range's far side at >= 2.2 R), Scenario B (an H4 channel boundary with >= 2
  earlier swing touches, 1.80 <= |Z| < 2.15, M15 MSS + OB + FVG limit, TP the H4 midpoint), Scenario C (H > 0.55, ADX > 32,
  |Z| > 3.2, RVOL >= 2.5: A and B off for 24 h, CHOICE), Scenario D (|Z| < 1.20, ATR M15 < 4 pips: NO_TRADE).
- Risk Manager: 1 % with the live USD/CHF pip value, spread < 12 % of SL, blended RR >= 1.85. Devil (hard veto): H > 0.52
  or ADX > 30, SNB / ECB ±30 min, an M15 close on its extreme outside ±2.5σ. BTP-Bund: no feed (said so). `pairReport`.
- Also fixed: the EQH / EQL pools were rounded to 2 decimals for every pair (FX now 5).
- One year (Dukascopy): 15 setups (A 14, B 1), none passes the spec's own spread rule (1.5-pip spread = 21-59 % of the
  4-8 pip stops). Taken anyway they would be 14 trades, 5 wins (36 %), -1.18R. The spec's benchmark (A 395 trades,
  68.6 %) is not reproduced: H < 0.46 holds on only 13 % of H1 bars here. No parameter changed after the results.

## v1.4 · 2026-11-09 · AUD/CHF: the user's spec aud_chf_multi_agent_quantitative_strategy_claude_prompt.md
- Replaces everything earlier for AUD/CHF (the analysis-only team) (`backend/app/smc/aussie.py`): "Risk-Regime Trend
  Efficiency & Cross-Session Inducement Pullback". Section 3 as written: Kaufman ER 20 H1, the EMA 21 / 55 / 200 ribbon,
  the confirmed trend (ribbon stacked, ER >= 0.32, last H1 break a BOS), the 50-78.6 % pullback touching [EMA21, EMA55],
  the IDM / L_Asia sweep, the RSI 14 M15 hook (<= 38 then > 45; 62 / 55 for shorts, CHOICE), BWR = BB(20, 2σ) / KC(20,
  1.5 ATR) on M15.
- Scenario A (23:00-05:00 or 06:30-10:30, H4 aligned; M15 MSS + OB + FVG in the ribbon; limit at the OB / 50 % FVG; SL
  sweep ∓ 0.35 ATR M15; TP1 the external H1 swing 50 %, TP2 -0.272 / -0.618 at >= 3.0 R), Scenario B (BWR < 0.85 for 6
  M15 in Asia, a 06:30-08:30 sweep then a >= 1.5 ATR body with RVOL >= 1.7 beyond the box with H4; the first FVG retest;
  TP 2.5 × the box), Scenario C (H1 bearish CHoCH > 2 ATR under EMA 200, short the 50-61.8 % retrace into the H1 OB, TP2
  -0.272 at >= 2.6 R), Scenario D (ER < 0.22 or 20:45-22:30 rollover: NO_TRADE).
- Risk Manager: 1 % with the live USD/CHF pip value, shorts 0.5 % (counter-carry), RR >= 2.60 to TP2 (A 3.0). Devil:
  ER < 0.25 +40, a close beyond the H1 major swing +70, an AUD/CAD or EUR/CHF H1 shock (> 1.5 ATR) against the trade +35,
  veto >= 65. The user's news rule: no AUD / CHF high-impact release ±15 min. Lead: consensus >= 78. `pairReport`.
- One year (Dukascopy): A 0 (only 691 of 6250 H1 bars are a confirmed trend, and only 3 M15 candles reached the
  pullback zone while it held), C 0 (11 shocks, none with its OB in 50-61.8 %), B 6 setups, 3 pass the checklist but all
  three have a stop under the test's 5× cost floor, so the year counts 0 trades. Counted anyway: 1 win, 2 losses,
  -1.04R. The spec's benchmark (A 312 trades, 57.7 %) is not reproduced. No parameter changed after the results.

## v1.5 · 2026-11-09 · AUD/CAD: the user's spec aud_cad_multi_agent_quantitative_strategy_claude_prompt.md
- Replaces everything earlier for AUD/CAD, the commodity range reversion "P" included (it had 17 trades, 59 %, +5.94R
  on the year; git history keeps it) (`backend/app/smc/loonie.py`): "Cointegrated Regression Channel & VPOC
  Supply/Demand Reversion". Section 3 as written: the 100-bar H1 OLS channel (e_N, σ_e with N - 2, Z_reg, β~ = 24 β /
  ATR 14 H1, R²); the 100-bar H1 volume profile in 40 bins (typical-price bins, TPO when the feed has no volume, CHOICE),
  VPOC and the narrowest contiguous 70 % value area; H1 S/D zones (base candle, >= 2.0 ATR departure within 3 candles
  with a BOS, CHOICE), fresh = tested <= 1, up to 30 days old (CHOICE).
- Scenario A (|β~| <= 1.25, |Z_reg| >= 1.90 outside the VA, an intact swing swept into a fresh zone, M15 CHoCH + OB +
  FVG toward VPOC; limit at the OB / 50 % FVG; SL the zone's distal edge ∓ 0.30 ATR M15; TP1 VPOC 50 %, TP2 the opposite
  VA edge at >= 2.4 R), Scenario B (0.60 < |β~| <= 1.60, 12:30-16:00 / 23:00-04:00, the ∓1.75 σ_e line + an H1 zone, M15
  MSS; TP the opposite 1.75 σ_e line at >= 2.8 R), Scenario C (RBA / BOC / CAD jobs / AUD CPI ±20 min, the 20:45-22:30
  rollover: nothing), Scenario D (|Z_reg| < 1.10: NO_TRADE).
- Risk Manager: 1 % at the CAD pip value ($7.30), spread <= 1.5 pips, RR >= 2.20. Devil: slope > 1.60 against the fade
  +45, a zone tapped >= 2 times +40, 19:00-21:00 UTC +30, veto >= 65. Lead >= 78. `pairReport`. `playbook.scan` now
  takes the config's spread.
- One year (Dukascopy): 14 setups (A 6, B 8), and every one fails the spec's spread rule: the app's AUD/CAD spread is
  2.0 pips (> 1.5), so 0 trades. Without that rule and above the test's 5× cost stop floor: 3 trades, 1 win, -0.55R.
  The spec's benchmark (A 328 trades, 64.6 %) is not reproduced. No parameter changed after the results.

## v1.6 · 2026-11-09 · Data feed & charts: the user's spec data_feed_charting_engine_architecture_prompt.md
- Feed (`backend/app/market/oanda.py`, `market/data.py`): OANDA v20 is the primary source when OANDA_API_TOKEN is set
  (the user's choice): mid-price candles (`price=MBA`), the bid / ask spread kept apart (`Candle.spread`), real tick volume,
  UTC alignment (H4 00/04/08 UTC, days 00:00 UTC), up to 5,000 candles. Missing slots are backfilled once with a from / to
  request. A failure falls back to Yahoo for 60 s. Live price: OANDA M1 mid + spread. No token: Yahoo, as before.
- CandleSanitizer (`market/sanitize.py`) on every intraday series: UTC grid snap, duplicate merge, the 4.5 × ATR 20
  bad-tick wick cut (no volume follow-through, not revisited; the spec's 500 ms tick rule cannot be seen on candles),
  missing-slot detection in market hours (Sunday 17:00 to Friday 17:00 New York, the 16:55-18:10 New York break excepted,
  so DST moves the UTC hours). Nothing is ever invented: a gap the provider cannot fill stays a gap.
- Data checks (`smc/integrity.py`, applied to the six teams): Backtest Engineer "data FIT • N • WR • PF" when the one-year
  sample has N >= 30 and the live M5 continuity >= 99.5 % (else LIMITED / NOT FIT); the Devil's 4-point audit (48 h M5
  continuity 100 %, sweep candle volume, FVG > 1.5 × spread, not 21:50-22:15 UTC). A failed audit vetoes the trade;
  a clean one says "M5 feed VERIFIED CLEAN • …". The year test now stores gross win / loss R (the PF).
- Chart (`frontend`): tabs M1 | M5 | M15 | H1 | H4 | H1 + M5 (split view); SMC overlays computed on the timeframe shown
  (`chart/smcOverlay.ts`): premium / discount tints with the 50 % line, BOS solid / CHoCH dotted on body closes, Asia /
  London KZ / NY KZ bands, "$$$ BSL / SSL" at the Asian range and PDH / PDL with "✕ Swept", unmitigated FVGs shrinking at
  their CE; the position tool's SL pips and 1 % risk, TP pips and R:R. An "SMC" toggle next to "Analysis".
- Live on Yahoo today (no token yet): FX continuity 98-99 % over 7 days, gold M5 misses slots (e.g. Monday 14:20), so the
  gold Devil vetoes on the feed check; no pair has N >= 30 in its year, so every Backtest Engineer says LIMITED.

## v1.7 · 2026-11-09 · AUD/CAD "P" restored; the simple 3-rule test
- The user asked for a simple version ("don't complicate it"): `backend/app/smc/simple.py`, the same three rules for
  the six pairs (direction · a sweep of the Asian range / PDH-PDL in the pair's window · an M15 MSS; limit at the retest,
  SL beyond the sweep, TP 2 R, closed 20:45 UTC, no entry ±15 min of news), fixed before the run. One year: 89 trades,
  34 %, -19.84R, PF 0.64; first 60 % -13.79R, last 40 % -6.06R. It loses in both parts and is NOT switched on (kept
  for research).
- AUD/CAD goes back to the commodity range reversion "P" (the user: "bring it back"), with the general team and its
  chart (Bollinger 3σ, 3-touch H4 levels). One year: 17 trades, 59 %, +5.94R, both halves positive. loonie.py (the AUD/CAD
  md: 0 trades) stays in the repo, unused.
- Switched on now: GBP/USD A + AUD/CAD P = 23 trades, 61 %, +7.52R (gold A 1 trade, -1.02R; the others 0).

## v1.8 · 2026-11-10 · FXAlexG "Set & Forget" for every pair: the user's spec fxalexg_set_and_forget_strategy_claude_implementation_prompt.md
- Part 1: the universe grows to FXAlexG's watchlist, gold + 28 forex pairs (29): `market/pairs.py` (Yahoo tickers),
  `market/oanda.py` (instruments), `smc/configs/<PAIR>.json` + `smc/pairs/<PAIR>/config.json` (pip, decimals 2 / 3 / 5,
  "500" step, max AOI width, tier, currencies, spreads CHOICE), live pip values for every quote currency (`desk._pip_value`),
  JPY prices (decimals 3, price sanity per pair), the portfolio cap on all 8 currencies (`skill/portfolio.exposure`), the
  frontend list and a JPY flag.
- Part 2: `backend/app/smc/alexg.py`: bodies, Snake Trick elbows (k W1 2, D1 3, H4 3, H1 3, M30 3, M15 4) and the body-close
  structure machine; W1 / D1 / H4 sync and its vetoes; 3-touch W1 (156) / D1 (300) AOIs <= W_max, W1 + D1 merge, "Every 500"
  snap, ± 5 pip proximity, 10 pip invalidation; live EMA 50 / prior elbow / candles / patterns; the mandatory SoS +
  engulfing on H1, M30, M15 (24 bars, > 1.8 ATR = 50 % limit); S_AlexG and the grades; SL / TP / RR >= 2.5; seasonal risk.
- Part 3: the 7 agents with the spec's score formulas, statuses, badges and the pairReport contract (EXECUTE /
  WAIT_FOR_TRIGGER / WATCH_ONLY / VETOED). CHOICE: when the Devil's only reason is the missing trigger, the Lead says
  WAIT_FOR_TRIGGER (the spec's own state) instead of VETOED; nothing executes either way.
- Part 4: D1 750 bars (W1 resampled from it), the chart (AOI boxes with touches / width, the "500" line, EMA 50 H4 / D1,
  H4 body HH / HL / LH / LL, the SoS neckline), tests (`test_alexg.py`). 80 backend tests pass, tsc clean. Every earlier
  per-pair strategy (gold.py, cable.py, fiber.py, swissy.py, aussie.py, loonie.py, AUD/CAD "P") stays in the code, unused.
- One year (Dukascopy, the 6 pairs with data; D1 / W1 built from the same year, so W1 AOIs see 52 weeks, not 156): GBP/USD
  1 trade, -1.10R; the others 0. Behind it: 3,100 SoS + engulfing setups at an AOI on the 5 FX pairs, of which ~230 reach
  grade B; the consensus >= 78 gate stops almost all (the Backtest Engineer scores 40 with N = 0, so consensus is capped).
  Taken all together the setups lose (40-48 % win, -0.06 to -0.26R each); grade B + RR >= 2.5 + no veto without the
  consensus gate: 4 trades, 1 win, -0.78R. Gold: 0 setups (± 5 pips = $0.50 and a $6 max AOI width are very tight for gold).
- The 23 new pairs have no history in `smc/pairs/` yet (no Dukascopy download made); their Backtest Engineer says N = 0.
- 29 teams read in 37 s locally (the Vercel cron allows 60 s per call).

## v1.9 · 2026-11-10 · FXAlexG redesigned: one engine, 5 agents, 3-stage alerts (the user's second FXAlexG spec)
- Step 1 · purge: gold.py, fiber.py, cable.py, swissy.py, aussie.py, loonie.py, simple.py, engine.py, engines.py, agents.py,
  chart.py, manage.py, integrity.py and their tests are deleted, with the old research tools that needed them. playbook.py
  keeps only the shared pieces (candles, indicators, the M5 trade follower) and the registry. Every one of the 29
  instruments runs alexg.py only. The tick-volume and M5-gap vetoes are gone: the strategy reads W1 / D1 / H4 / H1 / M30 /
  M15 prices only. Configs carry the new max AOI widths (gold and GBP crosses 65, EUR/GBP and EUR/CHF 50, AUD / NZD crosses
  55). Candle caches: W1 / D1 30 min, H1 5 min, M5 60 s, each ending just after its next candle closes. The notifier reads
  the teams 6 at a time.
- Step 2 · the engine: elbows confirmed by a close back under B+ / over B- (k = 3, W1 2); a trend shift needs a close
  0.5 pip beyond HL / LH; sync = W1 + D1 (+ H4 or its pullback) or D1 + H4 with no opposing W1 AOI inside 1.5 x risk;
  AOIs with >= 3 D1 touches or >= 2 W1 touches, 12 pips <= width <= W_max (a tighter cluster is widened to 12, CHOICE),
  psych level within 8 pips; the live window = one of the last 24 H1 candles within max(8 pips, 0.12 x ADR 20) and the
  close not 10 pips beyond the distal edge; the new engulfing (close beyond the previous body, body >= 0.85 x it); SL capped
  at 1.2 x ADR 20; the break-even trigger at +1.5 R (25 % banked, stop to the entry); TP 5 pips before the opposing
  D1 / W1 structure, at most 3.5 R, RR >= 2.5.
- Step 3 · the 5 agents: trend_director 25 %, aoi_architect 25 %, confluence_grader 25 %, trigger_sniper 15 %,
  risk_guardian 10 % + veto (news +-30 min, RR < 2.5, spread > 15 % of SL). CHOICE: the spec gives each agent's statuses and
  weight but no score formula, so the scores are simple steps (see alexg.squad). EXECUTE iff sync, S_AlexG >= 80, SoS +
  engulfing, RR >= 2.5 and no agent in veto. The frontend shows the 5 agents, the grade badge and the confluence bar with
  its 80 % line.
- Step 4 · alerts: RADAR (trend ok, in an AOI, >= 65 %, SoS in, engulfing awaited; once per wave through a watermark),
  SIGNAL (the spec's Telegram template with the plan, the confluences and the 5 badges), TRADE MANAGER (FILLED,
  BREAKEVEN +1.5R, TP_HIT, SL_HIT, BE_CLOSED, EXPIRED). Each goes to Telegram, web push and the in-app feed
  (/api/smc/signals now returns the radar list; a toast with a sound shows a new signal or radar). CHOICE: a market entry
  is alerted only within 20 minutes of its trigger candle.
- Step 5 · measured, one year of Dukascopy on the 6 pairs with stored data, news trades removed: about 6,200 two-step
  triggers at an AOI, 51 passed the gate: 39 % wins, -14.76R, PF 0.56 (first 60 %: 22 trades, -4.91R; last 40 %: 29 trades,
  -9.85R). Exits: 6 full targets, 14 break-even closes after +1.5 R, 31 stops. Gold: 32 triggers, none passed. The spec's
  goal (PF > 1.5, WR >= 50 %) is NOT met on this data; no number was changed after seeing the result. The 23 new pairs
  have no stored history.
- Tests: test_alexg.py and test_notify_pipeline.py replace the old spec tests: 40 backend tests pass, tsc clean. Live:
  29 teams read without error (42 s cold, 18 s with warm caches); AUD/JPY gave a live EXECUTE, EUR/USD and GBP/AUD a radar.

## v2.0 · 2026-11-11 · FXAlexG overhaul: SF_BR / SF_BOUNCE / SF_COUNTER, the GPA, the 5-agent desk (the user's third FXAlexG spec)
- Part 1: the legacy modules stay deleted; playbook.STRATEGIES = SF_BR (break & retest continuation), SF_BOUNCE (direct
  AOI bounce, 4th+ touch), SF_COUNTER (1D shifted against the 1W) for the 29 instruments; the old ids are gone.
- Part 2: Yahoo tickers USDJPY=X / USDCHF=X / USDCAD=X; a 2H timeframe (aggregated from 1H, OANDA H2); the desk reads
  M5 2000, H1 4000 (4H 1000), D1 900 (W1 120+ weeks); the notifier reads 8 teams at a time.
- Part 3 (alexg.py rewritten): No-Gap candles for every pattern; the EMA 50 tap (0.15 ATR); line-chart structure on
  closes (m: W1 2, D1 / 4H 3, LTF 3 CHOICE), HL strictly behind HH; AOIs from close + wick pivots, <= 0.35 ATR (D1) thick,
  touches = entry + a 0.75 ATR (D1) reversal within 10 candles (CHOICE), 3+ candles apart, >= 3, inside the active
  [HL, HH] / [LL, LH]; round numbers 50 / 100 pips (gold $25 / $50) within 10 pips; confirmations on 2H / 1H / 30M / 15M
  (doji / pinbar, the new engulfing, LTF SoS, double top-bottom / H&S); the 9-item 100-point GPA (A+ 90, A 80, B 75, C+ 70,
  F); entry at the confirmation close (band 0.15 ATR 1H), SL = AOI / swing - 0.20 ATR 1H - spread, TP 7 pips (CHOICE in
  the 5-10) before the next opposing D1 / W1 zone or the round number inside it, RR >= 2.0. A confirmation outside
  06:00-17:00 UTC executes at the next 06:00 if price is still inside the band (CHOICE: 17:00-21:00 waits too).
- Reading fixes made after the first run (not tuning): the TP target is the next OPPOSING zone (its last touch rejected
  price against the trade), not any zone above; the round number must sit at or just inside that target zone.
- The trade follower: at +1.5 R the stop goes to the entry + 2 pips (no partial close); a trade not in profit on Friday
  20:00 UTC is closed (TIME).
- Part 4: the 5 agents with the spec's scores and statuses (trend 100 / 80 / 70 / 25, AOI 100 / 85 / 60 / 0, grader = GPA,
  trigger 100 / 85 / 65 / 40, guardian: RR, session, Mon-Wed / Thursday A-grade + 1.2 ADR / Friday veto, news +-30 min,
  rollover 21:45-22:15, spread > 25 % of SL); consensus 0.25 / 0.25 / 0.20 / 0.20 / 0.10; execute iff consensus >= 70,
  GPA >= 70, no veto, trigger and guardian ok.
- Part 5: AOI_WATCH_ALERT ("👀 [RADAR] ..."), SIGNAL_EXECUTE (setup type, grade, consensus, entry zone, SL pips, BE level,
  front-run TP + psych, R:R, risk by grade 1 / 0.75 / 0.5 %, the 5 agents), MANAGER_LIVE_UPDATE (FILLED, BREAKEVEN LOCKED
  (+1.5R), TAKE PROFIT HIT (+X R), STOP LOSS HIT, CLOSED / EXPIRED). /api/telegram/test-me added for the bell.
- Part 6: tabs M15 | M30 | H1 | H2 | H4 | D1 | W1 | H4 + H1; pairs grouped (Majors, JPY, GBP/EUR, Commodity/CHF, Gold);
  the Sunday Swings toggle (top 5 by consensus, signals and radars first); the blue 50 EMA on every timeframe; AOI boxes
  "1W/1D AOI · N Touches · Psych ..."; HH / HL / LH / LL markers; the 1H SoS line; the +1.5R line on the position box;
  TeamCard: the 5 agents with score and weight, the GPA grade and bar (70 % line), the 9-point checklist; the bell
  (live feed + Test Telegram + Test Web Push).
- Part 7: 43 backend tests pass (test_alexg.py), tsc clean, the app checked live (no console or server error).
- Measured: Dukascopy one year, 6 pairs (D1 / W1 built from that year): 16 trades, 19 % wins, -3.14R, PF 0.76
  (SF_BR 11 trades +1.14R, SF_COUNTER 5 trades -4.28R, SF_BOUNCE none). Yahoo last 60 days, 29 pairs (full W1 / D1):
  29 trades, 21 % wins, +2.25R, PF 1.14. Both samples are small.

## v2.1 · 2026-11-11 · TP capped at 2.5R (the user: "TP 2R, 2.5R at most")
- `alexg.TP_CAP_R = 2.5`: the front-run target is cut to entry + 2.5 x risk when the structure is farther; the 2.0R floor stays.
- Same trades as v2.0 (the entries do not change); only the winners are smaller. Dukascopy one year, 6 pairs: 16 trades,
  19 % wins, -6.04R, PF 0.54 (was -3.14R). Yahoo 60 days, 29 pairs: 30 trades, 23 % wins, -1.17R, PF 0.93 (was +2.25R).
  No trade turned from a loss into a win: the ones that lost never reached 2.5R either.

## v2.2 · 2026-11-11 · TP from the structure only (the user: "the TP from the structure, not arbitrary, and the stop")
- The 2.5R cap is removed: the TP is the next opposing 1D / 1W zone, HH / LL or the round number inside it, 7 pips before it;
  RR >= 2.0 stays. The SL was already structural (beyond the AOI or the LTF swing, minus 0.20 ATR 1H and the spread).

## v2.4 · 2026-11-11 · Testable parameters, honest validation, calm charts, no radar notification (the owner's prompt)
- Parameters: backend/app/smc/strategy.json holds every testable threshold with its origin (source / research / baseline)
  and a finite pre-registered grid; alexg.P reads it, alexg.use(preset) switches versions for the validation only and
  refuses a value outside its grid. Source rules: >= 3 independent confirmed touches, the H4 fallback. Research numbers
  (ours, never the author's): zone thickness 0.35 ATR (D1), rejection 0.75 ATR (D1) within 10 candles, touches 3 candles
  apart, 500 H4 candles for the fallback, counter-trend GPA 80. Baseline: minimum R:R 2.
- H4 fallback (source: the gold example): when W1 / D1 give no three-touch zone inside the active range, zones are built
  on H4 with the same rules and must lie inside the active D1 / W1 range. It never replaces a W1 / D1 zone.
- Counter-trend (SF_COUNTER) kept apart: its own label, its own statistics, and a stricter gate (GPA >= 80; trend-following
  setups need 70). The old gate stays available as the "baseline" preset.
- Minimum R:R: 2 kept. 3R and 4R were run as fixed, separate versions (never tuned): they leave too few trades to say
  anything and are not adopted. With 3R wins and 1R losses the break-even win rate is 25 % before costs, with 4R 20 %.
- Validation (smc/tools/validate.py, smc/research/VALIDATION_2026-11-11_*.md, backend/app/smc/research/validation.json):
  baseline vs candidate vs candidate_rr3 / rr4, chronological 50 / 25 / 25 split, per instrument and per setup type:
  trades, win rate, average win / loss / cost in R, net expectancy with a seeded 95 % bootstrap interval, profit factor,
  maximum drawdown. Pre-registered: an instrument needs 100 out-of-sample trades and an interval above 0 R.
  Dukascopy year (6 pairs): baseline 16 trades, E -0.20R [-0.95, +0.77]; candidate 13 trades, E -0.08R [-1.08, +1.08].
  Yahoo 60 days (29 instruments): baseline 30 trades, E +0.17R [-0.40, +0.82]; candidate 29 trades, E +0.20R [-0.37, +0.92].
  The most out-of-sample trades any instrument has is 4 of the 100 needed: all 29 are "insufficient data". Nothing here
  shows the strategy is profitable, and nothing shows it is not.
- The team read carries `evidence` (state, out-of-sample trades, needed) and each setup its `family`, `invalidation`,
  confirmation timeframe and distances in the pair's own pips.
- Charts: calm by default. Always: candles, the zone in play (or the nearest zone above and below), the 1D structure
  levels, the proposed trade as three labelled lines (BUY / SELL ENTRY price, STOP price · pips · -1R, TARGET price · pips ·
  R:R) with the break-even step, a small legend, "research signal · not an order". Switches: "EMA 50" (on) and "Details"
  (off): the other zones, round numbers, 4H levels, HH / HL markers, the SoS line, premium / discount, BOS / CHoCH,
  sessions, liquidity, FVGs. The setup panel shows the same numbers, the timeframe, grade, family, invalidation and reasons.
- RADAR notifications removed: notify.tick() sends nothing for a radar read (no Telegram, no admin chat, no web push),
  /api/smc/signals no longer returns radar items, the toasts and the bell show signals only. The read's `radar` field
  stays (the "Watching" status on the pair's own card); stored radar items and watermarks are left untouched.
  SIGNAL_EXECUTE and the trade manager's updates are unchanged.
- Tests: tests/test_validation.py (9 tests) + the notification test now asserts that a radar sends nothing.

## v2.4.1 · 2026-11-11 · A pair shows at once; the pair bar holds only the pairs
- Slow switch, cause 1: the strategy maths of a team read (about a second, cold) ran on the server's event loop, so the
  chart's own candle request waited behind the other pairs' reads (0.22 s alone, 1.0 s behind three reads). It now runs in
  a worker thread, one read at a time (several Python threads side by side starved the loop more: 3.3 s, measured).
- Cause 2: Yahoo candles were rounded with exact Decimal maths, 122,000 calls per pair read (0.35 s) on the event loop.
  jsnum.round_to has a fast path, identical to Number(x.toFixed(d)) on 600,000 checked prices (halves and -0 included);
  only a value at a half takes the exact path. Measured: a cheap request waits at most 1.0 s once, instead of 3.3 s.
- Cause 3: the background warm-up loaded all 29 pairs' candles, then all 29 teams, while the user's clicks waited in line.
  It now goes pair by pair (candles and team together) and pauses while the user's own pair loads and 1.5 s after a switch.
  Measured in the app: a warmed pair shows (chart and team) in 50-150 ms, a cold one in about 1 s.
- The pair bar holds only the pairs: no group names (a thin line between groups), no "Sunday Swings", market status or price
  (the status bar and the chart already show them). Each pair is a 44 px target, 8 px apart, the strip swipes and snaps on a
  phone (about 3 pairs visible), drags or wheels with a mouse, and the pair on screen is scrolled into view when it changes.
  The "Top 5" switch (the former Sunday Swings) moved to the chart toolbar.

## v2.5 · 2026-11-11 · Each user's USD risk and lot, a fixed stop, the Telegram copy / import (the owner's prompt)
- Per-user USD risk (users.risk_usd, already in the schema and unused until now): GET / PUT /api/me/risk, a positive
  finite amount up to 1,000,000, saved on the signed-in user only. Not in user_json, so not in the admin's user list.
  Not set: every size says "set your USD risk"; no default, never another user's value.
- The lot (smc/sizing.py): risk per lot = |entry - stop| x contract units x Q-to-USD + (spread + slippage) x pip x units x
  Q-to-USD + commission, once; lots = risk / risk per lot rounded DOWN to the lot step; under the minimum lot: "size
  unavailable" (never rounded up); the estimated loss is re-checked <= the risk. Q-to-USD from the app's live prices
  (Q/USD, or 1 / USD/Q); a missing, "last known" or stale quote (> 15 min with the market open, > 72 h closed) makes the
  size unavailable. All 29 configs gained min_lot 0.01 / lot_step 0.01 with a lot_note: the app's stated broker assumption
  (a standard retail MT4 / MT5 account), to change to the broker's own contract specification.
- Snapshots (table user_signal_sizes, unique per user + signal): the user's risk, the lot, the estimated loss and the
  contract / conversion data used, with the time. Written once (from the app, the private Telegram line or an import) and
  never rewritten: a later risk change applies to signals sized after it. GET /api/me/sizing/{id}, GET /api/me/sizings,
  all scoped to the session's user; no route takes a user id.
- Fixed stop: strategy.json break_even = false (origin "owner"). The engine, the backtest and the trade manager follow the
  stop saved with the signal to the end: no break-even step, no trailing, also for signals sent before. The baseline preset
  keeps the old break-even for comparison. Re-run (Dukascopy year): the candidate is unchanged (13 trades, -0.08R
  [-1.08, +1.08]): no trade of that year ended at break-even.
- Telegram: the signal is short (symbol, side, grade, entry, SL, TP, R:R, timeframe, UTC time, signal id) with the copy
  payload `LD|v=1|id=…|symbol=…|side=…|entry=…|sl=…|tp=…|tf=…|time=YYYY-MM-DDTHH:MMZ` as plain text and a one-tap "📋 Copy
  setup data" button (Bot API 7.11 InlineKeyboardButton.copy_text; the bot sends raw Bot API JSON over httpx, so no library
  version limits it; older clients keep the text line). The payload never holds a risk or a lot. Each linked PRIVATE chat
  gets one more line, its owner's own lot from their own risk (saved as their snapshot); the admin chat, groups and
  channels never get one.
- Import (POST /api/me/import/preview, POST /api/me/import; My account → "Import a signal"): only the LD| line is read,
  exactly these keys, each validated (symbol of the app, side, prices with the pair's decimals, BUY stop < entry < target /
  SELL target < entry < stop, timeframe, UTC time), then checked against the signal the app saved: an id the app never
  sent, an edited field, a stale signal (> 24 h), a future one or an ended one is rejected. The lot is then computed from
  the signed-in user's own risk; a lot in the pasted text is never read. Nothing places an order.
- App: My account → "My risk per trade" and "Import a signal" (with "My saved sizes"); each signal on the pair card shows
  "Your size: X lot · your risk $R · loss at the stop ≈ $L", or why the size is unavailable.
- Tests: tests/test_risk_sizing.py (11), the manager test now checks the fixed stop.
