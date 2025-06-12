import pytest
from datetime import date
from LifeLog.config import Settings
from LifeLog.enrichment.timeline_generator import run_enrichment_for_day
from LifeLog.database import get_connection
import uuid

def test_enrichment_updates_db(tmp_path, monkeypatch):
    # Use temporary database
    db_path = tmp_path / "test_lifelog.db"
    monkeypatch.setattr("LifeLog.database.DB_PATH", db_path)
    
    from LifeLog.database import init_database
    init_database()
    
    # Setup: Insert a dummy unenriched event for a test day
    test_day = date(2025, 5, 22)
    test_event_id = str(uuid.uuid4())
    settings = Settings()
    
    with get_connection() as conn:
        cur = conn.cursor()
        cur.execute(
            """
            INSERT INTO timeline_events (event_id, start_time, end_time, duration_s, source, app_name, window_title, category, notes, last_modified)
            VALUES (?, '2025-05-22T10:00:00Z', '2025-05-22T11:00:00Z', 3600, 'test', 'TestApp', 'TestTitle', NULL, NULL, CURRENT_TIMESTAMP)
            """,
            (test_event_id,)
        )
        conn.commit()
    
    # Patch LLM to return a fixed enrichment
    from LifeLog.enrichment.timeline_generator import EnrichedTimelineEntry
    from datetime import datetime, timezone
    
    def mock_invoke_llm(day, prompt, settings):
        return [
            EnrichedTimelineEntry(
                event_id=test_event_id,
                start=datetime(2025, 5, 22, 10, 0, 0, tzinfo=timezone.utc),
                end=datetime(2025, 5, 22, 11, 0, 0, tzinfo=timezone.utc),
                activity="TestCat",
                project="TestProj",
                notes="TestNote"
            )
        ]
    
    monkeypatch.setattr(
        "LifeLog.enrichment.timeline_generator._invoke_llm_and_parse",
        mock_invoke_llm
    )
    
    # Run enrichment
    run_enrichment_for_day(test_day, settings)
    
    # Check DB for update
    with get_connection() as conn:
        cur = conn.cursor()
        cur.execute("SELECT category, project, notes FROM timeline_events WHERE event_id = ?", (test_event_id,))
        row = cur.fetchone()
        assert row == ("TestCat", "TestProj", "TestNote")
