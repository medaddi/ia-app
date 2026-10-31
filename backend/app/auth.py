"""Login with username + access code (or the password chosen at sign-up), bearer session tokens.
Self sign-up creates a "pending" account: it can log in but only sees the waiting page until an admin approves it."""

import hashlib
import hmac
import re
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
    from .trading import effective_risk

    return {"id": u.id, "username": u.username, "firstName": u.first_name, "lastName": u.last_name, "status": u.status or "approved", "role": u.role, "dailyLossLimit": u.daily_loss_limit, "riskUsd": u.risk_usd,
            "capital": u.capital or None, "riskPct": u.risk_pct if (u.capital or 0) > 0 else None,
            "effectiveRisk": effective_risk(u.risk_usd, u.capital, u.risk_pct), "telegramLinked": bool(u.telegram_chat_id),
            "telegramChatId": u.telegram_chat_id, "active": u.active,
            "createdAt": _aware(u.created_at).isoformat(), "lastLoginAt": _aware(u.last_login_at).isoformat() if u.last_login_at else None}


def login(db: Session, username: str, code: str) -> Optional[dict]:
    u = db.scalar(select(User).where(User.username == username.strip().lower()))
    # Only the code saved for this account works (ADMIN_ACCESS_CODE is just the first admin's starting code)
    if not u or not u.active or not check_code(code.strip(), u.access_code_hash):
        return None
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


def session_user(authorization: Optional[str] = Header(None), db: Session = Depends(get_db)) -> User:
    """The logged-in account, approved or still pending (only /auth/me and logout accept a pending one)."""
    token = _token(authorization)
    row = db.get(SessionToken, token) if token else None
    if not row or _aware(row.expires_at) < datetime.now(timezone.utc):
        raise HTTPException(401, "Session missing or expired")
    u = db.get(User, row.user_id)
    if not u or not u.active:
        raise HTTPException(401, "Account disabled")
    return u


def current_user(u: User = Depends(session_user)) -> User:
    if (u.status or "approved") != "approved":
        raise HTTPException(403, "Account waiting for admin approval")
    return u


USERNAME_RE = re.compile(r"^[a-z0-9._-]{3,32}$")
NAME_RE = re.compile(r"^[^\W\d_][^\W\d_ '\-]*(?:[ '\-][^\W\d_]+)*$", re.UNICODE)  # letters, single spaces / hyphens / apostrophes


def password_problems(password: str, username: str = "") -> list[str]:
    """What a sign-up password is missing (empty = strong enough): 10+ characters, upper and lower case, a digit,
    a symbol, no spaces, and not built on the username."""
    p = password or ""
    out = []
    if len(p) < 10:
        out.append("at least 10 characters")
    if not re.search(r"[a-z]", p):
        out.append("a lowercase letter")
    if not re.search(r"[A-Z]", p):
        out.append("an uppercase letter")
    if not re.search(r"\d", p):
        out.append("a digit")
    if not re.search(r"[^A-Za-z0-9]", p):
        out.append("a symbol")
    if re.search(r"\s", p):
        out.append("no spaces")
    if username and len(username) >= 3 and username.lower() in p.lower():
        out.append("not containing the username")
    return out


def register(db: Session, first: str, last: str, username: str, password: str) -> dict:
    """Creates a pending account and logs it in (it sees the waiting page until an admin approves it)."""
    name = username.strip().lower()
    first, last = " ".join(first.split()), " ".join(last.split())
    if not USERNAME_RE.match(name):
        raise HTTPException(400, "Username: 3 to 32 characters, letters, digits, dot, dash or underscore")
    for label, v in (("First name", first), ("Last name", last)):
        if not (1 <= len(v) <= 64) or not NAME_RE.match(v):
            raise HTTPException(400, f"{label}: letters only")
    problems = password_problems(password, name)
    if problems:
        raise HTTPException(400, "Password needs " + ", ".join(problems))
    if db.scalar(select(User.id).where(User.username == name)):
        raise HTTPException(409, "This username is taken")
    db.add(User(username=name, first_name=first, last_name=last, access_code_hash=hash_code(password), role="user", status="pending"))
    db.commit()
    out = login(db, name, password)
    assert out
    return out


def admin_user(u: User = Depends(current_user)) -> User:
    if u.role != "admin":
        raise HTTPException(403, "Admin only")
    return u


def bearer(authorization: Optional[str] = Header(None)) -> str:
    return _token(authorization)


def ensure_admin(db: Session) -> None:
    """Creates the first admin account on an empty database. ADMIN_RESET=true resets that admin's code to ADMIN_ACCESS_CODE."""
    if db.scalar(select(User.id).limit(1)) is not None:
        if settings.admin_reset:
            admin = db.scalar(select(User).where(User.username == settings.admin_username.lower()))
            if admin:
                admin.access_code_hash, admin.role, admin.active = hash_code(settings.admin_access_code), "admin", True
                db.commit()
                print(f"[auth] ADMIN_RESET: access code of '{admin.username}' reset to ADMIN_ACCESS_CODE; remove ADMIN_RESET now")
        return
    code = settings.admin_access_code or secrets.token_urlsafe(9)
    db.add(User(username=settings.admin_username.lower(), access_code_hash=hash_code(code), role="admin"))
    db.commit()
    if not settings.admin_access_code:
        print(f"[auth] Created admin '{settings.admin_username}' with access code: {code}  (set ADMIN_ACCESS_CODE to choose it)")
