"""
Web Push: notifications that reach the phone even when the app is closed (the tab is frozen or not open).
- VAPID keys are generated once and kept in the database (settings "push"), or come from VAPID_PUBLIC_KEY / VAPID_PRIVATE_KEY.
- Each browser that turns notifications on stores its push subscription (PushSubscription).
Nothing is pushed automatically for now: the app's analysis is being rebuilt.
"""

import asyncio
import base64
import json
import os
from typing import Optional

from cryptography.hazmat.primitives import serialization
from py_vapid import Vapid01
from pywebpush import WebPushException, webpush
from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import PushSubscription, User
from .store import get_setting, set_setting

SUBJECT = os.environ.get("VAPID_SUBJECT", "mailto:alerts@liquiditydissection.app")  # contact the push services may use
TTL = 3600  # a notification older than an hour is useless: the push service may drop it after that


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
        # Urgency high: the push service delivers at once, even to a phone asleep / in battery saving (no batching)
        webpush({"endpoint": row.endpoint, "keys": {"p256dh": row.p256dh, "auth": row.auth}}, payload,
                vapid_private_key=Vapid01.from_pem(private_pem.encode()), vapid_claims={"sub": SUBJECT}, ttl=TTL, timeout=8,
                headers={"Urgency": "high"})
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
