# app/db.py
from sqlalchemy import text
from sqlmodel import SQLModel, create_engine, Session
from app.models import Project, LogLine  # noqa: F401

# Cache engines by path so each DB file gets exactly one engine
_engines: dict[str, object] = {}


def get_engine(path: str):
    """Return (and cache) the SQLAlchemy engine for the given SQLite path.

    Creates tables and enables WAL mode on first call per path.
    """
    if path in _engines:
        return _engines[path]

    engine = create_engine(f"sqlite:///{path}", connect_args={"check_same_thread": False})

    with engine.connect() as conn:
        conn.execute(text("PRAGMA journal_mode=WAL"))
        conn.commit()

    SQLModel.metadata.create_all(engine)
    _engines[path] = engine
    return engine


def get_session(path: str) -> Session:
    """Return a new SQLModel session for the given DB path."""
    return Session(get_engine(path))
