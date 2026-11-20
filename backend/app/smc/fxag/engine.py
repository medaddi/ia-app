"""
The engine the app calls (desk.py, the backtest): the zero-lookahead replay of one pair over its candles (scan), the live
read with the 2 agents (report: the Strategy & Confirmation agent and the Risk agent), and the chart's objects (draw_objects). Every evaluation at a close T reads only
candles closed at T (7.3.1).
"""

from datetime import datetime, timezone

from ..playbook import M5S, _make, m5_index_at_close
from .strategy.confluence import engulfing
from .strategy.entry import best_sos, prox
from .strategy.zones import dist_pips
from .config import ENG_TFS, HOLD_DAYS, LIMIT_HOURS, meta
from .pair_actor import TIERS, context, evaluate

STRATEGY_NAME = "FX Alex G Set & Forget"
SETUPS = {"M1": "Full Sync (W + D + 4H)", "M2": "HTF Retracement (W + D, 4H against)", "M3": "Daily Swing / Counter-Weekly (D + 4H)"}
SID = {"M1": "M1", "M2": "M2", "M3": "M3"}
AGENTS = [("strategy", "StrategyAgent", "Agent 1 · strategy & confirmation"), ("risk", "RiskAgent", "Agent 2 · stop loss, take profit & lot")]
RISK_CODES = ("RR_BELOW_MIN", "WEEKLY_TRAP", "SL_TOO_WIDE")  # the Risk agent's vetoes; every other code is the Strategy agent's
SCORE_OF = {"ok": 100, "warn": 60, "wait": 30, "veto": 0}


def news_times(key: str, events) -> list[int]:
    cur = set(meta(key)["currencies"])
    return sorted({int(e["time"]) for e in (events or []) if e.get("currency") in cur})


def fmt(v: float, pip: float) -> str:
    return f"{v:.{2 if pip >= 0.1 else 3 if pip >= 0.01 else 5}f}"


def _engulf_times(cx) -> list[tuple[int, int]]:
    """Every (close time, direction) where a candle of M30 / H1 / H2 / H4 is a clean engulfing (the cheap pre-filter of the replay)."""
    out = set()
    for tf in ENG_TFS:
        st, tc = cx.st[tf], cx.snap[tf].tc
        for j in range(3, len(st.c)):
            for d in (1, -1):
                if engulfing(st.c, j, d, st.atr[j] or 0):
                    out.add((tc[j], d))
    return sorted(out)


