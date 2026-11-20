"""
The PairActor (blueprint step 1 and 5): one pair, isolated (it reads only its own candles), as a state machine whose state is
DERIVED from the closed candles at every read (a restart can never lose or invent a state). `evaluate()` is the ONE pure
function behind both the backtest (engine.scan) and the live read (engine.live): nothing is duplicated.

  TIER_3_DORMANT        W / D / 4H misaligned (M4), a consolidation (CHOP_MARKET) or an extreme (EXTREME_LEVEL)
  TIER_2_WATCHLIST      aligned (M1 / M2 / M3), price not in contact with a valid AOI yet
  TIER_1_SNIPER_AOI     in contact with a valid AOI (within delta_prox) and a score that can still reach a grade
  TIER_1_SOS_CONFIRMED  a body-close SoS on M15 / M30 / H1 is in
  AWAIT_PULLBACK_LIMIT  a huge engulfing: the 50 % limit waits (8 h)
  SIGNAL_EMITTED        a clean engulfing closed and the final gates approved
"""

from .config import GRADE_BP, K, W_C8, meta
from .risk.levels import plan, risk_mult
from .risk.order import proposal
from .strategy.alignment import chasing, matrix
from .strategy.checks import audit
from .strategy.confluence import grade_of, score
from .strategy.data import health, snapshot
from .strategy.entry import best_sos, order, prox, triggers
from .strategy.structure import Structure, extreme
from .strategy.zones import dist_pips, polarity_ok, suspended, zone_map

TIERS = ["TIER_3_DORMANT", "TIER_2_WATCHLIST", "TIER_1_SNIPER_AOI", "TIER_1_SOS_CONFIRMED", "AWAIT_PULLBACK_LIMIT", "SIGNAL_EMITTED"]
SCENARIO_KIND = {"M1": "full", "M2": "retrace", "M3": "counter"}


class Ctx:
    """One pair's snapshot and the structure of its 7 timeframes, built once per new set of candles."""

    def __init__(self, key: str, m5, h1, d_hist=None, spread: float | None = None):
        self.key, self.m = key, meta(key)
        self.pip, self.lam = self.m["pip"], self.m["lam"]
        self.spread_typ = self.m["spread_pips"] * self.pip
        self.spread = spread if spread else self.spread_typ
        self.snap = snapshot(m5, h1, d_hist)
        self.m5, self.h1 = m5, h1
        self.st = {tf: Structure(self.snap[tf], self.pip, chop=tf in ("D", "H4")) for tf in K}
        self._zones: dict = {}

    def idx(self, T: int) -> dict:
        return {tf: self.snap[tf].idx(T) for tf in self.st}

    def zones(self, idx: dict, with_h4: bool) -> list[dict]:
        k = (idx["W"], idx["D"], idx["H4"] if with_h4 else -2, with_h4)
        if k not in self._zones:
            self._zones[k] = zone_map(self.st, idx, self.pip, self.lam, self.m["step500"], with_h4)
        return self._zones[k]


_ctx: dict = {}


def context(key: str, m5, h1, d_hist=None, spread=None) -> Ctx:
    sig = (m5[-1].time if m5 else 0, len(m5), h1[-1].time, len(h1), d_hist[-1].time if d_hist else 0, len(d_hist or []), spread)
    hit = _ctx.get(key)
    if not hit or hit[0] != sig:
        _ctx[key] = (sig, Ctx(key, m5, h1, d_hist, spread))
    return _ctx[key][1]


