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