def scan(key: str, m5, h1, cost: float, events=None, d_hist=None, spread: float | None = None, follow=None) -> tuple[list, list]:
    """Every clean engulfing close the 2 agents read (both directions) with its plan, its checks, `pass` (approved) and its
    result followed on `follow` (M5 live; the backtest passes H1). Zero look-ahead: each close is evaluated by the same
    `evaluate()` the live read uses, from candles closed at that moment. One trade per pair at a time."""
    follow = follow if follow is not None else m5
    if len(h1) < 300 or len(follow) < 50:
        return [], []
    cx = context(key, m5, h1, d_hist, spread)
    pip = cx.pip
    nw = news_times(key, events) if events is not None else None
    ft = [x.time for x in follow]
    fstep = min(b.time - a.time for a, b in zip(follow[-50:-1], follow[-49:]))
    end = follow[-1].time + fstep
    out, seen = [], set()
    for T, d in _engulf_times(cx):
        if T > end:
            break
        k0 = m5_index_at_close(ft, T)
        if k0 is None or T - (follow[k0].time + fstep) > 3600:
            continue
        r = evaluate(cx, T, d, None, nw)
        if not r.get("candidate"):
            continue
        z, sos, o, cf, cand = r["zone"], r["sos"], r["plan"], r["conf"], r["candidate"]
        approved = r["audit"]["verdict"] == "APPROVE"
        wave = (z["id"], d, sos["time"])
        if (wave, "pass") in seen or (not approved and (wave, cand["entryTf"]) in seen):
            continue
        seen.add((wave, "pass") if approved else (wave, cand["entryTf"]))
        sid = r["align"]["scenario"]
        expiry = 0 if o["market"] else max(1, LIMIT_HOURS * 3600 // fstep)
        miss = None if o["market"] else o["entry"] + d * 0.5 * abs(o["tp"] - o["entry"])  # S07 "missed bus": half way to the TP without a fill
        steps = [(f"W {r['bias']['W']:+d} · D {r['bias']['D']:+d} · 4H {r['bias']['H4']:+d}", True, r["align"]["label"]),
                 (f"At {z['kind']} AOI {fmt(z['lo'], pip)}-{fmt(z['hi'], pip)} ({z['touches']} touches)", True, ""),
                 (f"{sos['tf']} SoS at {fmt(sos['level'], pip)}", True, f"Phi {sos['phi']}"), (f"{cand['entryTf']} Engulfing · {o['model']}", True, o["orderType"]),
                 (f"Score {cf['total']} % (grade {cf['grade']})", cf["grade"] in ("A+", "A", "B+"), ""), (f"R:R {o['rr']:.2f} >= 2.0", o["rr"] >= 2.0, "")]
        s = _make(key, sid, d, follow, k0, o["entry"], o["sl"], None, o["tp"], 1.0, o["market"], expiry, T + HOLD_DAYS * 86400, steps,
                  {"aoi": (z["lo"], z["hi"], z["t0"]), "sos": (sos["level"], sos["time"])}, cost,
                  zone=(o["entry"], o["entry"]), be_off=None, miss_px=miss)
        if not s:
            continue
        s.update(gpa=cf["total"], score=cf["total"], grade=cf["grade"], setupType=sid, riskPct=cand["riskMult"], riskMult=cand["riskMult"], etf=cand["entryTf"],
                 sosTf=cand["sosTf"], orderType=o["orderType"], model=o["model"], confirmedAt=T, fridayExit=False, vetoes=r["audit"]["reasons"],
                 consensus=None, alignmentStrength={"M1": 5, "M2": 5, "M3": 4}[sid], sosInfo=sos, breakdown=cf["breakdown"], detail=cf["detail"],
                 checklistGpa=[{"key": k, "label": f"{k} {cf['detail'].get(k, '')}".strip(), "pts": v, "ok": True} for k, v in cf["breakdown"].items()],
                 zoneInfo={"low": z["lo"], "high": z["hi"], "tfs": sorted(z["tfs"], reverse=True), "kind": z["kind"], "touches": z["touches"],
                           "width": z["width_pips"], "psych": z["psych"], "overlap": z["overlap"]},
                 slPips=cand["slPips"], tpPips=round(abs(o["tp"] - o["entry"]) / pip, 1), target=o["target"], capped=o.get("capped", False),
                 proposal=r["proposal"], audit=r["audit"], newsChecked=nw is not None)
        s["checklist"] = [("1 · Two consecutive HTFs aligned", True, r["align"]["label"]), (f"2 · Grade {cf['grade']} ({cf['total']} %)", cf["grade"] in ("A+", "A", "B+"), ""),
                          ("3 · SoS + clean engulfing", True, f"{sos['tf']} / {cand['entryTf']} · {o['model']}"),
                          (f"4 · R:R >= 2.0 ({o['rr']:.2f})", o["rr"] >= 2.0, o["orderType"]),
                          ("5 · Final gates", approved, ", ".join(r["audit"]["reasons"]) or "APPROVE")]
        s["pass"] = approved
        out.append(s)
    out.sort(key=lambda s: s["time"])
    busy = 0
    for s in out:
        if not s["pass"]:
            continue
        if s["time"] < busy:
            s["pass"] = False
            s["vetoes"] = [*s["vetoes"], "PAIR_LOCKED"]
            s["checklist"].append(("6 · One trade per pair at a time", False, "PAIR_LOCKED"))
            continue
        busy = follow[s["result"]["at"]].time + fstep if "at" in s["result"] else 1 << 62
    return out, []


def _status(r: dict, live: bool) -> dict:
    """The 2 agents' status, badge and lines for one read: (status, badge, lines)."""
    key = r["key"]
    m = meta(key)
    pip, lam, dec = m["pip"], m["lam"], m["decimals"]
    f = lambda v: f"{v:.{dec}f}"  # noqa: E731
    yes = lambda ok: "✅" if ok else "▫️"  # noqa: E731
    al, z, cf, sos, eng, au = r["align"], r.get("zone"), r.get("conf"), r.get("sos"), r.get("engulf"), r.get("audit")
    h = r["health"]
    s_veto = [c for c in ((au or {}).get("reasons", []) + r.get("vetoes", [])) if c not in RISK_CODES]
    lines = [f"{yes(h['ok'])} Data: closed NY-aligned candles" + ("" if h["ok"] else f" · {len(h['gaps'])} H1 gap(s)"),
             f"{yes(r['aligned'])} Trend W {r['bias']['W']:+d} · D {r['bias']['D']:+d} · 4H {r['bias']['H4']:+d}: {al['label']}",
             f"{yes(bool(z) and not r.get('suspended'))} AOI: " +
             (f"{z['kind']} {f(z['lo'])}–{f(z['hi'])} · {z['touches']} touches · {r['zoneDist']:.0f} pips" + (" · BROKEN" if r.get("suspended") else "")
              if z else ("none near" if not r.get("near") else f"nearest {r['near']['kind']} {dist_pips(r['price'], r['near'], pip):.0f} pips")),
             f"{yes(bool(cf) and cf['grade'] in ('A+', 'A', 'B+'))} Score: " + (f"{cf['total']} % · grade {cf['grade']}" if cf else "—"),
             f"{yes(bool(sos))} Shift of structure: " + (f"{sos['tf']} at {f(sos['level'])}" if sos else "awaited (M15 / M30 / H1)"),
             f"{yes(bool(eng))} Engulfing: " + (eng["tf"] if eng else "awaited (H1 / H2 / H4)"),
             f"{yes(bool(au) and not s_veto)} Session, news, spread: " + (", ".join(s_veto) if s_veto else "clear" if au else "checked at the entry")]
    if r.get("suspended") or s_veto:
        st = ("veto", s_veto[0] if s_veto else "AOI broken: wait for the retest")
    elif eng:
        st = ("ok", f"Confirmed {eng['model']}: {sos['tf']} SoS + {eng['tf']} Engulfing · {cf['total']} % ({cf['grade']})")
    elif sos:
        st = ("warn", f"{sos['tf']} SoS at the AOI · engulfing awaited")
    elif r["tier"] == "TIER_1_SNIPER_AOI":
        st = ("warn", f"At the {z['kind']} AOI · {cf['pre']} % · SoS awaited")
    elif r["aligned"]:
        st = ("wait", f"{al['scenario']} {al['label']}" + (" · no AOI in contact" if not z else f" · {r['zoneDist']:.0f} pips from the AOI"))
    else:
        st = ("wait", "HTF_MISALIGNED")
    a = {"strategy": (st[0], st[1], lines)}
    o = r.get("plan")
    if o:
        risk_pct = (r.get("candidate") or {}).get("riskPct")
        slp = o["risk"] / pip
        rl = [f"Order: {o['orderType']} @ {f(o['entry'])}", f"Stop loss: {f(o['sl'])} (-{slp:.1f} pips)",
              f"Take profit: {f(o['tp'])} (+{abs(o['tp'] - o['entry']) / pip:.1f} pips){' · capped before a W AOI' if o['capped'] else ''}",
              f"R:R 1:{o['rr']:.2f} (minimum 2.0)", f"Risk {risk_pct}% (season x grade) · lot = your $ risk / ({slp:.1f} pips x pip value)",
              f"Lot for $100: {lots_for(100, slp, m)}"]
        if o["trap"]:
            a["risk"] = ("veto", "W-AOI trap: runway < 2 x SL", rl)
        else:
            a["risk"] = ("ok", f"SL {f(o['sl'])} · TP {f(o['tp'])} · 1:{o['rr']:.2f}", rl)
    elif r.get("reject"):
        a["risk"] = ("veto", "R:R under 2.0" if r["reject"] == "RR_BELOW_MIN" else r["reject"], [])
    else:
        a["risk"] = ("ok", "SET & FORGET LOCKED (signal)", []) if live else ("wait", "Waits for the strategy agent's confirmation", [])
    return a


def lots_for(usd: float, sl_pips: float, m: dict) -> float:
    from .risk.levels import lots
    return lots(usd, sl_pips, m["pip_value_usd_per_lot"], m["min_lot"], m["max_lot"], m["lot_step"])


def report(key: str, m5, h1, now: int, setups: list, news_events, d_hist=None, spread: float | None = None) -> dict:
    """The pair's read now: both directions at the last close, the most advanced one (tier, then score) shown; a live
    approved trade is shown as SET & FORGET LOCKED."""
    cx = context(key, m5, h1, d_hist, spread)
    nw = news_times(key, news_events) if news_events is not None else None
    T = m5[-1].time + M5S
    P = m5[-1].close
    live = [s for s in setups if s["pass"] and s["result"]["state"] in ("PENDING", "ACTIVE")]
    cand = live[-1] if live else None
    reads = [evaluate(cx, T, d, P, nw) for d in (1, -1)]
    r = max(reads, key=lambda q: (q["aligned"], TIERS.index(q["tier"]), (q["conf"] or {}).get("total", 0)))
    if cand:
        r2 = evaluate(cx, cand["confirmedAt"], cand["dir"], None, nw)
        if r2.get("candidate"):
            r = r2
    r["key"], r["newsChecked"] = key, nw is not None
    ag = _status(r, bool(cand))
    agents = [{"key": k, "id": name, "name": name, "role": role, "status": ag[k][0], "finding": ag[k][1], "badge": ag[k][1],
               "score": SCORE_OF[ag[k][0]], "weight": 0.5, "lines": ag[k][2], "details": ag[k][2]} for k, name, role in AGENTS]
    d = r["dir"]
    cf = r.get("conf") or {"total": 0, "grade": "D", "breakdown": {}}
    tier = "SET_AND_FORGET_LOCKED" if cand else r["tier"]
    decision = "EXECUTE" if cand else ("VETOED" if r.get("audit") and r["audit"]["verdict"] == "VETO" or r.get("reject") else
                                       "WAIT_FOR_TRIGGER" if r["tier"].startswith("TIER_1") or r["tier"] == "AWAIT_PULLBACK_LIMIT" else "WATCH_ONLY")
    contract = {"pair": cx.m["symbol"], "strategy_name": STRATEGY_NAME, "setup_type": r["align"]["scenario"] if r["aligned"] else None,
                "timestamp_utc": datetime.fromtimestamp(T, timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"), "direction": "BUY" if d > 0 else "SELL",
                "tier": tier, "alignment": r["align"], "consensus_score": round(sum(a["score"] for a in agents) / len(agents)),
                "gpa_score": cf["total"], "grade": cf["grade"], "final_decision": decision, "pass": bool(cand),
                "checklist": [{"key": k, "label": k, "pts": v, "ok": True} for k, v in cf["breakdown"].items()], "agents": ag}
    return {"contract": contract, "agents": agents, "execute": bool(cand), "candidate": cand, "radar": None, "read": r, "tier": tier}


def draw_objects(key: str, m5, h1, now: int, r_fn=round, d_hist=None, spread=None, focus: dict | None = None) -> dict:
    """The chart: the AOI in play (or the nearest above and below the price) and the D structure levels always; the
    other AOIs, the 500 levels, the 4H levels, the HH / HL markers and the latest LTF SoS line under "Details"."""
    cx = context(key, m5, h1, d_hist, spread)
    pip = cx.pip
    idx = cx.idx(now)
    end = m5[-1].time + M5S
    px = m5[-1].close
    zs = sorted(cx.zones(idx, False), key=lambda z: abs((z["lo"] + z["hi"]) / 2 - px))[:8] if idx["W"] >= 0 and idx["D"] >= 0 else []
    if focus:
        main = [focus]
        if not any(z["id"] == focus["id"] for z in zs):
            zs = [focus, *zs]
    else:
        below, above = [z for z in zs if z["hi"] < px], [z for z in zs if z["lo"] > px]
        main = [z for z in zs if z["lo"] <= px <= z["hi"]][:1] + below[:1] + above[:1]
    ids = {z["id"] for z in main}
    boxes, segs, labels = [], [], []
    for z in zs:
        tfl = {"W": "1W", "D": "1D", "H4": "4H", "W+D": "1W/1D"}[z["kind"]]
        boxes.append({"from": z["t0"], "to": end + 6 * 3600, "top": r_fn(z["hi"]), "bottom": r_fn(z["lo"]), "kind": "ob", "dir": 1 if z["hi"] < px else -1,
                      "label": f"{tfl} zone · {z['touches']} touches"[:24], "detail": z["id"] not in ids})
        if z["psych"] is not None:
            segs.append({"from": z["t0"], "to": end, "price": r_fn(z["psych"]), "kind": "eq", "dir": 0, "label": f"500 {fmt(z['psych'], pip)}", "detail": True})
    for tf in ("D", "H4"):
        st, i = cx.st[tf], idx[tf]
        if i < 0:
            continue
        names = (("HH", st.hh, 1), ("HL", st.hl, -1)) if st.bias[i] >= 0 else (("LH", st.lh, 1), ("LL", st.ll, -1))
        for name, arr, dirn in names:
            lv = arr[i]
            if lv and lv[1] >= i - 150:
                t0 = cx.snap[tf].t[lv[1]]
                segs.append({"from": t0, "to": end, "price": r_fn(lv[0]), "kind": "liquidity", "dir": dirn,
                             "label": f"{'1D' if tf == 'D' else '4H'} {name}", "detail": tf != "D"})
                labels.append({"time": t0, "price": r_fn(lv[0]), "text": name, "above": dirn > 0, "kind": "structure", "detail": True})
    for d in (1, -1):
        for z in main:
            s = best_sos(cx.st, end, z, d, prox(cx.st["H1"], idx["H1"], pip, cx.lam))
            if s:
                segs.append({"from": s["time"] - 6 * 3600, "to": end, "price": r_fn(s["level"]), "kind": "bos", "dir": d, "label": f"{s['tf']} SoS", "detail": True})
                break
    return {"boxes": boxes, "segments": segs, "labels": labels, "lines": []}
