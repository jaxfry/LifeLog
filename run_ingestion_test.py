import logging
from datetime import datetime, timedelta, timezone

from backend.app.core.db import get_db_connection
from backend.app.core.settings import settings
from backend.app.ingestion.activitywatch import ingest_activitywatch_data

logging.basicConfig(level=logging.INFO)

if __name__ == "__main__":
    print("--- Running Standalone Ingestion Test ---")
    
    # Define a time window to test, e.g., the last 6 hours
    end_utc = datetime.now(timezone.utc)
    start_utc = end_utc - timedelta(hours=6)
    
    print(f"Testing window: {start_utc} -> {end_utc}")
    
    con = get_db_connection()
    try:
        # Ingest data
        ingest_activitywatch_data(con, settings, start_utc, end_utc)
        
        # Process timeline
        from backend.app.processing.timeline import process_pending_events_sync
        process_pending_events_sync(con, settings)

        print("\n--- TEST RUN FINISHED ---")
        
        # Check results
        event_result = con.execute("SELECT count(*) FROM events").fetchone()
        event_count = event_result[0] if event_result else 0
        
        timeline_result = con.execute("SELECT count(*) FROM timeline_entries").fetchone()
        timeline_entry_count = timeline_result[0] if timeline_result else 0

        project_result = con.execute("SELECT count(*) FROM projects").fetchone()
        project_count = project_result[0] if project_result else 0

        print(f"Events in DB: {event_count}")
        print(f"Timeline entries in DB: {timeline_entry_count}")
        print(f"Projects in DB: {project_count}")
        
    except Exception as e:
        print(f"An error occurred: {e}")
        con.rollback()
    finally:
        con.close()