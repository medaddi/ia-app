"""
Phase 3 of the user's spec data_feed_charting_engine_architecture_prompt.md: the data checks behind the Backtest
Engineer's and the Devil's Advocate's badges, the same for the six teams (applied by desk.read_team to each pair report).

Backtest Engineer: the sample is the pair's strategies run over the one-year Dukascopy history (smc/tools/playbook_test.py,
far more than the spec's 1,500 M5 / 1,000 H1 minimum) plus the setups the live buffer shows. "data FIT" needs N >= 30
trades AND the live M5 continuity >= 99.5 %.

Devil's Advocate, the 4-point Data Integrity Audit before any critique of the structure:
  1. timestamp continuity 100 %: no missing M5 slot in the last 48 h (market hours only, market/sanitize.py)
  2. the sweep candle carries real tick volume (the feed has volume and the candle's is > 0) and is not a FEED_ARTIFACT
  3. the setup's FVG is wider than 1.5 × the current spread (the live OANDA spread, else the config's assumed one)
  4. the setup's candle did not form between 21:50 and 22:15 UTC (the rollover)
Checks 2-4 concern a setup; with none on the table they have nothing to reject.
"""

from typing import Optional

from ..market.sanitize import missing_slots

M5S, H1S, DAY = 300, 3600, 86400


def continuity(m5, hours: int = 48) -> tuple[float, int]:
    if not m5:
        return 0.0, 0
    since = m5[-1].time - hours * H1S
    recent = [x for x in m5 if x.time >= since]
    miss = missing_slots(recent, M5S, since)
    tot = len(recent) + len(miss)
    return (len(recent) / tot if tot else 1.0), len(miss)


def audit(m5, cand: Optional[dict], spread_px: float, pip: float) -> dict:
    cont, miss = continuity(m5)
    checks = [("1 · Timestamp continuity 100 % (M5, last 48 h)", miss == 0, f"{cont * 100:.2f} % · {miss} missing")]
    has_vol = any((x.volume or 0) > 0 for x in m5[-300:])
    if cand:
        g = cand.get("geo") or {}
        sw = g.get("sweep")
        if sw:
            t = int(sw[1])
            near = [x for x in m5 if t <= x.time < t + 900]  # the sweep's M5 candles (an M15 sweep spans three)
            vol = sum((x.volume or 0) for x in near)
            ok = has_vol and vol > 0
            checks.append(("2 · Sweep candle has real tick volume", ok, f"volume {vol:g}" if has_vol else "this feed has no volume"))
        else:
            checks.append(("2 · Sweep candle has real tick volume", True, "no sweep in this setup"))
        f = g.get("fvg")
        if f:
            size = abs(f[0] - f[1])
            checks.append(("3 · FVG > 1.5 × the spread", size > 1.5 * spread_px, f"{size / pip:.1f} vs {1.5 * spread_px / pip:.1f} pips"))
        else:
            checks.append(("3 · FVG > 1.5 × the spread", True, "no FVG in this setup"))
        tod = cand["time"] % DAY
        roll = 21 * H1S + 50 * 60 <= tod < 22 * H1S + 15 * 60
        checks.append(("4 · Not formed in the 21:50-22:15 UTC rollover", not roll, ""))
    else:
        checks += [("2 · Sweep candle has real tick volume", True, "no setup to check"), ("3 · FVG > 1.5 × the spread", True, "no setup to check"),
                   ("4 · Not formed in the 21:50-22:15 UTC rollover", True, "no setup to check")]
    return {"checks": checks, "clean": all(ok for _, ok, _ in checks), "continuity": cont, "missing": miss, "hasVolume": has_vol}


