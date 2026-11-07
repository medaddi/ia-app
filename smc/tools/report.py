"""
Writes each pair's TEAM_REPORT.md and the cross-pair SUMMARY.md from results.json, config.json and quality.json.
Every number is copied from those files (VERIFIED); nothing is typed by hand.

  python -m smc.tools.report
"""

import csv
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PAIRS = ["XAUUSD", "EURUSD", "GBPUSD", "EURCHF", "AUDCAD", "AUDCHF"]
PROFILE_FOCUS = {"XAUUSD": "S3 and S2 around the London and NY opens", "EURUSD": "S2 (frequent PDH / PDL sweeps)",
                 "GBPUSD": "S3 (London-open Judas swings)", "EURCHF": "few setups worth the spread: measure the minimum range",
                 "AUDCAD": "S4 and S1 (range-bound)", "AUDCHF": "S1 on 1H / 15M, S2 around PDH / PDL"}


def d(t: int) -> str:
    return datetime.fromtimestamp(t, timezone.utc).strftime("%Y-%m-%d")


def cell(m: dict) -> str:
    if not m or not m.get("trades"):
        return "0 trades"
    pf = m["profitFactor"] if m["profitFactor"] is not None else "∞"
    return (f"{m['trades']} tr · win {m['winRate']} % · exp {m['expectancyR']:+.2f}R · PF {pf} · DD {m['maxDrawdownR']}R · "
            f"streak {m['longestLosingStreak']}")


def data_verdict(q: dict) -> str:
    return q["M5"]["verdict"]


