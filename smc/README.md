# smc/ — research for the strategy

The strategy the app runs lives in `backend/app/smc/fxag/` (FX Alex G Set & Forget, v2 blueprint). This folder only holds
what is used to test it on history and the reports. **Not financial advice; the app sends signals, it never places an order.**

| File | What it is |
|---|---|
| `tools/playbook_test.py` | backtest on the app's feed (H1 2 years, D1 5 years) → writes `PLAYBOOK.md` and `backend/app/smc/research/playbook.json` (the numbers the app shows) |
| `news/high_impact.csv` | stored high-impact news calendar, used by the backtest's news blackout |
| `PLAYBOOK.md` | the last backtest |
| `FXAG_V2_REPORT.md` | the v2 blueprint's gates: measured results, what passes and what does not |
| `CHANGELOG.md` | every version of the strategy, newest first |

```bash
# from the repository root, with the backend's virtual environment
PYTHONPATH=. backend/.venv/Scripts/python smc/tools/playbook_test.py feed
PYTHONPATH=. backend/.venv/Scripts/python smc/tools/playbook_test.py feed CACHE.pkl   # from saved candles
```
