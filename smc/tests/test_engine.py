"""
The engine's rules, and the proof that no setup uses the future.
  python -m pytest smc/tests -q        (from the repository root)
"""

import json
from pathlib import Path

import pytest

from smc.engine import smc
from smc.engine.candles import Candle, load

ROOT = Path(__file__).resolve().parents[1]
H1S, M5S = 3600, 300


def bars(rows, t0=1_700_000_000, step=M5S):
    return [Candle(t0 + k * step, o, h, l, c) for k, (o, h, l, c) in enumerate(rows)]


# ---------------------------------------------------------------- the rules, one by one
def test_a_swing_high_needs_a_candle_breaking_the_mother_candles_low():
    # up leg to 1.10 (candle 2 = mother), candle 3 is an inside bar, candle 4 trades below the mother's low
    c = bars([(1.00, 1.05, 0.99, 1.04), (1.04, 1.08, 1.03, 1.07), (1.07, 1.10, 1.06, 1.09),
              (1.09, 1.095, 1.065, 1.08), (1.08, 1.085, 1.05, 1.06)])
    sh, sl, at = smc.pullback_swings(c)
    assert sh[2] == 1.10
    confirming = [i for i, ev in at.items() if ("H", 2) in ev]
    assert confirming == [4]  # the inside bar (3) did not confirm it, the break of the mother's low (4) did


def test_a_wick_beyond_a_swing_is_a_sweep_and_only_a_body_close_is_a_bos():
    c = bars([(1.00, 1.05, 0.99, 1.04), (1.04, 1.10, 1.03, 1.07), (1.07, 1.08, 1.02, 1.03),  # swing high 1.10 confirmed at 2
              (1.03, 1.11, 1.02, 1.05),  # wick to 1.11, close back below: SWEEP
              (1.05, 1.13, 1.04, 1.12)])  # body close above the new wick tip 1.11: BOS / CHoCH
    st = smc.Structure(c)
    assert any(e[0] == "SWEEP" and e[1] == 1 for e in st.ev[3]) and not st.breaks(3, 1)
    assert st.breaks(4, 1)


def test_fvg_is_the_three_candle_gap():
    c = bars([(1.00, 1.01, 0.99, 1.005), (1.005, 1.03, 1.004, 1.028), (1.028, 1.04, 1.015, 1.035)])
    f = smc.fvgs(c)
    assert f[2] == (1, 1.01, 1.015)  # candle 1 high 1.01 below candle 3 low 1.015


def test_the_checklist_has_seven_questions_and_any_no_blocks():
    m5 = load(ROOT / "pairs" / "EURUSD" / "data" / "M5.csv")
    h1 = load(ROOT / "pairs" / "EURUSD" / "data" / "H1.csv")
    res = smc.scan_all(m5, h1, 0.00012, 5)
    every = [s for sid in ("S1", "S2", "S3", "S4") for s in res[sid]["setups"]]
    assert every, "the data gives at least one setup"
    for s in every:
        assert len(s["checklist"]) == 7 and s["pass"] == all(ok for _, ok, _ in s["checklist"])


# ---------------------------------------------------------------- no look-ahead
@pytest.mark.parametrize("pair", ["EURUSD", "XAUUSD"])
def test_setups_do_not_change_when_future_data_is_removed_or_changed(pair):
    """Cut the data at several moments: every setup dated before the cut is identical with and without the future,
    and with the future replaced by nonsense. Its result (which needs the future) is not compared."""
    d = ROOT / "pairs" / pair
    cfg = json.loads((d / "config.json").read_text(encoding="utf-8"))
    smc.configure(cfg, [])
    m5, h1 = load(d / "data" / "M5.csv"), load(d / "data" / "H1.csv")
    cost = (cfg["spread_pips"] + cfg["slippage_pips"]) * cfg["pip"]
    full = smc.scan_all(m5, h1, cost, cfg["decimals"])
    key = lambda s: (s["sid"], s["time"], s["dir"], round(s["entry"], 6), round(s["sl"], 6), round(s["tp"], 6), s["pass"])  # noqa: E731
    for frac in (0.35, 0.6, 0.85):
        cut = m5[int(len(m5) * frac)].time
        m5c = [x for x in m5 if x.time + M5S <= cut]
        h1c = [x for x in h1 if x.time + H1S <= cut]
        # the future replaced by candles that drift far away: a look-ahead would change the past setups
        last = m5c[-1].close
        fake = [Candle(m5c[-1].time + (k + 1) * M5S, last * (1 + 0.002 * k), last * (1 + 0.002 * k + 0.001), last * (1 + 0.002 * k - 0.001),
                       last * (1 + 0.002 * (k + 1))) for k in range(200)]
        for m5x, h1x in ((m5c, h1c), (m5c + fake, h1c)):
            cutres = smc.scan_all(m5x, h1x, cost, cfg["decimals"])
            # the setups known at the cut: those whose last needed candle closed before it, minus the ones still being
            # decided at the very edge (an S3 / S2 sweep near the cut may get its confirmation later)
            edge = cut - 3 * H1S
            past_full = {key(s) for sid in ("S1", "S2", "S3", "S4") for s in full[sid]["setups"] if s["time"] <= edge}
            past_cut = {key(s) for sid in ("S1", "S2", "S3", "S4") for s in cutres[sid]["setups"] if s["time"] <= edge}
            assert past_full == past_cut, f"{pair} cut {frac}: setups before the cut changed when the future changed"
