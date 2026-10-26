"""SQLAlchemy engine and session. SQLite file locally, Postgres when DATABASE_URL is set."""

from collections.abc import Iterator

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from .config import settings

_url = settings.db_url
_serverless_postgres = settings.on_vercel and _url.startswith("postgresql")
_engine_options = {"pool_pre_ping": True}
if _url.startswith("sqlite"):
    _engine_options["connect_args"] = {"check_same_thread": False}
elif _serverless_postgres:
    # Reuse one connection per warm Vercel function and avoid burst connections during scale-out.
    _engine_options.update(pool_size=1, max_overflow=0, pool_timeout=10, pool_recycle=300)
engine = create_engine(
    _url,
    **_engine_options,
)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


def get_db() -> Iterator[Session]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db() -> None:
    from . import models  # noqa: F401  (registers the tables)

    # Vercel may start several cold functions together. Serialize the idempotent schema setup
    # so they do not race while creating tables or adding columns in the shared Postgres DB.
    with engine.begin() as conn:
        if conn.dialect.name == "postgresql":
            conn.execute(text("SELECT pg_advisory_xact_lock(72830102026)"))
        Base.metadata.create_all(conn)
        _add_missing_columns(conn)


def _add_missing_columns(conn) -> None:
    """create_all() never alters existing tables: add columns introduced after the first deploy."""
    added = {"users": {"default_lot": "FLOAT", "daily_loss_limit": "FLOAT", "risk_usd": "FLOAT"},
             "subscribers": {"muted": "BOOLEAN DEFAULT FALSE", "risk_usd": "FLOAT"}}
    insp = inspect(conn)
    for table, cols in added.items():
        have = {c["name"] for c in insp.get_columns(table)}
        for name, sql_type in cols.items():
            if name not in have:
                conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {name} {sql_type}"))
