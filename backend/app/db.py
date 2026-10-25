"""SQLAlchemy engine and session. SQLite file locally, Postgres when DATABASE_URL is set."""

from collections.abc import Iterator

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from .config import settings

_url = settings.db_url
engine = create_engine(
    _url,
    pool_pre_ping=True,
    connect_args={"check_same_thread": False} if _url.startswith("sqlite") else {},
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

    Base.metadata.create_all(engine)
    _add_missing_columns()


def _add_missing_columns() -> None:
    """create_all() never alters existing tables: add columns introduced after the first deploy."""
    from sqlalchemy import inspect, text

    added = {"users": {"default_lot": "FLOAT", "daily_loss_limit": "FLOAT"}}
    insp = inspect(engine)
    with engine.begin() as conn:
        for table, cols in added.items():
            have = {c["name"] for c in insp.get_columns(table)}
            for name, sql_type in cols.items():
                if name not in have:
                    conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {name} {sql_type}"))
