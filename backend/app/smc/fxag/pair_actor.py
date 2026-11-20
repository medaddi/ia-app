"""
The PairActor (spec 5.1): one pair, isolated (it reads only its own candles), as a finite state machine. Its state at a
candle close is DERIVED from the closed candles every time (a deterministic replay: a restart can never lose or invent
a state), in the spec's order: Agent 1 snapshot -> 2 structure and alignment -> 3 zones -> 4 score -> 5 SoS + engulfing
-> 6 plan -> 7 audit -> 8 locked order.

  TIER_3_DORMANT        no two consecutive HTFs aligned (or the Daily consolidating)
  TIER_2_WATCHLIST      aligned, price not yet at an eligible AOI with enough confluence
  TIER_1_SNIPER_AOI     at an eligible AOI (<= 5 lambda pips, visited in the last 24 H1 candles and within 15 pips) and
                        the score with the mandatory entry sequence >= 80 % (CHOICE, see `tier1_ok`)
  TIER_1_SOS_CONFIRMED  a valid body-close SoS (12 h) is in
  AWAIT_PULLBACK_LIMIT  a huge engulfing: the 50 % limit waits (6 h)
  SIGNAL_EMITTED        the engulfing closed and the auditor approved
"""

from .strategy.data import health, snapshot
from .strategy.structure import Structure, alignment, extreme
from .strategy.zones import dist_pips, polarity_ok, suspended, zone_map
from .strategy.confluence import score
from .strategy.entry import best_sos, engulf_at, order
from .risk.levels import plan, risk_pct
from .strategy.checks import audit
from .risk.order import proposal
from .config import PROX_PIPS, W_ENTRY, meta

TIERS = ["TIER_3_DORMANT", "TIER_2_WATCHLIST", "TIER_1_SNIPER_AOI", "TIER_1_SOS_CONFIRMED", "AWAIT_PULLBACK_LIMIT", "SIGNAL_EMITTED"]


def tier1_ok(pre: int) -> bool:
    """CHOICE (the spec is self-contradictory here): Tier 1 asks "S_total >= 80 %" before the entry, but S_total holds the
    mandatory SoS + Engulfing weight (+10); read literally before the entry no Grade B could ever exist. Tier 1 therefore
    counts the gatekeeper weight as present: pre-entry score + 10 >= 80."""
    return pre + W_ENTRY >= 80


class Ctx:
    """One pair's snapshot and the structure of its 7 timeframes (built once per new set of candles)."""

    def __init__(self, key: str, m5, h1, d_hist=None, spread: float | None = None):
        self.key, self.m = key, meta(key)
        self.pip, self.lam = self.m["pip"], self.m["lam"]
        self.spread_median = self.m["spread_pips"] * self.pip
        self.spread = spread if spread else self.spread_median
        self.snap = snapshot(m5, h1, d_hist)
        self.m5, self.h1 = m5, h1
        self.st = {tf: Structure(self.snap[tf], self.pip, chop=tf in ("W", "D")) for tf in ("W", "D", "H4", "H2", "H1", "M30", "M15")}
        self._zones: dict = {}

    def idx(self, T: int) -> dict:
        return {tf: self.snap[tf].idx(T) for tf in self.st}

    def zones(self, iw: int, id_: int) -> list[dict]:
        if (iw, id_) not in self._zones:
            self._zones[(iw, id_)] = zone_map(self.st["W"], self.st["D"], iw, id_, self.pip, self.lam, self.m["step500"])
        return self._zones[(iw, id_)]


_ctx: dict = {}


def context(key: str, m5, h1, d_hist=None, spread=None) -> Ctx:
    sig = (m5[-1].time if m5 else 0, len(m5), h1[-1].time, len(h1), d_hist[-1].time if d_hist else 0, len(d_hist or []), spread)
    hit = _ctx.get(key)
    if not hit or hit[0] != sig:
        _ctx[key] = (sig, Ctx(key, m5, h1, d_hist, spread))
    return _ctx[key][1]


