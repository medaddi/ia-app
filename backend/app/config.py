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


class Settings:
    data_dir: str = os.environ.get("DATA_DIR", str(BACKEND_DIR / "data"))
    # SQLite file locally; set DATABASE_URL to a Postgres URL (Neon / Supabase) in production
    database_url: str = os.environ.get("DATABASE_URL", "")
    cors_origins: list[str] = [o.strip() for o in os.environ.get("CORS_ORIGINS", "http://localhost:3000,http://localhost:5173").split(",") if o.strip()]
    admin_username: str = os.environ.get("ADMIN_USERNAME", "admin")
    admin_access_code: str = os.environ.get("ADMIN_ACCESS_CODE", "")
    session_days: int = int(os.environ.get("SESSION_DAYS", "30"))
    telegram_bot_token: str = os.environ.get("TELEGRAM_BOT_TOKEN", "")
    telegram_chat_id: str = os.environ.get("TELEGRAM_CHAT_ID", "")
    gemini_api_key: str = os.environ.get("GEMINI_API_KEY", "")
    gemini_model: str = os.environ.get("GEMINI_MODEL", "gemini-2.5-flash")
    scheduler_enabled: bool = _bool("SCHEDULER_ENABLED", True)
    telegram_polling: bool = _bool("TELEGRAM_POLLING", True)

    @property
    def db_url(self) -> str:
        url = self.database_url
        if not url:
            Path(self.data_dir).mkdir(parents=True, exist_ok=True)
            return f"sqlite:///{Path(self.data_dir) / 'exunu.db'}"
        # Render / Heroku style URLs
        if url.startswith("postgres://"):
            url = "postgresql://" + url[len("postgres://"):]
        return url


settings = Settings()
