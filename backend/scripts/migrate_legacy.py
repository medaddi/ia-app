"""
Imports the old Node app's data/db.json into the new database (SQLite or DATABASE_URL Postgres):
users (access codes are hashed), Telegram activation codes, subscribers with their capital/risk,
Telegram settings and app settings. Existing rows are kept; running it twice is safe.

  python -m scripts.migrate_legacy ../data/db.json
"""

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

from app.auth import hash_code
from app.db import SessionLocal, init_db
from app.models import ActivationKey, Subscriber, User
from app.store import set_setting


def ms(v):
    try:
        return datetime.fromtimestamp(int(v) / 1000, timezone.utc) if v else None
    except (TypeError, ValueError, OSError, OverflowError):
        return None


def main(path: str) -> None:
    data = json.loads(Path(path).read_text("utf8"))
    init_db()
    counts = {"users": 0, "codes": 0, "subscribers": 0}
    with SessionLocal() as db:
        for u in data.get("users") or []:
            name = str(u.get("username") or "").strip().lower()
            code = str(u.get("accessCode") or "").strip()
            if not name or not code or db.query(User).filter_by(username=name).first():
                continue
            db.add(User(username=name, access_code_hash=hash_code(code), role="admin" if u.get("role") == "admin" else "user",
                        created_at=ms(u.get("createdAt")) or datetime.now(timezone.utc), last_login_at=ms(u.get("lastLoginAt"))))
            counts["users"] += 1

        for key, k in (data.get("activationKeys") or {}).items():
            code = str(k.get("code") or key).strip()
            if not code or db.get(ActivationKey, code):
                continue
            db.add(ActivationKey(code=code, label=str(k.get("label") or ""), duration_hours=int(k.get("durationHours") or 720),
                                 multi_use=bool(k.get("multiUserAllowed") or k.get("isPermanent")), used_count=1 if k.get("used") else 0,
                                 revoked=str(k.get("status") or "ACTIVE").upper() in ("REVOKED", "DISABLED"),
                                 created_at=ms(k.get("createdAt")) or datetime.now(timezone.utc)))
            counts["codes"] += 1

        for chat_id, s in (data.get("chatSubscribers") or {}).items():
            cid = str(s.get("chatId") or chat_id)
            if db.get(Subscriber, cid):
                continue
            db.add(Subscriber(chat_id=cid, first_name=str(s.get("firstName") or ""), code=s.get("code"), activated_at=ms(s.get("activatedAt")),
                              expires_at=ms(s.get("expiresAt")), capital=float(s.get("capital") or 0), risk_pct=float(s.get("riskPercent") or 1)))
            counts["subscribers"] += 1
        db.commit()

        tg = data.get("telegramConfig") or {}
        set_setting(db, "telegram", {k: v for k, v in {"botToken": tg.get("botToken"), "chatId": str(tg.get("chatId") or ""), "enabled": tg.get("enabled"),
                                                       "minConfidence": tg.get("minConfidence")}.items() if v not in (None, "")})
        app = data.get("systemSettings") or {}
        set_setting(db, "app", {k: app[k] for k in ("appName", "defaultLanguage", "theme", "requireAuth") if k in app})
    print(f"Imported {counts['users']} users, {counts['codes']} activation codes, {counts['subscribers']} subscribers, Telegram and app settings.")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "../data/db.json")
