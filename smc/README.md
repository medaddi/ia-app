# SMC research: one team per pair

Educational research and backtesting of Smart Money Concepts rules on XAU/USD, EUR/USD, GBP/USD, EUR/CHF, AUD/CAD and
AUD/CHF. **Not financial advice, no signals, no orders, no broker connection.** Demo testing before any live use; live use
is the account owner's decision.

## Read first
- `SUMMARY.md`: the six pairs side by side.
- `DATA_QUALITY.md`: whether each pair's candles can be trusted (most cannot, see below).
- `pairs/<PAIR>/TEAM_REPORT.md`: each team's document (summary, rule book with its config, backtest, journal, open questions).
- `RULEBOOK.md` (BUY / SELL, S1–S4, the 7 questions) and `DEFINITIONS.md` (every term, every interpretation flagged).
- `JOURNAL_TEMPLATE.md`, `journal_template.csv`, `WEEKLY_REVIEW.md`, `CHANGELOG.md`.

## The teams in the app
Each pair's team runs live (backend `app/smc/`): every minute it reads the pair's closed M5 / H1 candles with this same
engine. Its seven agents report on the chart page: Lead Strategist, Structure, Liquidity & Session, Entry, Risk,
Backtest Engineer and Devil's Advocate. A setup that passes its rules and the 7 questions is drawn on the chart and sent
once to Telegram and phone notifications. `python -m smc.tools.bundle` copies the backtest summaries the Backtest
Engineer quotes. Research, not advice: nothing is guaranteed.

## Two limits to know
1. **The 10-episode masterclass script was not provided.** The rules come from the brief's summary of it (SCRIPT (brief))
   or are team interpretations. They must be checked against the script.
2. **The data is not good enough to conclude anything.** Yahoo Finance gives only ~70 days of M5. Its EUR/USD and GBP/USD
   M5 candles fail the quality check (sampled quotes, opening jumps), and the crosses look synthetic. Only gold's M5 passes,
   and no strategy reaches 100 trades on any pair.

## Run it (from the repository root, with the backend's Python: `backend/.venv/Scripts/python` on Windows)
```bash
python smc/tools/fetch_data.py          # download and check the candles (Yahoo) into smc/pairs/<PAIR>/data/
python -m smc.tools.data_quality        # DATA_QUALITY.md + pairs/<PAIR>/quality.json
python -m smc.engine.backtest           # S1–S4 per pair: trades.csv + results.json
python -m smc.tools.report              # TEAM_REPORT.md per pair + SUMMARY.md
python -m pytest smc/tests -q           # the rules and the no-look-ahead test
```
Better data: put CSVs with the same columns (`time` = UTC unix seconds of the candle open, `open, high, low, close, volume`)
in `smc/pairs/<PAIR>/data/` (M5.csv and H1.csv are required), then run the last four commands.
News: `smc/news/high_impact.csv` with a `time_utc` column (ISO time) turns on the news gate.

## Layout
```
smc/engine/smc.py        shared engine: structure, liquidity, FVG, OB, S1–S4, the 7-question checklist
smc/engine/manage.py     management variant: 50 % at 1:3, break-even after an M5 BOS
smc/engine/backtest.py   in-sample / out-of-sample split, metrics, random baseline, trades.csv
smc/pairs/<PAIR>/        config.json, data/, trades.csv, results.json, quality.json, TEAM_REPORT.md
smc/tools/               fetch_data, data_quality, report, make_configs
smc/tests/               rule tests and the no-look-ahead test
```