def evaluate(cx: Ctx, T: int, d: int, price: float | None = None, news: list[int] | None = None, need_engulf: bool = True) -> dict:
    """The pair's full read for direction d at the close T (price: the live price; default the last H1 close)."""
    pip, lam, st = cx.pip, cx.lam, cx.st
    idx = cx.idx(T)
    bw, bd, b4 = st["W"].biased(idx["W"]), st["D"].biased(idx["D"]), st["H4"].biased(idx["H4"])
    al = alignment(bw, bd, b4)
    h1 = st["H1"]
    P = price if price is not None else (h1.C[idx["H1"]] if idx["H1"] >= 0 else None)
    r = {"dir": d, "T": T, "bias": {"W": bw, "D": bd, "H4": b4}, "align": al, "aligned": al["dir"] == d, "price": P, "tier": "TIER_3_DORMANT",
         "zone": None, "zones": [], "conf": None, "sos": None, "engulf": None, "plan": None, "audit": None, "proposal": None,
         "chop": {"W": st["W"].chop[idx["W"]] if idx["W"] >= 0 else False, "D": st["D"].chop[idx["D"]] if idx["D"] >= 0 else False},
         "extreme": extreme(st["W"], idx["W"], d), "health": health(cx.h1, cx.m5, T)}
    if P is None or idx["W"] < 0 or idx["D"] < 0:
        return r
    zones = cx.zones(idx["W"], idx["D"])
    r["zones"] = zones
    counter = al["kind"] == "counter"
    ok = [z for z in zones if polarity_ok(z, d) and (not counter or "D" in z["tfs"])]
    if not r["aligned"]:
        r["near"] = min(ok, key=lambda z: dist_pips(P, z, pip)) if ok else None
        return r
    r["tier"] = "TIER_2_WATCHLIST"
    m = PROX_PIPS * lam * pip
    recent = h1.c[max(0, idx["H1"] - 23):idx["H1"] + 1]
    visited = [z for z in ok if any(x.low <= z["hi"] + m and x.high >= z["lo"] - m for x in recent) and dist_pips(P, z, pip) <= 15 * lam]
    near = min(ok, key=lambda z: dist_pips(P, z, pip)) if ok else None
    r["near"] = near
    if not visited:
        return r
    z = min(visited, key=lambda q: (dist_pips(P, q, pip), q["kind"] != "W+D_MERGED"))
    r["zone"] = z
    r["zoneDist"] = dist_pips(P, z, pip)
    r["suspended"] = suspended(z, d, st["D"], idx["D"], st["W"], idx["W"], pip, lam)
    conf = score(st, idx, z, d, al["kind"], pip, lam)
    r["conf"] = conf
    if r["suspended"] or not tier1_ok(conf["pre"]) or r["zoneDist"] > PROX_PIPS * lam and not any(
            x.low <= z["hi"] + m and x.high >= z["lo"] - m for x in recent[-3:]):
        return r
    r["tier"] = "TIER_1_SNIPER_AOI"
    sos = best_sos(st, T, z, d, pip, lam)
    r["sos"] = sos
    if not sos:
        return r
    r["tier"] = "TIER_1_SOS_CONFIRMED"
    eng = engulf_at(st, T, d, pip, lam, sos["time"])
    r["engulf"] = eng
    if not eng:
        return r
    plan_at = lambda e: plan(e, d, z, sos["extreme"], eng["candle"], zones, st, idx, pip, lam, cx.spread, counter)  # noqa: E731
    o = order(eng, z, d, plan_at, pip, lam)
    r["order"] = o
    conf = score(st, idx, z, d, al["kind"], pip, lam, entry_ok=True)
    r["conf"] = conf
    if not o or o.get("reject"):
        r["reject"] = (o or {}).get("reject") or "ERR_NO_STRUCTURAL_TARGET"
        return r
    r["plan"] = o
    if not o["market"]:
        r["tier"] = "AWAIT_PULLBACK_LIMIT"
    g = conf["grade"]
    p = {"score": conf["total"], "grade": g, "sos": True, "engulf": True, "rr": o["rr"], "orderType": o["orderType"],
         "entryDistPips": dist_pips(o["entry"], z, pip), "trap": o["trap"], "suspended": r["suspended"], "extreme": r["extreme"],
         "slPips": round(o["risk"] / pip, 1), "entry": o["entry"], "sl": o["sl"], "tp": o["tp"], "entryTf": eng["tf"], "sosTf": sos["tf"],
         "time": T, "riskPct": risk_pct(T, g)}
    r["candidate"] = p
    r["audit"] = audit(p, T, news, news is not None, cx.spread, cx.spread_median, pip, lam, r["health"])
    if r["audit"]["verdict"] == "APPROVE":
        r["proposal"] = proposal(cx.m["symbol"], d, p)
        if o["market"]:
            r["tier"] = "SIGNAL_EMITTED"
    return r
