"""
Trade follow-up: while a sent trade runs, short notices that say what happened and what to do, on Telegram (the chats
that got the trade) and on the phones (Web Push). Each notice goes out once per trade (claimed in push_sent first):
- 🟡 ORDER FILLED   a limit order was triggered → the trade is live
- 📈 +1R            one risk in profit (targets are 1.5R–2R) → hold
- ⚠️ NEAR SL        down 0.7R → keep the stop, add nothing
- 📰 NEWS IN N MIN  high-impact news on one of the pair's currencies within 30 min → keep the SL
- 🚪 EXIT SOON / ⌛ CANCEL  the trade-management agent: the strategy's exit is forming, or a limit order is about to expire
How a trade ends (TP / SL / BE / cancelled) is sent by notify_closed / push_closed.
"""

import hashlib
import html
import time
from typing import Optional

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from .db import SessionLocal
from .models import PushSent, Signal
from .trading import TERMINAL, signal_json

NEWS_WINDOW = 1800  # warn this long before the news
FILLED = ("OPEN", "TP1_HIT", "TP2_HIT")
MANAGER_NOTICE = {"EXIT_SOON": "🚪 EXIT SOON", "CANCEL": "⌛ CANCEL THE ORDER"}  # the trade manager's verdicts sent as notices


def _currencies(symbol: str) -> set[str]:
    base, quote = symbol.split("/")
    return {"USD"} if base == "XAU" else {base, quote}


def events_for(sig: Signal, price: Optional[float], news: list[dict], now: float) -> list[tuple[str, str, str]]:
    """The notices this trade is due now, as (key, headline, what to do)."""
    out: list[tuple[str, str, str]] = []
    filled = sig.state in FILLED
    if filled and sig.entry_type != "MARKET":
        out.append(("fill", "🟡 ORDER FILLED", "👉 The trade is live. Keep SL and TP as they are."))
    risk = abs(sig.entry - sig.sl)
    if filled and price and risk > 0:
        r = (price - sig.entry) / risk * (1 if sig.direction == "BUY" else -1)
        if r >= 1:
            out.append(("1r", "📈 +1R", "👉 Good progress toward TP. Hold the trade, don't close early."))
        elif r <= -0.7:
            out.append(("nearsl", "⚠️ NEAR SL", "👉 Keep the stop where it is. Don't add to the trade."))
    ccys = _currencies(sig.symbol)
    for e in news:
        t = e.get("time") or 0
        if e.get("impact") == "High" and e.get("currency") in ccys and now < t <= now + NEWS_WINDOW:
            mins = max(1, round((t - now) / 60))
            out.append((f"news{int(t)}", f"📰 NEWS IN {mins} MIN",
                        f"{e['currency']} {html.escape(e.get('title', ''))}\n👉 Big moves possible. Keep your SL, don't move it."))
    return out


def _claim(db, key: str, signal_id: str) -> bool:
    """True the first time this notice is claimed for this trade (several ticks or workers never send it twice)."""
    db.add(PushSent(id=f"fu:{key}:{hashlib.sha1(signal_id.encode()).hexdigest()[:24]}"))
    try:
        db.commit()
        return True
    except IntegrityError:
        db.rollback()
        return False


async def follow_up(symbol: str, price: Optional[float], manager: Optional[dict] = None, setup_id: Optional[str] = None) -> int:
    """Sends the notices due now for the running trades of `symbol`. Returns how many notices went out.
    `manager`: the trade-management agent's verdict on the trade `setup_id` (its EXIT SOON / CANCEL become a notice too)."""
    from .push import push_update
    from .strategies.shared.news import load_news_calendar
    from .telegram.bot import send_update

    with SessionLocal() as db:
        running = list(db.scalars(select(Signal).where(Signal.symbol == symbol, Signal.state.not_in(TERMINAL))))
        if not running:
            return 0
        try:
            news = (await load_news_calendar())["events"]
        except Exception:  # no calendar: price notices still go out
            news = []
        now = time.time()
        items = [(s, key, head, todo) for s in running for key, head, todo in events_for(s, price, news, now)]
        for s in running:
            if manager and s.id == setup_id and manager.get("verdict") in MANAGER_NOTICE:
                head = MANAGER_NOTICE[manager["verdict"]]
                items.append((s, f"{manager['verdict'].lower()}{manager.get('exitAt') or ''}", head, f"👉 {manager['action']['en']}"))
        due = [(signal_json(s), key, head, todo) for s, key, head, todo in items if _claim(db, key, s.id)]
    for sig, key, head, todo in due:
        await send_update(sig, head, todo)
        await push_update(sig, head, todo, f"ld-{key}-{sig['id']}")
    return len(due)
