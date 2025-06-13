import uuid
from datetime import datetime, timezone, date
import duckdb
import pytest
from LifeLog.database import init_database, get_connection, DB_PATH
from LifeLog.enrichment import timeline_generator as tg
from LifeLog.config import Settings


def test_enrichment_updates_db(tmp_path, monkeypatch):
    db_path = tmp_path / "lifelog.db"
    monkeypatch.setattr("LifeLog.database.DB_PATH", db_path)
    init_database()
    with duckdb.connect(str(db_path)) as conn:
        conn.execute(
            """
            INSERT INTO timeline_events (event_id, start_time, end_time, duration_s, source, app_name, window_title, last_modified)
            VALUES ('11111111-1111-1111-1111-111111111111', '2025-06-01 10:00:00', '2025-06-01 10:05:00', 300, 'test', 'TestApp', 'Test Window', '2025-06-01 10:05:00')
            """
        )

    def fake_llm(day, prompt, settings):
        return [tg.EnrichedTimelineEntry(
            event_id="11111111-1111-1111-1111-111111111111",
            start=datetime(2025,6,1,10,0,tzinfo=timezone.utc),
            end=datetime(2025,6,1,10,5,tzinfo=timezone.utc),
            activity="Coding",
            project="LifeLog",
            notes="Working"
        )]

    monkeypatch.setattr(tg, "_invoke_llm_and_parse", fake_llm)
    settings = Settings()
    count = tg.run_enrichment_for_day(date(2025,6,1), settings)
    assert count == 1
    with duckdb.connect(str(db_path)) as conn:
        row = conn.execute("SELECT category, project, notes FROM timeline_events WHERE event_id='11111111-1111-1111-1111-111111111111'").fetchone()
        assert row[0] == 'Coding'
        assert row[1] == 'LifeLog'
        assert row[2] == 'Working'
