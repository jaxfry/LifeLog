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
        con.begin()
        # Use the correct function from activitywatch.py
        ingest_activitywatch_data(con, settings, start_utc, end_utc)
        print("\n--- TEST RUN FINISHED ---")
        
        # Check results
        result = con.execute("SELECT count(*) FROM events").fetchone()
        event_count = result[0] if result else 0
        print(f"Events in DB: {event_count}")
        
        print("\nRolling back transaction to keep DB clean for next test.")
        con.rollback()
        
    except Exception as e:
        print(f"An error occurred: {e}")
        con.rollback()
    finally:
        con.close()