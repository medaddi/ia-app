"""The Analyse button's two scenarios: each side keeps its strongest trigger (its own test x how close price is x whether it
can fire now), the market context adds its points, and every strategy is compared in one list."""

from app.analysis.drawing import scenario_drawing
from app.analysis.scenarios import build


def trig(fam, id_, d, level, dist, test_r, trades=50, ready=True):
    entry = level
    sl = level - 0.002 if d == "BUY" else level + 0.002
    tp = level + 0.002 if d == "BUY" else level - 0.002
    return {"family": fam, "id": id_, "name": id_, "dir": d, "trigger": f"H1 close beyond {level}", "order": "MARKET", "level": level,
            "entry": entry, "sl": sl, "tp": tp, "rr": 1.0, "distPips": dist, "blockers": [] if ready else ["hours"], "ready": ready,
            "maxHours": 48, "test": {"kind": "t", "trades": trades, "winRate": 60, "totalR": test_r}}


def test_each_side_keeps_its_strongest_trigger_and_context_adds_points():
    ts = [trig("plan", "NEAR", "SELL", 1.105, 5, 10), trig("plan", "FAR", "SELL", 1.12, 200, 20),
          trig("plan", "BUYW", "BUY", 1.09, 10, 2, ready=False), trig("smc", "D", "BUY", 1.095, 8, -8, trades=30)]
    sc = build(ts, {"trend": "bearish", "structure": "bearish", "zone": "premium (70 % of the H1 range)"}, 1.10, 15, 5)
    assert sc["sell"]["main"]["id"] == "NEAR"  # close and proven beats far
    assert sc["bias"] == "SELL" and sc["sellPct"] > 58 and sc["buyPct"] + sc["sellPct"] == 100
    assert all(c["ok"] for c in sc["sell"]["context"]) and not any(c["ok"] for c in sc["buy"]["context"])
    w = {t["id"]: t["weight"] for t in sc["compare"]}
    assert w["NEAR"] > w["FAR"] and w["D"] < w["NEAR"]  # a losing SMC test weighs little
    assert [t["weight"] for t in sc["compare"]] == sorted((t["weight"] for t in sc["compare"]), reverse=True)


def test_a_scenario_drawing_has_its_trigger_entry_stop_and_target():
    t = trig("plan", "X", "BUY", 1.1, 5, 10)
    d = scenario_drawing("EURUSD", {**t, "name": "X"}, 1_790_000_000)
    labels = [l["label"] for l in d["priceLines"]]
    assert labels[0] == "BUY trigger" and "BUY SL" in labels and any(x.startswith("BUY TP") for x in labels)
    assert all(z["id"].startswith("AN-") for z in d["zones"]) and d["tradeExecutionBox"] is None
