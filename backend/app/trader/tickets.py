"""
Order tickets and the decision log: the forex and gold version of trader-broker (github.com/Jakeschincariol/trader-skill,
MIT; the yes rules are the skill's own).

It never talks to a broker and never places anything. Around the one moment that matters, your yes:
  status    an order is READY only if the risk check passed THIS exact order today (fingerprint) and nobody decided yet
  approve   records your explicit yes for ONE order, word for word. It refuses "yes to all", "sure", "ok", a yes that names
            another instrument or another size, and any order that is not READY. You then place it yourself at your broker.
  decline   records a no.
Everything goes to the user's broker log (append only).
"""

import re
from datetime import datetime, timezone
from typing import Optional

from .risk import fingerprint

YES_WORDS = ("yes", "y", "oui", "ah", "iyeh", "نعم", "آه")
BATCH_WORDS = {"all", "every", "everything", "rest", "remaining", "them", "both", "batch", "each", "tous", "tout", "kolchi"}
DOUBT_WORDS = {"no", "not", "dont", "don't", "wait", "cancel", "stop", "but", "maybe", "later", "hold", "unless", "if",
               "non", "mais", "attends", "bla"}


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def today() -> str:
    return datetime.now(timezone.utc).date().isoformat()


def plain(o: dict) -> str:
    """BUY 0.12 lot of EUR/USD at market, stop 1.11500, target 1.12900 (risk $50)"""
    lots = o.get("lots")
    return (f"{str(o.get('side', '')).upper()} {lots:g} lot{'' if lots == 1 else 's'} of {o.get('symbol')} at market, "
            f"stop {o.get('sl')}, target {o.get('tp')} (risk ${float(o.get('riskUsd') or 0):,.0f})")


def parse_yes(reply: str, order: dict, batch_symbols=()) -> tuple[bool, str]:
    """Is this reply an explicit yes for THIS one order? (ok, why)"""
    raw = (reply or "").strip()
    if not raw:
        return False, "the reply is empty"
    if "?" in raw:
        return False, "the reply is a question, not a yes"
    words = re.findall(r"[a-zA-Z؀-ۿ']+", raw.lower())
    if not words or words[0] not in YES_WORDS:
        return False, 'only a reply that starts with "yes" counts (not ok, sure, go, do it)'
    if BATCH_WORDS & set(words):
        return False, "a yes covers one order at a time, not a batch"
    if DOUBT_WORDS & set(words[1:]):
        return False, "the reply has a condition or a doubt in it; ask again"
    sym = str(order.get("symbol", "")).upper()
    named = {s.upper() for s in batch_symbols if s.upper() != sym and (s.upper() in raw.upper() or s.upper().replace("/", "") in raw.upper())}
    if named:
        return False, f"the reply names {', '.join(sorted(named))}, but this order is for {sym}"
    nums = [float(n.replace(",", ".")) for n in re.findall(r"\d+(?:[.,]\d+)?", raw)]
    if nums:
        want = [float(order.get("lots") or 0)]
        if not any(abs(n - w) < 0.0001 for n in nums for w in want):
            return False, f"the reply says {', '.join(f'{n:g}' for n in nums)}, but this order is {plain(order)}"
    return True, f"explicit yes for {plain(order)}"


def latest(log: list[dict], fp: str, day: str) -> Optional[dict]:
    found = None
    for rec in log:
        if rec.get("fingerprint") == fp and str(rec.get("at", ""))[:10] == day:
            found = rec
    return found


def status_of(order: dict, risk: Optional[dict], log: list[dict], day: str) -> tuple[bool, str]:
    fp = fingerprint(order)
    if not risk:
        return False, "NOT READY: the risk check has not looked at these orders"
    if risk.get("date") != day:
        return False, f"NOT READY: the risk check is from {risk.get('date')}, not today"
    rv = next((r for r in risk.get("results", []) if r.get("fingerprint") == fp), None)
    if not rv:
        return False, "NOT READY: this exact order was not in the last risk check (it changed); check again"
    if rv["verdict"] != "PASS":
        return False, "BLOCKED by the risk check: " + "; ".join(rv.get("reasons", []))
    rec = latest(log, fp, day)
    if rec:
        return False, f"DONE: {rec.get('status')} at {rec.get('at', '')[11:16]} UTC"
    return True, "READY: the risk check passed, waiting for your yes"
