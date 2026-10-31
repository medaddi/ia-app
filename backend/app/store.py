"""App parameters stored in the `settings` table (key → JSON), with defaults."""

import copy

from sqlalchemy.orm import Session

from .config import settings as env
from .strategies.alexg.config import ALEXG_CONFIGS
from .models import Setting

DEFAULTS: dict[str, dict] = {
    "app": {"appName": "LiquidityDissection", "defaultLanguage": "fr", "theme": "dark", "requireAuth": True},
    "telegram": {
        "botToken": "", "chatId": "", "enabled": True, "minConfidence": 75, "assets": ["XAU/USD", *ALEXG_CONFIGS],
        "protectContent": True, "personalOffsets": True,
    },
}


OLD_DEFAULT_ASSETS = [["EUR/USD", "XAU/USD"], ["EUR/USD", "GBP/USD", "XAU/USD"]]


def get_setting(db: Session, key: str) -> dict:
    row = db.get(Setting, key)
    value = copy.deepcopy(DEFAULTS.get(key, {}))
    if row and isinstance(row.value, dict):
        value.update(row.value)
    if key == "telegram":
        # Environment variables win when the database has no value
        value["botToken"] = value.get("botToken") or env.telegram_bot_token
        value["chatId"] = value.get("chatId") or env.telegram_chat_id
        # A list saved before the FXAlexG pairs existed = "every instrument": send the new pairs too
        if sorted(value.get("assets") or []) in OLD_DEFAULT_ASSETS:
            value["assets"] = list(DEFAULTS["telegram"]["assets"])
    return value


def set_setting(db: Session, key: str, patch: dict) -> dict:
    row = db.get(Setting, key)
    current = dict(row.value) if row and isinstance(row.value, dict) else {}
    allowed = DEFAULTS.get(key)
    for k, v in patch.items():
        if allowed is None or k in allowed:
            current[k] = v
    if row:
        row.value = current
    else:
        db.add(Setting(key=key, value=current))
    db.commit()
    return get_setting(db, key)


def public_telegram(cfg: dict) -> dict:
    """Telegram settings without the full bot token."""
    token = cfg.get("botToken") or ""
    return {**cfg, "botToken": "", "botTokenMasked": f"{token[:6]}…{token[-4:]}" if len(token) > 12 else "", "hasBotToken": bool(token)}