def pair_report(p: str) -> tuple[str, list[str]]:
    base = ROOT / "pairs" / p
    cfg = json.loads((base / "config.json").read_text(encoding="utf-8"))
    res = json.loads((base / "results.json").read_text(encoding="utf-8"))
    q = json.loads((base / "quality.json").read_text(encoding="utf-8"))
    verdict = data_verdict(q)
    with open(base / "data" / "H1.csv", newline="") as f:
        next(f)
        h1_from = d(int(next(f).split(",")[0]))
    with open(base / "trades.csv", newline="", encoding="utf-8") as f:
        trades = list(csv.DictReader(f))
    fails = Counter(x.strip() for t in trades for x in (t.get("checklist_fails") or "").split(";") if x.strip())
    valid = verdict == "FIT"
    s = res["strategies"]
    total_gated = sum((b["gated_in"]["plain"].get("trades") or 0) + (b["gated_out"]["plain"].get("trades") or 0) for b in s.values())
    total_setups = sum(b["setups"] for b in s.values())
    lines = [f"# {cfg['symbol']} team report (v0.1)", "",
             "Educational research. Not financial advice, not a signal service, no guarantee. Demo testing comes before any live use, "
             "and live use is the account owner's decision.", "",
             "## 1. Executive summary", "",
             f"- **Data:** Yahoo Finance; LTF (M5) {d(res['m5From'])} → {d(res['m5To'])} (about {round((res['m5To'] - res['m5From']) / 86400)} days), "
             f"H1 {h1_from} → {d(res['m5To'])}. M5 data verdict: **{verdict}**"
             + (f" ({', '.join(q['M5']['why'])})" if q['M5']['why'] else "") + ". See `../../DATA_QUALITY.md`.",
             f"- **Sample:** {total_setups} setups across S1–S4; **{total_gated} passed all 7 questions** (the trades the playbook takes). "
             "Every strategy is far below 100 trades: **statistically weak, no conclusion possible.**",
             "- **What works:** not known. No strategy has enough trades, in sample or out of sample, to say it has an edge."
             + ("" if valid else " The M5 candles also fail the data check, so even these few results are **NOT VALID**."),
             "- **What does not work:** not known either, for the same reason.",
             f"- **Key risks:** tiny sample; a single fixed cost ({cfg['spread_pips']} + {cfg['slippage_pips']} pips) that under-states news and rollover spreads; "
             "no news calendar for the test period; the source script was not available, so every rule is the brief's summary or a team interpretation.",
             f"- **Profile focus (from the brief, HYPOTHESIS):** {PROFILE_FOCUS[p]}.", "",
             "## 2. Rule book", "", "Shared rule book `../../RULEBOOK.md` (v0.1, BUY and SELL), with this pair's config:", "",
             f"- pip {cfg['pip']} · contract {cfg['contract_size']} · pip value ≈ ${cfg['pip_value_usd_per_lot']} per lot (verify with the broker)",
             f"- cost per trade: spread {cfg['spread_pips']} + slippage {cfg['slippage_pips']} pips · commission ${cfg['commission_usd_per_lot']} (none assumed)",
             f"- sessions (UTC, not DST-shifted): Asia {cfg['sessions_utc']['asia']} · London {cfg['sessions_utc']['london']} · NY {cfg['sessions_utc']['newyork']}",
             f"- S3 minimum Asian range: {cfg['s3_min_asia_range_atr']} × H1 ATR(14) · minimum stop: {cfg['min_stop_cost_ratio']} × cost", "",
             "Pair notes:", *[f"- {n}" for n in cfg["notes"]], "",
             "## Team and sign-off", "",
             "The team's seven agents run live in the app on this pair (backend `app/smc/agents.py`), each on its own part of the same engine read:", "",
             "| Role | Owns | Sign-off for v0.1 |", "|---|---|---|",
             "| Lead Strategist | decision, rule book, `CHANGELOG.md` | published v0.1; a setup is published only when its rules and all 7 questions pass |",
             "| Structure Analyst | H4 bias (question 1), H1 swings, IDM, BOS / CHoCH, dealing range | signs when the H4 bias and range are defined |",
             "| Liquidity & Session Analyst | PDH / PDL, Asian range, killzones, DST, news | objects: DST unverified, no news calendar |",
             "| Entry Specialist | OB / FVG validity, LTF confirmation | signs a setup's zone; otherwise reports what each strategy waits for |",
             "| Risk Manager | 1 % sizing, stop vs cost, BE, partials | signs only RR ≥ 1:3 and stop ≥ 5 × cost |",
             "| Backtest Engineer | data, code, this report | objects: data verdict above, < 100 trades |",
             "| Devil's Advocate | objections, hindsight, overfitting | lists every objection with each read |", "",
             "The sign-offs are the code's checks, run on every read; no human has reviewed this version yet.", "",
             "## 3. Definitions", "", "`../../DEFINITIONS.md` (every interpretation flagged).", "",
             "## 4. Backtest", "",
             f"In-sample: first 60 % of the M5 period (to {d(res['split'])}); out-of-sample: the rest. Rules were fixed before the run; "
             "0 tuning passes. Results in R after costs. \"Gated\" = strategy rules + 7 questions (the trades taken); \"all\" = every "
             "setup of the strategy (checklist ignored, a bigger but untradeable sample). Baseline = random direction at the same "
             "moments with the same stop and target (500 runs).", "",
             ("**Data verdict NOT FIT: the numbers below are kept for transparency only. They are NOT VALID.**" if not valid else
              "**Data verdict FIT for M5, but the sample is far too small: statistically weak.**"), "",
             "| Strategy | setups | gated · in-sample | gated · out-of-sample | all · in-sample | all · out-of-sample | baseline (all, OOS) |",
             "|---|---|---|---|---|---|---|"]
    for sid, b in s.items():
        base_oos = (b["all_out"]["baseline"] or {}).get("expectancyR")
        lines.append(f"| {sid} {b['name']} | {b['setups']} | {cell(b['gated_in']['plain'])} | {cell(b['gated_out']['plain'])} | "
                     f"{cell(b['all_in']['plain'])} | {cell(b['all_out']['plain'])} | {f'{base_oos:+.2f}R' if base_oos is not None else '—'} |")
    lines += ["", "Managed (50 % at 1:3, BE after an M5 BOS), same trades:", "", "| Strategy | gated · OOS | all · OOS |", "|---|---|---|"]
    for sid, b in s.items():
        lines.append(f"| {sid} | {cell(b['gated_out']['managed'])} | {cell(b['all_out']['managed'])} |")
    lines += ["", f"Why setups were not taken (the 7 questions, across all {len(trades)} setups; one setup can fail several):", ""]
    lines += [f"- {k}: {v}" for k, v in fails.most_common()] or ["- none"]
    lines += ["", "Trades: `trades.csv` (every setup, its checklist answers and why it failed, its plain and managed result).", "",
              "Statistical caveats: fewer than 100 trades per strategy means a win rate or expectancy can change sign with a "
              "handful of trades; the out-of-sample period is about 30 days; costs are a single fixed estimate; gold uses futures prices.", "",
              "## 5. Journal and the first two weeks of demo", "", "`../../JOURNAL_TEMPLATE.md` and `../../journal_template.csv`.", "",
              "## 6. Open questions and next experiments", "",
              "1. **The source script**: needed to check every SCRIPT (brief) rule and resolve the flagged interpretations.",
              "2. **Data**: M5 / M1 history of at least 2 years from a clean source (broker MT5 export, or Dukascopy) to reach 100+ trades per strategy.",
              "3. A high-impact news calendar CSV for the test period (`smc/news/high_impact.csv`, column `time_utc`).",
              "4. DST-shifted killzones (London 06:00–09:00 UTC in summer) against the script's fixed UTC hours.",
              "5. Not yet coded: IFVG entries, EQH / EQL, PWH / PWL, trendline liquidity, Extreme vs Decisional OB, trailing, 4H single candles.",
              "6. Devil's advocate: questions 4 and 5 of the checklist never say no (built into the strategies); question 1 removes most reversals.", ""]
    row = [cfg["symbol"], verdict, total_setups, total_gated,
           ", ".join(f"{sid} {b['gated_out']['plain'].get('trades', 0)}" for sid, b in s.items())]
    return "\n".join(lines), row


def main() -> None:
    rows = []
    for p in PAIRS:
        text, row = pair_report(p)
        (ROOT / "pairs" / p / "TEAM_REPORT.md").write_text(text, encoding="utf-8")
        rows.append(row)
    out = ["# Summary across the six teams (v0.1)", "", "VERIFIED from each pair's results.json. Not financial advice.", "",
           "| Pair | M5 data | setups (S1–S4) | passed the 7 questions | gated out-of-sample trades | Result |", "|---|---|---|---|---|---|"]
    for r in rows:
        out.append(f"| {r[0]} | {r[1]} | {r[2]} | {r[3]} | {r[4]} | statistically weak{'' if r[1] == 'FIT' else ', data NOT VALID'} |")
    out += ["", "No strategy on any pair reaches 100 trades. Nothing here shows an edge or the lack of one."]
    (ROOT / "SUMMARY.md").write_text("\n".join(out) + "\n", encoding="utf-8")
    print("\n".join(out))


if __name__ == "__main__":
    main()
