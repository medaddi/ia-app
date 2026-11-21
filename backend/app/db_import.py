"""
One-time copy of the previous database (Neon, until 2026-11-20) into the active one (Supabase).

The Vercel backend still holds Neon's address (DATABASE_URL / DATABASE_POSTGRES_URL, set by the Neon integration), so the
copy runs inside the app and nobody handles the password. It REPLACES the active tables' rows with the old ones (the new
database only holds what was created since the switch: the bootstrap admin, a session, two settings), table by table in
foreign-key order, in one transaction, then moves each id sequence past the copied ids. A dry run only counts the rows.
"""

import os

from sqlalchemy import Integer, create_engine, inspect, select, text

from .config import settings
from .db import Base, engine

SOURCE_KEYS = ("OLD_DATABASE_URL", "DATABASE_URL", "DATABASE_POSTGRES_URL")


def _norm(url: str) -> str:
    url = url.strip()
    if url.startswith("postgres://"):
        url = "postgresql://" + url[len("postgres://"):]
    return url


def source_url() -> str | None:
    """The old database's address: the first of SOURCE_KEYS that is set and is not the active database."""
    active = _norm(settings.database_url or "")
    for k in SOURCE_KEYS:
        v = os.environ.get(k)
        if v and _norm(v) != active:
            return _norm(v)
    return None


def import_old(src_url: str | None = None, dry_run: bool = False) -> dict:
    from . import models  # noqa: F401  (registers the tables)

    src_url = src_url or source_url()
    if not src_url:
        return {"ok": False, "error": "No previous database address is configured"}
    src = create_engine(src_url, pool_pre_ping=True, connect_args={"connect_timeout": 15} if src_url.startswith("postgresql") else {})
    tables = Base.metadata.sorted_tables
    counts: dict[str, int] = {}
    try:
        with src.connect() as s:
            have = set(inspect(s).get_table_names())
            rows: dict[str, list[dict]] = {}
            for t in tables:
                if t.name not in have:
                    continue
                cols = {c["name"] for c in inspect(s).get_columns(t.name)} & set(t.c.keys())
                data = [dict(r._mapping) for r in s.execute(select(*[t.c[c] for c in cols]))]
                rows[t.name] = data
                counts[t.name] = len(data)
    except Exception as e:  # the old database refuses (quota, address, network)
        return {"ok": False, "error": str(e).splitlines()[0][:300]}
    finally:
        src.dispose()
    if dry_run:
        return {"ok": True, "dryRun": True, "rows": counts}
    with engine.begin() as d:
        for t in reversed(tables):
            if t.name in rows:
                d.execute(t.delete())
        for t in tables:
            if rows.get(t.name):
                d.execute(t.insert(), rows[t.name])
        if d.dialect.name == "postgresql":
            for t in tables:
                pk = [c for c in t.primary_key.columns if isinstance(c.type, Integer)]
                if rows.get(t.name) and len(pk) == 1:
                    col = pk[0].name
                    seq = d.execute(text("SELECT pg_get_serial_sequence(:t, :c)"), {"t": t.name, "c": col}).scalar()
                    if seq:
                        d.execute(text(f'SELECT setval(:s, (SELECT COALESCE(MAX("{col}"), 1) FROM "{t.name}"))'), {"s": seq})
    return {"ok": True, "rows": counts}
