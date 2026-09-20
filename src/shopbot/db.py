"""SQLite (WAL mode) engine/session setup. Local file only (constraint C6)."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager

from sqlalchemy import event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from shopbot.config import Settings


def make_engine(settings: Settings):
    from sqlalchemy import create_engine

    connect_args = {"check_same_thread": False}
    engine = create_engine(settings.db_url(), connect_args=connect_args, future=True)

    @event.listens_for(engine, "connect")
    def _set_sqlite_pragma(dbapi_connection, _connection_record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.execute("PRAGMA busy_timeout=5000")
        cursor.close()

    return engine


class Database:
    """Thin wrapper bundling an engine + sessionmaker, created once per process
    (or once per test) so tests can use isolated in-memory/temp-file DBs."""

    def __init__(self, settings: Settings):
        self.settings = settings
        self.engine: Engine = make_engine(settings)
        self.SessionLocal: sessionmaker[Session] = sessionmaker(
            bind=self.engine, autoflush=False, expire_on_commit=False, future=True
        )

    def create_all(self) -> None:
        from shopbot.models import Base

        Base.metadata.create_all(self.engine)

    @contextmanager
    def session(self) -> Iterator[Session]:
        session = self.SessionLocal()
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()