def evaluate(cx: Ctx, T: int, d: int, price: float | None = None, news: list[int] | None = None, locked: bool = False,
             exposure: dict | None = None) -> dict:
    """The pair's full read for direction d at the close T, from candles closed at T only."""
    pip, lam, st = cx.pip, cx.lam, cx.st
    idx = cx.idx(T)
    bw, bd, b4 = st["W"].biased(idx["W"]), st["D"].biased(idx["D"]), st["H4"].biased(idx["H4"])
    al = matrix(bw, bd, b4, d)
    h1 = st["H1"]
    P = price if price is not None else (h1.C[idx["H1"]] if idx["H1"] >= 0 else None)
    chop = {"D": bool(idx["D"] >= 0 and st["D"].chop[idx["D"]]), "H4": bool(idx["H4"] >= 0 and st["H4"].chop[idx["H4"]])}
    r = {"key": cx.key, "dir": d, "T": T, "bias": {"W": bw, "D": bd, "H4": b4}, "align": {**al, "dir": d if al["scenario"] != "M4" else 0,
         "strength": {"M1": 5, "M2": 5, "M3": 4}.get(al["scenario"], 0), "kind": SCENARIO_KIND.get(al["scenario"])},
         "aligned": al["scenario"] != "M4", "price": P, "tier": "TIER_3_DORMANT", "zone": None, "zones": [], "conf": None, "sos": None,
         "engulf": None, "plan": None, "audit": None, "proposal": None, "vetoes": [], "chop": chop, "health": health(cx.h1, cx.m5, T),
         "extreme": False, "suspended": False}
    if P is None or idx["W"] < 0 or idx["D"] < 0 or idx["H4"] < 0 or idx["H1"] < 0:
        r["vetoes"].append("NO_DATA")
        return r
    if not r["aligned"]:
        r["vetoes"].append("HTF_MISALIGNED")
        return r
    if chop["D"] and chop["H4"]:
        r["vetoes"].append("CHOP_MARKET")
        return r
    r["extreme"] = extreme(st["W"], idx["W"], d)
    if r["extreme"]:
        r["vetoes"].append("EXTREME_LEVEL")
        return r
    r["tier"] = "TIER_2_WATCHLIST"
    zones = cx.zones(idx, al["scenario"] == "M3")
    r["zones"] = zones
    dprox = prox(h1, idx["H1"], pip, lam)
    ok = [z for z in zones if polarity_ok(z, d) and (al["scenario"] != "M3" or "D" in z["tfs"] or z["kind"] == "H4")]
    r["near"] = min(ok, key=lambda z: dist_pips(P, z, pip)) if ok else None
    recent = h1.c[max(0, idx["H1"] - 11):idx["H1"] + 1]
    contact = [z for z in ok if any(x.low <= z["hi"] + dprox and x.high >= z["lo"] - dprox for x in recent)]
    live = []
    for z in contact:
        if suspended(z, d, st["D"], idx["D"], st["H4"], idx["H4"], pip):
            r["suspended"] = True
        else:
            live.append(z)
    if not live:
        return r
    z = min(live, key=lambda q: (dist_pips(P, q, pip), q["kind"] != "W+D"))
    r["zone"], r["zoneDist"], r["suspended"] = z, dist_pips(P, z, pip), False
    leg_tf = "H4" if al["scenario"] == "M3" else "D"
    lst, li = st[leg_tf], idx[leg_tf]
    lo_hi = (lst.hl[li], lst.hh[li]) if d > 0 else (lst.ll[li], lst.lh[li])
    if lo_hi[0] and lo_hi[1] and not z["flip"]:
        ch = chasing(P, min(lo_hi[0][0], lo_hi[1][0]), max(lo_hi[0][0], lo_hi[1][0]), d)
        if ch:
            r["vetoes"].append(ch)
            return r
    sc = score(st, idx, z, d, al["scenario"], pip, lam, None, dprox)
    r["conf"] = sc
    if sc["pre"] + W_C8["E1"] < GRADE_BP:
        return r
    r["tier"] = "TIER_1_SNIPER_AOI"
    sos = best_sos(st, T, z, d, dprox)
    r["sos"] = sos
    if sos:
        r["tier"] = "TIER_1_SOS_CONFIRMED"
    trs = triggers(st, T, z, d, dprox)
    if not trs:
        return r
    best = None
    for tr in trs:
        anchor = min(tr["sos"]["extreme"], tr["candle"].low) if d > 0 else max(tr["sos"]["extreme"], tr["candle"].high)
        plan_at = lambda e, _a=anchor: plan(e, d, z, _a, zones, st, idx, pip, lam, cx.spread, al["scenario"])  # noqa: E731
        o = order(tr, d, plan_at, 0)
        if o.get("reject") or o.get("tp") is None:
            best = best or {"tr": tr, "o": None, "reject": o.get("reject") or "RR_BELOW_MIN"}
            continue
        conf = score(st, idx, z, d, al["scenario"], pip, lam, o["model"], dprox)
        grade = grade_of(conf["total"], al["scenario"], o["rr"])
        h4a = st["H4"].atr[idx["H4"]] or 0
        ext = (min(abs(o["entry"] - z["hi"]), abs(o["entry"] - z["lo"])) if not (z["lo"] <= o["entry"] <= z["hi"]) else 0.0) / h4a if h4a else 0.0
        cand = {"grade": grade, "score": conf["total"], "rr": o["rr"], "model": o["model"], "ext_atr": ext, "slWide": o["slWide"], "trap": o["trap"],
                "side": "BUY" if d > 0 else "SELL", "side_of": {}, "slPips": round(o["risk"] / pip, 1), "entry": o["entry"], "sl": o["sl"],
                "tp": o["tp"], "orderType": o["orderType"], "entryTf": tr["eng_tf"], "sosTf": tr["sos"]["tf"], "time": T,
                "riskMult": risk_mult(T, grade), "early": [], "scenario": al["scenario"]}
        cur = {"tr": tr, "o": o, "conf": conf, "cand": cand}
        a = audit(cand, T, news, news is not None, cx.spread, cx.spread_typ, pip, r["health"], locked, exposure, tuple(cx.m["currencies"]))
        cur["audit"] = a
        if best is None or best.get("o") is None or (a["verdict"] == "APPROVE" and best["audit"]["verdict"] != "APPROVE"):
            best = cur
        if a["verdict"] == "APPROVE":
            break
    if best is None:
        return r
    tr = best["tr"]
    r["engulf"], r["sos"] = {"tf": tr["eng_tf"], "candle": tr["candle"], "model": tr["model"], "time": T}, tr["sos"]
    if best.get("o") is None:
        r["reject"] = best["reject"]
        r["vetoes"].append(best["reject"])
        return r
    r["plan"], r["conf"], r["candidate"], r["audit"] = best["o"], best["conf"], best["cand"], best["audit"]
    r["tier"] = "AWAIT_PULLBACK_LIMIT" if not best["o"]["market"] else r["tier"]
    if best["audit"]["verdict"] == "APPROVE":
        c = best["cand"]
        r["proposal"] = proposal(cx.m["symbol"], d, {**c, "grade": c["grade"], "score": c["score"], "riskPct": c["riskMult"]})
        if best["o"]["market"]:
            r["tier"] = "SIGNAL_EMITTED"
    return r
