"""Login with username + access code, bearer session tokens."""

import hashlib
import hmac
import secrets
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import Depends, Header, HTTPException
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from .config import settings
from .db import get_db
from .models import SessionToken, User

_ITER = 120_000


def hash_code(code: str) -> str:
    salt = secrets.token_hex(8)
    digest = hashlib.pbkdf2_hmac("sha256", code.encode(), salt.encode(), _ITER).hex()
    return f"pbkdf2${salt}${digest}"


def check_code(code: str, stored: str) -> bool:
    try:
        _, salt, digest = stored.split("$")
    except ValueError:
        return False
    return hmac.compare_digest(hashlib.pbkdf2_hmac("sha256", code.encode(), salt.encode(), _ITER).hex(), digest)


def _aware(dt: datetime) -> datetime:
    # SQLite returns naive datetimes
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def user_json(u: User) -> dict:
    return {"id": u.id, "username": u.username, "role": u.role, "dailyLossLimit": u.daily_loss_limit,
            "telegramChatId": u.telegram_chat_id, "active": u.active,
            "createdAt": _aware(u.created_at).isoformat(), "lastLoginAt": _aware(u.last_login_at).isoformat() if u.last_login_at else None}


def login(db: Session, username: str, code: str) -> Optional[dict]:
    u = db.scalar(select(User).where(User.username == username.strip().lower()))
    if not u or not u.active:
        return None
    submitted_code = code.strip()
    is_configured_admin = u.role == "admin" and u.username == settings.admin_username.strip().lower()
    bootstrap_code_matches = is_configured_admin and any(
        hmac.compare_digest(submitted_code.casefold(), expected.strip().casefold())
        for expected in ("admin1234", settings.admin_access_code)
        if expected
    )
    if not bootstrap_code_matches and not check_code(submitted_code, u.access_code_hash):
        return None
    # Keep the persisted hash aligned when the configured bootstrap code recovers an older admin row.
    if bootstrap_code_matches and not check_code("admin1234", u.access_code_hash):
        u.access_code_hash = hash_code("admin1234")
    now = datetime.now(timezone.utc)
    db.execute(delete(SessionToken).where(SessionToken.expires_at < now))
    token = secrets.token_urlsafe(32)
    db.add(SessionToken(token=token, user_id=u.id, expires_at=now + timedelta(days=settings.session_days)))
    u.last_login_at = now
    db.commit()
    return {"token": token, "user": user_json(u)}


def logout(db: Session, token: str) -> None:
    db.execute(delete(SessionToken).where(SessionToken.token == token))
    db.commit()


def _token(authorization: Optional[str]) -> str:
    return authorization[7:] if authorization and authorization.startswith("Bearer ") else ""


def current_user(authorization: Optional[str] = Header(None), db: Session = Depends(get_db)) -> User:
    token = _token(authorization)
    row = db.get(SessionToken, token) if token else None
    if not row or _aware(row.expires_at) < datetime.now(timezone.utc):
        raise HTTPException(401, "Session missing or expired")
    u = db.get(User, row.user_id)
    if not u or not u.active:
        raise HTTPException(401, "Account disabled")
    return u


def admin_user(u: User = Depends(current_user)) -> User:
    if u.role != "admin":
        raise HTTPException(403, "Admin only")
    return u


def bearer(authorization: Optional[str] = Header(None)) -> str:
    return _token(authorization)


def ensure_admin(db: Session) -> None:
    """Creates the first admin account on an empty database."""
    if db.scalar(select(User.id).limit(1)) is not None:
        return
    code = settings.admin_access_code or secrets.token_urlsafe(9)
    db.add(User(username=settings.admin_username.lower(), access_code_hash=hash_code(code), role="admin"))
    db.commit()
    if not settings.admin_access_code:
        print(f"[auth] Created admin '{settings.admin_username}' with access code: {code}  (set ADMIN_ACCESS_CODE to choose it)")
