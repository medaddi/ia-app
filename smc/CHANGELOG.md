# Changelog

## v0.1 · 2026-11-05
- First version of the shared engine (`engine/smc.py`), taken from the app's SMC engine (git c262bdc), reduced to the
  brief's four strategies (S1 = A, S2 = B, S3 = D, S4 = E; the supply / demand flip strategy C dropped) and made
  configurable (sessions, news window, minimum Asian range, minimum stop / cost).
- Added the managed simulation (50 % at 1:3, BE after an M5 BOS) and the random-direction baseline.
- Data: Yahoo Finance, fetched 2026-11-05 (`tools/fetch_data.py`), checked by `tools/data_quality.py`.
- Parameter changes after seeing results: **none.** Tuning passes: 0.
