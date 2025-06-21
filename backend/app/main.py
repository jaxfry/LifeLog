#!/usr/bin/env python3
"""
Main entry point for the LifeLog system.
"""
import sys
import logging

def main():
    """Main CLI entry point."""
    if len(sys.argv) < 2:
        print_usage()
        return
    
    command = sys.argv[1]
    
    if command == "init-db":
        from backend.app.core.db import initialize_database
        print("Initializing database...")
        initialize_database()
        print("Database initialized successfully!")
        
    elif command == "daemon":
        from backend.app.daemon.daemon import main as daemon_main
        daemon_main()
        
    elif command == "realtime-watcher":
        from backend.app.daemon.realtime_watcher import main as watcher_main
        watcher_main()
        
    elif command == "test-ingestion":
        # Useful for testing ingestion without running the full daemon
        from backend.app.core.db import get_db_connection
        from backend.app.core.settings import settings
        from backend.app.ingestion.activitywatch import ingest_aw_window
        from datetime import datetime, timezone, timedelta
        
        con = get_db_connection()
        try:
            end_utc = datetime.now(timezone.utc)
            start_utc = end_utc - timedelta(hours=2)
            print(f"Testing ingestion from {start_utc} to {end_utc}")
            ingest_aw_window(con, settings, start_utc, end_utc)
            print("Ingestion test completed!")
        finally:
            con.close()
            
    elif command == "test-processing":
        # Test the timeline processing
        from backend.app.core.db import get_db_connection
        from backend.app.core.settings import settings
        from backend.app.processing.timeline import process_pending_events_sync
        
        con = get_db_connection()
        try:
            print("Testing timeline processing...")
            process_pending_events_sync(con, settings)
            print("Processing test completed!")
        finally:
            con.close()
            
    elif command == "process-now":
        # NEW COMMAND FOR ON-DEMAND PROCESSING
        from backend.app.core.db import get_db_connection
        from backend.app.core.settings import settings
        from backend.app.processing.timeline import process_pending_events_sync
        
        con = get_db_connection()
        try:
            print("Starting on-demand timeline processing...")
            print("This will process all pending events and may take a moment.")
            process_pending_events_sync(con, settings)
            print("On-demand processing complete!")
        finally:
            con.close()

    elif command == "ingest":
        # Command to ingest data for a specific date or days ago
        from backend.app.core.db import get_db_connection
        from backend.app.core.settings import settings
        from backend.app.ingestion.activitywatch import ingest_aw_window
        from datetime import datetime, timezone, timedelta
        from zoneinfo import ZoneInfo
        import argparse

        parser = argparse.ArgumentParser(prog="ingest")
        parser.add_argument("--date", type=str, help="Specific date to ingest in YYYY-MM-DD format")
        parser.add_argument("--days-ago", type=int, help="Number of days ago to ingest")
        args = parser.parse_args(sys.argv[2:])

        con = get_db_connection()
        try:
            local_tz = ZoneInfo(settings.LOCAL_TZ)

            if args.date:
                target_date = datetime.strptime(args.date, "%Y-%m-%d").date()
            elif args.days_ago is not None:
                target_date = (datetime.now(local_tz) - timedelta(days=args.days_ago)).date()
            else:
                # Default to yesterday
                target_date = (datetime.now(local_tz) - timedelta(days=1)).date()

            start_local = datetime.combine(target_date, datetime.min.time(), tzinfo=local_tz)
            end_local = start_local + timedelta(days=1)

            start_utc = start_local.astimezone(timezone.utc)
            end_utc = end_local.astimezone(timezone.utc)

            print(f"Ingesting data for {target_date} ({start_utc} to {end_utc})")
            ingest_aw_window(con, settings, start_utc, end_utc)
            print(f"Successfully ingested data for {target_date}!")
        finally:
            con.close()

    else:
        print(f"Unknown command: {command}")
        print_usage()

def print_usage():
    """Print usage information."""
    print("LifeLog System")
    print("Usage:")
    print("  python -m backend.app.main init-db           # Initialize database")
    print("  python -m backend.app.main daemon            # Run scheduled jobs (nightly processing, backups)")
    print("  python -m backend.app.main realtime-watcher  # Run real-time event watcher for AURA (Hot Path)")
    print("  python -m backend.app.main process-now       # Manually process pending events into timeline")
    print("  python -m backend.app.main test-ingestion    # Test data ingestion")
    print("  python -m backend.app.main test-processing   # Test timeline processing")
    print("  python -m backend.app.main ingest            # Ingest data for a specific date or days ago")

if __name__ == "__main__":
    # Configure logging
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(levelname)s - [%(name)s] - %(message)s"
    )
    main()
