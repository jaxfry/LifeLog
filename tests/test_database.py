import pytest
from LifeLog.database import init_database, get_connection
import duckdb
import os
from pathlib import Path

def test_database_schema_creation(tmp_path, monkeypatch):
    # Patch DB_PATH to use a temporary location
    db_path = tmp_path / "lifelog.db"
    monkeypatch.setattr("LifeLog.database.DB_PATH", db_path)
    init_database()
    assert db_path.exists()
    with duckdb.connect(str(db_path)) as conn:
        tables = set(row[0] for row in conn.execute("SHOW TABLES").fetchall())
        assert "timeline_events" in tables
        assert "daily_summaries" in tables
        assert "metadata" in tables
        # Check columns for timeline_events
        columns = set(row[0] for row in conn.execute("DESCRIBE timeline_events").fetchall())
        assert "event_id" in columns
        assert "start_time" in columns
        assert "date" in columns
        assert "duration_s" in columns
        assert "source" in columns
        assert "app_name" in columns
        assert "window_title" in columns
        assert "category" in columns
        assert "notes" in columns
        assert "last_modified" in columns

def test_basic_insert_and_query(tmp_path, monkeypatch):
    db_path = tmp_path / "lifelog.db"
    monkeypatch.setattr("LifeLog.database.DB_PATH", db_path)
    init_database()
    with duckdb.connect(str(db_path)) as conn:
        conn.execute("""
            INSERT INTO timeline_events (event_id, start_time, end_time, duration_s, source, app_name, window_title, last_modified)
            VALUES ('123e4567-e89b-12d3-a456-426614174000', '2025-06-12 10:00:00', '2025-06-12 11:00:00', 3600, 'test', 'TestApp', 'Test Window', '2025-06-12 11:01:00')
        """)
        result = conn.execute("SELECT * FROM timeline_events WHERE event_id = '123e4567-e89b-12d3-a456-426614174000'").fetchone()
        assert result is not None
        # DuckDB returns UUID as uuid.UUID object, so compare as string
        assert str(result[0]) == '123e4567-e89b-12d3-a456-426614174000'
