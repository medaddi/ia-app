"""
Web Push: trade notifications that reach the phone even when the app is closed (the tab is frozen or not open).
- VAPID keys are generated once and kept in the database (settings "push"), or come from VAPID_PUBLIC_KEY / VAPID_PRIVATE_KEY.
- Each browser that turns notifications on stores its push subscription (PushSubscription).
- Every new signal the strategy may notify, once the AI trade desk approves it, is pushed once (PushSent dedupes by setup id),
  to every approved, active account. Independent of Telegram.
"""

import asyncio
import base64
import json
import os
from typing import Optional

from cryptography.hazmat.primitives import serialization
from py_vapid import Vapid01
from pywebpush import WebPushException, webpush
from sqlalchemy import or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .db import SessionLocal
from .models import PushSent, PushSubscription, User
from .store import get_setting, set_setting
from .strategies.service import CONFIGS, normalize_symbol
from .trading import effective_risk, lot_for_risk

SUBJECT = os.environ.get("VAPID_SUBJECT", "mailto:alerts@liquiditydissection.app")  # contact the push services may use
TTL = 3600  # a trade notification older than an hour is useless: the push service may drop it after that


def _b64url(b: bytes) -> str:
    return base64.urlsafe_b64encode(b).rstrip(b"=").decode()


def vapid_keys(db: Session) -> dict:
    """{"publicKey": base64url (for the browser), "privateKey": PEM}: from the environment, else created once and stored."""
    env_pub, env_priv = os.environ.get("VAPID_PUBLIC_KEY"), os.environ.get("VAPID_PRIVATE_KEY")
    if env_pub and env_priv:
        return {"publicKey": env_pub, "privateKey": env_priv.replace("\\n", "\n")}
    cfg = get_setting(db, "push")
    if cfg.get("publicKey") and cfg.get("privateKey"):
        return cfg
    v = Vapid01()
    v.generate_keys()
    pub = v.public_key.public_bytes(serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint)
    keys = {"publicKey": _b64url(pub), "privateKey": v.private_pem().decode()}
    return set_setting(db, "push", keys)


def save_subscription(db: Session, user: User, sub: dict, agent: str = "") -> None:
    endpoint, keys = sub["endpoint"], sub.get("keys") or {}
    row = db.scalar(select(PushSubscription).where(PushSubscription.endpoint == endpoint))
    if row:
        row.user_id, row.p256dh, row.auth, row.user_agent = user.id, keys["p256dh"], keys["auth"], agent[:200]
    else:
        db.add(PushSubscription(endpoint=endpoint, p256dh=keys["p256dh"], auth=keys["auth"], user_id=user.id, user_agent=agent[:200]))
    db.commit()


def remove_subscription(db: Session, endpoint: str) -> None:
    row = db.scalar(select(PushSubscription).where(PushSubscription.endpoint == endpoint))
    if row:
        db.delete(row)
        db.commit()


def _send_one(row: PushSubscription, payload: str, private_pem: str) -> Optional[int]:
    """Sends one push; returns the HTTP status of a failure (None = delivered to the push service)."""
    try:
        webpush({"endpoint": row.endpoint, "keys": {"p256dh": row.p256dh, "auth": row.auth}}, payload,
                vapid_private_key=Vapid01.from_pem(private_pem.encode()), vapid_claims={"sub": SUBJECT}, ttl=TTL, timeout=8)
        return None
    except WebPushException as err:
        return err.response.status_code if err.response is not None else 0
    except Exception:  # network error: try again on the next signal
        return 0


async def send_push(db: Session, rows: list[PushSubscription], message: dict) -> int:
    """Pushes `message` ({title, body, tag, symbol}) to `rows` in parallel; forgets subscriptions the browser revoked."""
    if not rows:
        return 0
    pem = vapid_keys(db)["privateKey"]
    payload = json.dumps(message, ensure_ascii=False)
    results = await asyncio.gather(*(asyncio.to_thread(_send_one, r, payload, pem) for r in rows))
    for r, status in zip(rows, results):
        if status in (404, 410):  # unsubscribed or expired on the phone
            db.delete(r)
    db.commit()
    return sum(s is None for s in results)


def trade_message(signal: dict, lots: Optional[float] = None) -> dict:
    """The notification of a new trade, one line: "🟢 XAU/USD (BUY) — Entry: 2745.50 | LOT: 0.07 | TP: 2760.00 | SL: 2738.00".
    The pair and side are the title, the levels the body; LOT is the lot for the receiver's own risk (left out when unset)."""
    sym, side = signal["symbol"], signal["signalType"]
    tp = signal.get("target3") or signal.get("target2")
    try:
        dec = CONFIGS[normalize_symbol(sym)]["spec"]["decimals"]
    except KeyError:
        dec = 5
    fmt = lambda v: f"{float(v):.{dec}f}" if v is not None else "—"
    parts = [f"Entry: {fmt(signal.get('entryPrice'))}"]
    if lots:
        parts.append(f"LOT: {lots:.2f}")
    parts += [f"TP: {fmt(tp)}", f"SL: {fmt(signal.get('stopLoss'))}"]
    return {"title": f"{'🟢' if side == 'BUY' else '🔴'} {sym} ({side})", "body": " | ".join(parts),
            "tag": f"ld-{signal['id']}", "symbol": sym}


def _user_lot(u: User, signal: dict) -> Optional[float]:
    """The lot for this user's saved risk with the signal's own stop (None when no risk is set)."""
    risk = effective_risk(u.risk_usd, u.capital, u.risk_pct) or 0
    entry, sl = signal.get("entryPrice"), signal.get("stopLoss")
    if risk <= 0 or entry is None or sl is None:
        return None
    return lot_for_risk(signal["symbol"], float(entry), float(sl), risk)["lots"] or None


async def notify_trade(signal: dict) -> int:
    """Pushes a new trade once to every approved, active account (claimed by setup id first, like the Telegram send)."""
    with SessionLocal() as db:
        db.add(PushSent(id=str(signal["id"])))
        try:
            db.commit()
        except IntegrityError:
            db.rollback()
            return 0  # already pushed (another tick or worker)
        rows = db.scalars(select(PushSubscription).join(User, User.id == PushSubscription.user_id)
                          .where(User.active.is_(True), or_(User.status.is_(None), User.status != "pending"))).all()
        by_user: dict[int, list[PushSubscription]] = {}
        for r in rows:
            by_user.setdefault(r.user_id, []).append(r)
        sent = 0
        for uid, subs in by_user.items():  # each account gets the lot for its own risk
            sent += await send_push(db, subs, trade_message(signal, _user_lot(db.get(User, uid), signal)))
        return sent


async def push_setup(symbol: str) -> str:
    """At a candle close: pushes the fresh signal of `symbol` when the three agents agree (the same vote as Telegram)."""
    from .strategies.exunu import run_exunu, to_ai_signal

    res = await run_exunu(symbol)
    r = res["strategy"]
    if not (r["market"]["isOpen"] and r["status"] == "SIGNAL" and r["canNotify"] and r["setup"]):
        return "no signal to push"
    if not (res.get("consensus") or {}).get("approved"):
        return "agents did not agree"
    n = await notify_trade(to_ai_signal(res))
    return f"pushed to {n} device(s)"
