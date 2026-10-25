"""Settings from environment variables (a local .env file is read too). See backend/.env.example."""

import os
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent


def _load_dotenv(path: Path) -> None:
    if not path.exists():
        return
    for line in path.read_text("utf8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


_load_dotenv(BACKEND_DIR / ".env")


def _bool(name: str, default: bool) -> bool:
    v = os.environ.get(name)
    return default if v is None else v.strip().lower() in ("1", "true", "yes", "on")


# Vercel runs the API as short-lived functions: no background loops, only /tmp is writable
ON_VERCEL = bool(os.environ.get("VERCEL"))


class Settings:
    on_vercel: bool = ON_VERCEL
    data_dir: str = os.environ.get("DATA_DIR", "/tmp/exunu" if ON_VERCEL else str(BACKEND_DIR / "data"))
    # SQLite file locally; set DATABASE_URL to a Postgres URL (Neon / Supabase) in production.
    # The Vercel Neon integration names it POSTGRES_URL.
    database_url: str = os.environ.get("DATABASE_URL") or os.environ.get("POSTGRES_URL", "")
    cors_origins: list[str] = [o.strip() for o in os.environ.get("CORS_ORIGINS", "http://localhost:3000,http://localhost:5173").split(",") if o.strip()]
    admin_username: str = os.environ.get("ADMIN_USERNAME", "admin")
    # Bootstrap credential for a fresh database. Set ADMIN_ACCESS_CODE in production to override it.
    admin_access_code: str = os.environ.get("ADMIN_ACCESS_CODE") or "admin1234"
    session_days: int = int(os.environ.get("SESSION_DAYS", "30"))
    telegram_bot_token: str = os.environ.get("TELEGRAM_BOT_TOKEN", "")
    telegram_chat_id: str = os.environ.get("TELEGRAM_CHAT_ID", "")
    gemini_api_key: str = os.environ.get("GEMINI_API_KEY", "")
    gemini_model: str = os.environ.get("GEMINI_MODEL", "gemini-2.5-flash")
    # Always-on server: in-process candle-close scheduler and Telegram long polling.
    # Serverless (Vercel): an external pinger calls /api/cron/tick and Telegram uses a webhook instead.
    scheduler_enabled: bool = _bool("SCHEDULER_ENABLED", not ON_VERCEL)
    telegram_polling: bool = _bool("TELEGRAM_POLLING", not ON_VERCEL)
    cron_secret: str = os.environ.get("CRON_SECRET", "")
    telegram_webhook_secret: str = os.environ.get("TELEGRAM_WEBHOOK_SECRET", "")
    telegram_webhook_url: str = os.environ.get("TELEGRAM_WEBHOOK_URL", "")

    @property
    def db_url(self) -> str:
        url = self.database_url
        if not url:
            if self.on_vercel:
                raise RuntimeError("Set DATABASE_URL (or POSTGRES_URL) to a persistent PostgreSQL database on Vercel")
            Path(self.data_dir).mkdir(parents=True, exist_ok=True)
            return f"sqlite:///{Path(self.data_dir) / 'exunu.db'}"
        # Render / Heroku style URLs
        if url.startswith("postgres://"):
            url = "postgresql://" + url[len("postgres://"):]
        return url


settings = Settings()
