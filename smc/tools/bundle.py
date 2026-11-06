"""
Copies each pair's research summary (backtest results + data verdict) into the live app, so the pair's Backtest Engineer
quotes them: backend/app/smc/research/<PAIR>.json. VERIFIED numbers only (from results.json and quality.json).

  python -m smc.tools.bundle        (after the backtest and the data check)
"""

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT.parent / "backend" / "app" / "smc" / "research"
PAIRS = ["XAUUSD", "EURUSD", "GBPUSD", "EURCHF", "AUDCAD", "AUDCHF"]


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    for p in PAIRS:
        d = ROOT / "pairs" / p
        if not (d / "results.json").exists():
            continue
        res = json.loads((d / "results.json").read_text(encoding="utf-8"))
        q = json.loads((d / "quality.json").read_text(encoding="utf-8")) if (d / "quality.json").exists() else {}
        out = {"pair": p, "m5From": res["m5From"], "m5To": res["m5To"], "split": res["split"],
               "data": {tf: {"verdict": v.get("verdict"), "why": v.get("why", [])} for tf, v in q.items()},
               "strategies": {sid: {"setups": b["setups"], "gatedIn": b["gated_in"]["plain"], "gatedOut": b["gated_out"]["plain"],
                                    "allIn": b["all_in"]["plain"], "allOut": b["all_out"]["plain"],
                                    "baselineOut": (b["all_out"].get("baseline") or {}).get("expectancyR")}
                              for sid, b in res["strategies"].items()}}
        (OUT / f"{p}.json").write_text(json.dumps(out, indent=1), encoding="utf-8")
        print(p, "bundled")


if __name__ == "__main__":
    main()
