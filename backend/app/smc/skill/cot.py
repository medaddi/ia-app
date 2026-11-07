"""
COT positioning: the forex and gold version of trader-copycat (github.com/Jakeschincariol/trader-skill, MIT licence in
LICENSE-trader-skill.txt). For the pair teams it is CONTEXT, never a trigger (MASTER BRIEF: "context filter, not a trigger").

trader-copycat copies an investor from the 13F filing they must publish. Gold and currencies have no 13F; their big
players publish their futures positions instead, every week, in the CFTC Commitments of Traders report (free, public):
  large speculators  (non-commercials: hedge funds, CTAs) the money that follows a view
  commercials        (producers, banks hedging) usually on the other side

For each instrument the team reads 3 years of weekly reports and copies the speculators' side:
  net            speculators long − short contracts, and as a % of their positions
  COT index      where this week's net sits in its 3-year range (0 = the most short in 3 years, 100 = the most long)
  the side       the speculators' net: a USD pair is its currency's futures (EUR/USD = the euro), gold the gold futures,
                 a cross the difference of its two currencies (EUR/CHF = euro net % − franc net %).
                 More than 10 % net long → BUY (copy them), more than 10 % net short → SELL, between → no clear side
  strength       how one-sided they are (the net %, up to 100)
  crowded        their side is at its 3-year extreme (index ≥ 90 for a BUY, ≤ 10 for a SELL): everybody is already in,
                 the late part of a move

What it is not: the report is as of Tuesday, published on Friday (3 days late). It shows positions on CME / COMEX
futures, not the spot market, and nothing about timing. Positioning, not a signal.
"""

import time
from datetime import date, timedelta
from typing import Optional

import httpx

URL = "https://publicreporting.cftc.gov/resource/6dca-aqww.json"  # Legacy, futures only
MARKETS = {"XAU": ("088691", "Gold (COMEX)"), "EUR": ("099741", "Euro FX (CME)"), "GBP": ("096742", "British pound (CME)"),
           "CHF": ("092741", "Swiss franc (CME)"), "AUD": ("232741", "Australian dollar (CME)"), "CAD": ("090741", "Canadian dollar (CME)")}
# each instrument from its legs: (+1 base currency futures, −1 quote currency futures)
LEGS = {"XAU/USD": [("XAU", 1)], "EUR/USD": [("EUR", 1)], "GBP/USD": [("GBP", 1)], "EUR/CHF": [("EUR", 1), ("CHF", -1)],
        "AUD/CAD": [("AUD", 1), ("CAD", -1)], "AUD/CHF": [("AUD", 1), ("CHF", -1)]}
TTL = 6 * 3600  # a weekly report: read again at most every 6 hours
CAVEATS = [
    "The COT report is a snapshot of Tuesday, published on Friday: three days old when you read it.",
    "It shows futures positions on CME / COMEX, not the spot market or your broker's.",
    "It says where the big players are, not when price will move. Positioning, not a signal.",
    "Education and tooling, not financial advice. Nothing here places an order.",
]

_cache: dict = {"at": 0.0, "rows": None}


async def _fetch() -> list[dict]:
    since = (date.today() - timedelta(days=3 * 365 + 14)).isoformat()
    codes = ",".join(f"'{c}'" for c, _ in MARKETS.values())
    params = {"$select": "report_date_as_yyyy_mm_dd,cftc_contract_market_code,noncomm_positions_long_all,noncomm_positions_short_all,"
                         "comm_positions_long_all,comm_positions_short_all,open_interest_all",
              "$where": f"cftc_contract_market_code in({codes}) AND report_date_as_yyyy_mm_dd >= '{since}'",
              "$order": "report_date_as_yyyy_mm_dd ASC", "$limit": "5000"}
    async with httpx.AsyncClient(timeout=20, headers={"User-Agent": "LiquidityDissection COT reader"}) as c:
        r = await c.get(URL, params=params)
    r.raise_for_status()
    data = r.json()
    if not isinstance(data, list) or not data:
        raise ValueError("empty COT answer")
    return data


def _series(raw: list[dict]) -> dict[str, list[dict]]:
    by_code = {code: k for k, (code, _) in MARKETS.items()}
    out: dict[str, list[dict]] = {k: [] for k in MARKETS}
    for x in raw:
        k = by_code.get(x.get("cftc_contract_market_code"))
        if not k:
            continue
        L, S = float(x["noncomm_positions_long_all"]), float(x["noncomm_positions_short_all"])
        out[k].append({"date": x["report_date_as_yyyy_mm_dd"][:10], "long": L, "short": S, "net": L - S,
                       "netPct": 100 * (L - S) / (L + S) if L + S else 0.0,
                       "commNet": float(x["comm_positions_long_all"]) - float(x["comm_positions_short_all"]),
                       "oi": float(x["open_interest_all"])})
    return out


def market_view(s: list[dict]) -> Optional[dict]:
    """One futures market: this week's speculator net, its 3-year COT index and its weekly change."""
    if len(s) < 10:
        return None
    nets = [w["net"] for w in s]
    lo, hi = min(nets), max(nets)
    last, prev = s[-1], s[-2]
    index = 100 * (last["net"] - lo) / (hi - lo) if hi > lo else 50.0
    return {"date": last["date"], "long": last["long"], "short": last["short"], "net": last["net"], "netPct": last["netPct"],
            "change": last["net"] - prev["net"], "index": index, "commNet": last["commNet"], "weeks": len(s),
            "history": [{"date": w["date"], "net": w["net"]} for w in s[-52:]]}


def pair_view(symbol: str, views: dict[str, dict]) -> Optional[dict]:
    legs = LEGS[symbol]
    if any(views.get(k) is None for k, _ in legs):
        return None
    if len(legs) == 1:
        v = views[legs[0][0]]
        score, net_pct, change_up = v["index"], v["netPct"], v["change"] > 0
    else:
        (b, _), (q, _) = legs
        score = 50 + (views[b]["index"] - views[q]["index"]) / 2
        net_pct = views[b]["netPct"] - views[q]["netPct"]
        change_up = views[b]["change"] - views[q]["change"] > 0
    bias = "BUY" if net_pct > 10 else "SELL" if net_pct < -10 else "NEUTRAL"
    crowded = (bias == "BUY" and score >= 90) or (bias == "SELL" and score <= 10)
    return {"symbol": symbol, "bias": bias, "score": round(score, 1), "percentile": round(score, 1), "strength": round(min(100.0, abs(net_pct)), 1),
            "netPct": round(net_pct, 1), "rising": change_up, "crowded": crowded, "reportDate": views[legs[0][0]]["date"],
            "legs": [{"market": MARKETS[k][1], "code": MARKETS[k][0], "sign": sg, **{x: round(views[k][x], 1) for x in ("net", "netPct", "change", "index", "commNet")},
                      "long": views[k]["long"], "short": views[k]["short"], "history": views[k]["history"]} for k, sg in legs]}


async def cot_all(fresh: bool = False) -> list[dict]:
    """Every instrument's COT view (cached 6 hours)."""
    if not fresh and _cache["rows"] is not None and time.time() - _cache["at"] < TTL:
        return _cache["rows"]
    series = _series(await _fetch())
    views = {k: market_view(v) for k, v in series.items()}
    rows = [r for r in (pair_view(s, views) for s in LEGS) if r]
    _cache.update(at=time.time(), rows=rows)
    return rows

