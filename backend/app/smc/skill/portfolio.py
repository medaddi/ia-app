"""
The portfolio risk check across ALL the pair teams: the trader-risk part of the trader-skill (github.com/Jakeschincariol/
trader-skill, MIT), adapted to the MASTER BRIEF's 1 % per trade. Each team checks its own setup with the 7 questions; this
checks the setups TOGETHER, because six teams can find a trade at the same moment. PASS or BLOCK, with every reason.

A setup is "live" from its signal until its limit expires plus the 4 hours a filled trade may run (the engine's HOLD).

  duplicate   a live setup already on this pair (one trade per pair at a time)
  dollar      already max_usd_same_side live setups betting the same way on the US dollar: EUR/USD, GBP/USD and XAU/USD
              move together (BUY any of them = short the dollar), so three of them at once is one big dollar bet
  total risk  the live setups plus this one would risk more than max_total_risk_pct of the balance (1 % each)
  daily       already max_orders_per_day setups sent today (UTC)
  correlation the guide's correlation cap (global risk rule 2), for a trade the SAME way as a live one:
              EUR/USD + GBP/USD (+0.84): the risk is split, 0.5 % on each (PASS with riskPct 0.5: the alert halves the lot
              and says to cut the other trade to 0.5 % too) · AUD/CAD + AUD/CHF (+0.66): not both (BLOCK).

The numbers are the skill's defaults made stricter for 1 % per trade (HYPOTHESIS: not tested). Nothing here places an order.
"""

from typing import Iterable, Optional

LIMITS = {"risk_pct": 1.0, "max_total_risk_pct": 3.0, "max_usd_same_side": 2, "max_orders_per_day": 5}
USD_PAIRS = {"EUR/USD", "GBP/USD", "XAU/USD"}  # quoted against the dollar
HOLD_SEC = 4 * 3600


def usd_side(symbol: str, direction: str) -> int:
    """+1 = long the dollar, −1 = short it, 0 = no dollar leg. BUY EUR/USD, GBP/USD or XAU/USD sells the dollar."""
    if symbol not in USD_PAIRS:
        return 0
    return -1 if direction == "BUY" else 1


def live(sent: Iterable[dict], now: int) -> list[dict]:
    """The setups sent that may still be open: until their `liveUntil` (the last moment the trade can still run), or for
    an older setup its limit's end plus the 4 hours a filled trade may run."""
    return [s for s in sent if (s.get("liveUntil") or (s.get("validUntil") or s.get("time", 0)) + HOLD_SEC) > now]


CORRELATED = [({"EUR/USD", "GBP/USD"}, 0.84, "split"), ({"AUD/CAD", "AUD/CHF"}, 0.66, "block")]


def twins(symbol: str) -> dict[str, float]:
    """The pairs the guide counts as correlated with `symbol`, with their correlation."""
    return {p: c for grp, c, _ in CORRELATED if symbol in grp for p in grp if p != symbol}


def twin_rule(a: str, b: str) -> str | None:
    return next((rule for grp, _, rule in CORRELATED if {a, b} <= grp), None)


def check(symbol: str, setup: dict, sent: list[dict], now: int, limits: Optional[dict] = None) -> dict:
    """`sent`: the setups already sent (each with symbol, direction, time, validUntil). Returns PASS / BLOCK + reasons."""
    lim = {**LIMITS, **(limits or {})}
    open_ = live(sent, now)
    day = now // 86400
    reasons = []
    if any(s["symbol"] == symbol for s in open_):
        reasons.append(f"duplicate: a {symbol} setup is still live (one trade per pair at a time)")
    side = usd_side(symbol, setup["direction"])
    if side:
        same = [s for s in open_ if usd_side(s["symbol"], s["direction"]) == side]
        if len(same) >= lim["max_usd_same_side"]:
            reasons.append(f"dollar: already {len(same)} live setups {'long' if side > 0 else 'short'} the US dollar "
                           f"({', '.join(s['symbol'] for s in same)}); the limit is {lim['max_usd_same_side']}")
    tw = twins(symbol)
    same_way = [s for s in open_ if s["symbol"] in tw and s["direction"] == setup["direction"]]
    split = [s for s in same_way if twin_rule(symbol, s["symbol"]) == "split"]
    blocked = [s for s in same_way if twin_rule(symbol, s["symbol"]) == "block"]
    if blocked:
        reasons.append("correlation: " + ", ".join(f"{s['symbol']} {s['direction']} (+{tw[s['symbol']]:.2f})" for s in blocked)
                       + " already live the same way: the guide forbids both at full risk at the same time")
    notes = [f"correlation: {s['symbol']} {s['direction']} (+{tw[s['symbol']]:.2f}) is live the same way: 0.5 % on each "
             f"(this one at 0.5 %, cut the {s['symbol']} trade to 0.5 % too)" for s in split]
    total = (len(open_) + 1) * lim["risk_pct"]
    if total > lim["max_total_risk_pct"]:
        reasons.append(f"total risk: {len(open_)} live setups + this one = {total:g} % of the balance, over {lim['max_total_risk_pct']:g} %")
    today = [s for s in sent if s.get("time", 0) // 86400 == day]
    if len(today) >= lim["max_orders_per_day"]:
        reasons.append(f"daily: already {len(today)} setups sent today, the limit is {lim['max_orders_per_day']}")
    return {"verdict": "BLOCK" if reasons else "PASS", "reasons": reasons, "live": len(open_), "limits": lim,
            "riskPct": 0.5 if split and not reasons else lim["risk_pct"], "notes": notes}
