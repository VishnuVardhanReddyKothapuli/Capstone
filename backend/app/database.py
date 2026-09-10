"""SQLAlchemy engine, session factory and declarative base."""

from __future__ import annotations

import logging
from collections.abc import Iterator

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.config import settings

logger = logging.getLogger(__name__)

_is_sqlite = settings.DATABASE_URL.startswith("sqlite")
_db_url = settings.DATABASE_URL
if _db_url.startswith("postgres://"):
    _db_url = _db_url.replace("postgres://", "postgresql://", 1)

engine = create_engine(
    _db_url,
    # FastAPI runs sync endpoints in a threadpool, so a SQLite connection can be
    # touched by a different thread than the one that opened it.
    connect_args={"check_same_thread": False} if _is_sqlite else {},
    pool_pre_ping=True,
    future=True,
)

SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


def get_db() -> Iterator[Session]:
    """FastAPI dependency: one session per request, always closed."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# Nullable columns added after the first release. `create_all` only ever creates
# missing *tables*, so without this an existing sentinal.db would 500 on every
# query that touches them.
_LATER_COLUMNS: dict[str, dict[str, str]] = {
    "checks": {
        "explanation_json": "TEXT",
        "explained_at": "DATETIME",
        "uploaded_by": "VARCHAR(64) DEFAULT 'anonymous'",
    },
    "users": {"email": "VARCHAR(254)"},
}


def _add_missing_columns() -> None:
    """Bring an existing database up to the current model, additively.

    Only ever adds nullable columns from the hardcoded table above — no data is
    rewritten and nothing is dropped, so it is safe to run on every startup.
    """
    inspector = inspect(engine)
    tables = set(inspector.get_table_names())
    for table, columns in _LATER_COLUMNS.items():
        if table not in tables:
            continue  # create_all just built it with every column
        existing = {column["name"] for column in inspector.get_columns(table)}
        for name, ddl_type in columns.items():
            if name in existing:
                continue
            with engine.begin() as connection:
                connection.execute(text(f"ALTER TABLE {table} ADD COLUMN {name} {ddl_type}"))
            logger.info("Added missing column %s.%s", table, name)


def init_db() -> None:
    """Create any missing tables. Import models first so they are registered."""
    from app import models  # noqa: F401  (populates Base.metadata)

    Base.metadata.create_all(bind=engine)
    _add_missing_columns()