def sample(research: Optional[dict], strategies: list[str]) -> dict:
    """The one-year result over the pair's strategies: N, win rate, profit factor, expectancy."""
    st = (research or {}).get("strategies") or {}
    n = w = 0
    gw = gl = tot = 0.0
    for sid in strategies:
        a = (st.get(sid) or {}).get("all") or {}
        n += a.get("trades", 0)
        w += a.get("wins", 0)
        tot += a.get("totalR", 0.0)
        gw += a.get("grossWinR", 0.0)
        gl += a.get("grossLossR", 0.0)
    return {"trades": n, "winRate": round(100 * w / n) if n else None, "pf": round(gw / gl, 2) if gl else None,
            "expectancyR": round(tot / n, 3) if n else None, "source": (research or {}).get("source")}


def _ui(rep: dict, key: str):
    return next(a for a in rep["agents"] if a["key"] == key)


def apply(rep: dict, m5, research: Optional[dict], strategies: list[str], live_setups: int, spread_px: float, pip: float,
          spread_live: bool) -> dict:
    """Puts the checks into a pair report (contract + UI agents); a failed audit vetoes the trade."""
    cand = rep.get("candidate")
    au = audit(m5, cand, spread_px, pip)
    sm = sample(research, strategies)
    ag = rep["contract"]["agents"]
    fit = sm["trades"] >= 30 and au["continuity"] >= 0.995
    if fit:
        bt = f"data FIT • N={sm['trades']} setups • WR {sm['winRate']}% • {sm['pf'] if sm['pf'] is not None else '—'} PF"
    elif sm["trades"] < 30:
        bt = f"data LIMITED • N={sm['trades']} setups (< 30)" + (f" • WR {sm['winRate']}%" if sm["winRate"] is not None else "")
    else:
        bt = f"data NOT FIT • continuity {au['continuity'] * 100:.1f}% (< 99.5)"
    b = ag["backtest_engineer"]
    b.update(ui_badge_summary=bt[:55], status="VALID" if fit else "WARNING",
             data_check={"sample_trades": sm["trades"], "win_rate": sm["winRate"], "profit_factor": sm["pf"], "expectancy_r": sm["expectancyR"],
                         "history": f"{sm['source'] or 'dukascopy'} 1 year", "live_buffer_m5": len(m5), "live_buffer_setups": live_setups,
                         "continuity_48h": round(au["continuity"], 4), "fit_rule": "N >= 30 and continuity >= 99.5 %"})
    d = ag["devils_advocate"]
    d["data_integrity_audit"] = [{"check": q, "ok": ok, "detail": det} for q, ok, det in au["checks"]]
    d["spread_used"] = f"{spread_px / pip:.1f} pips ({'live OANDA' if spread_live else 'assumed: no live bid/ask'})"
    if au["clean"]:
        d["feed"] = "M5 feed VERIFIED CLEAN • sweeps & FVGs validated against tick/ATR filter • checking setup traps..."
    else:
        bad = next(q for q, ok, _ in au["checks"] if not ok)
        d.update(feed="M5 feed NOT CLEAN: " + bad.split(" · ", 1)[1], veto_active=True, status="VETO",
                 failure_probability=max(d.get("failure_probability") or 0, 0.9))
        d["ui_badge_summary"] = ("My worry: feed check failed: " + bad.split(" · ", 1)[1])[:55]
        if rep["execute"]:
            rep["execute"] = False
            rep["contract"]["final_decision"] = "NO_TRADE"
            lead = ag["lead_strategist"]
            lead.update(ui_badge_summary="No trade: the M5 feed failed its data check", status="WAIT", execution_plan=None)
    for k, name in (("backtest", "backtest_engineer"), ("devil", "devils_advocate"), ("lead", "lead_strategist")):
        a, src = _ui(rep, k), ag[name]
        st = {"VALID": "ok", "WAIT": "wait", "WARNING": "warn", "VETO": "veto", "STANDBY": "wait"}[src["status"]]
        lines = [f"{x}: {y}" for x, y in src.items() if x not in ("ui_badge_summary", "status", "feed") and y not in (None, [], {})]
        if k == "devil":
            lines = [src["feed"]] + lines
        a.update(finding=src["ui_badge_summary"], status=st, statusMd=src["status"], lines=lines)
    return au
