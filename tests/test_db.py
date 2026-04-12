def test_get_engine_creates_db_file(tmp_path):
    from app.db import get_engine
    db_path = str(tmp_path / "test.db")
    engine = get_engine(db_path)
    assert engine is not None
    # Second call returns same engine (cached)
    assert get_engine(db_path) is get_engine(db_path)

def test_get_engine_enables_wal_mode(tmp_path):
    from app.db import get_engine
    from sqlalchemy import text
    db_path = str(tmp_path / "test.db")
    engine = get_engine(db_path)
    with engine.connect() as conn:
        result = conn.execute(text("PRAGMA journal_mode")).scalar()
    assert result == "wal"

def test_tables_are_created(tmp_path):
    from app.db import get_engine
    from sqlalchemy import inspect
    db_path = str(tmp_path / "test.db")
    engine = get_engine(db_path)
    inspector = inspect(engine)
    tables = inspector.get_table_names()
    assert "project" in tables
    assert "logline" in tables
