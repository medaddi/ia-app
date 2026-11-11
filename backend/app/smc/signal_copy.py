"""
The copy payload of a signal (Telegram's "Copy setup data" button and its plain-text twin) and its import into the app.

  LD|v=1|id=SMC-XAUUSD-SF_BR-1794410100-S|symbol=XAUUSD|side=SELL|entry=2350.40|sl=2357.10|tp=2330.30|tf=M15|time=2026-11-11T11:30Z

Only market data: never a user's risk amount or lot size. On import the payload is parsed strictly (exactly these keys,
once each), each field validated, then checked against the signal the app itself saved (same id, symbol, side, entry,
stop, target, timeframe and time): a payload the app never sent, an edited one, a stale one (over 24 h) or one from the
future is rejected. The lot is then computed again from the SIGNED-IN user's own USD risk. Importing places no order.
"""

import math
import re
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy.orm import Session

from ..market.pairs import decimals_of
from ..models import Signal

PREFIX, VERSION = "LD", "1"
KEYS = ("v", "id", "symbol", "side", "entry", "sl", "tp", "tf", "time")
TFS = {"M5", "M15", "M30", "H1", "H2", "H4", "D1", "W1"}
STALE_SEC = 24 * 3600   # CHOICE: a signal older than a day is not imported
FUTURE_SEC = 5 * 60     # clocks may differ by a few minutes, not more
ENDED = {"CLOSED", "EXPIRED", "MISSED", "BLOCKED"}
ID_RE = re.compile(r"^SMC-([A-Z]{6})-[A-Z0-9_]{2,16}-(\d{9,11})-([BS])$")
MAX_LEN = 256  # Telegram's copy_text limit


def iso_min(t: int) -> str:
    return datetime.fromtimestamp(t, timezone.utc).strftime("%Y-%m-%dT%H:%MZ")


def payload(s: dict, symbol: str) -> str:
    """The copy text of a sent setup (`s` is the setup JSON the desk sends)."""
    dec = decimals_of(symbol)
    f = lambda v: f"{v:.{dec}f}"  # noqa: E731
    out = (f"{PREFIX}|v={VERSION}|id={s['id']}|symbol={symbol.replace('/', '')}|side={s['direction']}|entry={f(s['entry'])}|sl={f(s['sl'])}"
           f"|tp={f(s['tp'])}|tf={s.get('etf') or 'H1'}|time={iso_min(int(s['time']))}")
    assert len(out) <= MAX_LEN
    return out


def parse(text: str) -> tuple[Optional[dict], list[str]]:
    """The fields of a pasted payload, or the reasons it is rejected. Only the payload line is read (a whole pasted
    Telegram message is fine: its other lines are ignored)."""
    if not isinstance(text, str) or not text.strip():
        return None, ["nothing pasted"]
    lines = [ln.strip().strip("`").strip() for ln in text.strip().splitlines()]
    cand = [ln for ln in lines if ln.startswith(PREFIX + "|")]
    if len(cand) != 1:
        return None, ["no setup data found: paste the line that starts with LD|" if not cand else "more than one setup in the paste"]
    line = cand[0]
    if len(line) > MAX_LEN:
        return None, ["the setup data is too long"]
    parts = line.split("|")[1:]
    kv, errs = {}, []
    for p in parts:
        if "=" not in p:
            return None, [f"malformed field '{p[:20]}'"]
        k, v = p.split("=", 1)
        if k in kv:
            return None, [f"field '{k}' given twice"]
        kv[k] = v
    if set(kv) != set(KEYS):
        miss, extra = [k for k in KEYS if k not in kv], [k for k in kv if k not in KEYS]
        return None, [f"missing {', '.join(miss)}" if miss else f"unexpected {', '.join(extra)}"]
    if kv["v"] != VERSION:
        errs.append(f"unknown version {kv['v']}")
    sym = kv["symbol"]
    from .desk import BY_SYMBOL
    pair = f"{sym[:3]}/{sym[3:]}" if re.fullmatch(r"[A-Z]{6}", sym) else None
    if pair not in BY_SYMBOL:
        errs.append(f"unknown symbol {sym}")
    side = kv["side"]
    if side not in ("BUY", "SELL"):
        errs.append(f"unknown side {side}")
    m = ID_RE.match(kv["id"])
    if not m:
        errs.append("malformed signal id")
    elif m.group(1) != sym or m.group(3) != ("B" if side == "BUY" else "S"):
        errs.append("the signal id does not match the symbol / side")
    px = {}
    for k in ("entry", "sl", "tp"):
        v = kv[k]
        if not re.fullmatch(r"\d{1,7}(\.\d{1,6})?", v):
            errs.append(f"{k} is not a price")
            continue
        x = float(v)
        if not (math.isfinite(x) and x > 0):
            errs.append(f"{k} is not a positive price")
        elif pair and len(v.split(".")[1]) > decimals_of(pair) if "." in v else False:
            errs.append(f"{k} has more decimals than {pair} prices")
        px[k] = x
    if len(px) == 3 and side in ("BUY", "SELL"):
        e, s_, t_ = px["entry"], px["sl"], px["tp"]
        if side == "BUY" and not (s_ < e < t_):
            errs.append("a BUY needs stop < entry < target")
        if side == "SELL" and not (t_ < e < s_):
            errs.append("a SELL needs target < entry < stop")
    if kv["tf"] not in TFS:
        errs.append(f"unknown timeframe {kv['tf']}")
    try:
        ts = int(datetime.strptime(kv["time"], "%Y-%m-%dT%H:%MZ").replace(tzinfo=timezone.utc).timestamp())
    except ValueError:
        ts = None
        errs.append("the time is not YYYY-MM-DDTHH:MMZ (UTC)")
    if errs:
        return None, errs
    return {"id": kv["id"], "symbol": pair, "side": side, "entry": px["entry"], "sl": px["sl"], "tp": px["tp"], "tf": kv["tf"], "time": ts}, []


def check_against_app(db: Session, f: dict, now: float) -> tuple[Optional[Signal], list[str]]:
    """The signal the app saved for this payload, or why the payload is not one of the app's live signals."""
    errs = []
    if f["time"] > now + FUTURE_SEC:
        errs.append("the signal time is in the future")
    elif now - f["time"] > STALE_SEC:
        errs.append(f"the signal is {int((now - f['time']) // 3600)} h old: stale (over 24 h)")
    sig = db.get(Signal, f["id"])
    if sig is None or not sig.id.startswith("SMC-"):
        return None, errs + ["this app never sent a signal with that id"]
    if sig.state in ENDED:
        errs.append(f"the signal is no longer live ({sig.state.lower()})")
    dec = decimals_of(sig.symbol)
    same = lambda a, b: abs(a - b) < 0.5 * 10 ** -dec  # noqa: E731
    stored_tf = (sig.payload or {}).get("etf") or "H1"
    diffs = [n for n, ok in (("symbol", sig.symbol == f["symbol"]), ("side", sig.direction == f["side"]), ("entry", same(sig.entry, f["entry"])),
                             ("stop", same(sig.sl, f["sl"])), ("target", same(sig.tp2, f["tp"])), ("timeframe", stored_tf == f["tf"]),
                             ("time", abs(int(sig.signal_time) - f["time"]) < 60)) if not ok]
    if diffs:
        errs.append("does not match the signal the app sent: " + ", ".join(diffs) + " differ")
    return sig, errs
