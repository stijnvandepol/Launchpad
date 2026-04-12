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
    _migrate(engine)
    _engines[path] = engine
    return engine


def _migrate(engine) -> None:
    """Apply incremental schema migrations for columns added after initial release."""
    with engine.connect() as conn:
        # container_port added in v2 — default 8080 for all existing projects
        existing = {row[1] for row in conn.execute(text("PRAGMA table_info(project)"))}
        if "container_port" not in existing:
            conn.execute(text("ALTER TABLE project ADD COLUMN container_port INTEGER NOT NULL DEFAULT 8080"))
            conn.commit()


def get_session(path: str) -> Session:
    """Return a new SQLModel session for the given DB path."""
    return Session(get_engine(path))
