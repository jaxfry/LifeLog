import duckdb
from backend.app.core.settings import Settings
from backend.app.processing.timeline import process_pending_events_sync

def main():
    settings = Settings()
    con = duckdb.connect(database=str(settings.DB_FILE), read_only=False)
    
    print("Clearing event_state table...")
    con.execute("DELETE FROM event_state")
    
    print("Reprocessing timeline...")
    process_pending_events_sync(con, settings)
    
    print("Done.")
    con.close()

if __name__ == "__main__":
    main()