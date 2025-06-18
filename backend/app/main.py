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
        from backend.app.processing.timeline import process_pending_events
        
        con = get_db_connection()
        try:
            print("Testing timeline processing...")
            process_pending_events(con, settings)
            print("Processing test completed!")
        finally:
            con.close()
            
    else:
        print(f"Unknown command: {command}")
        print_usage()

def print_usage():
    """Print usage information."""
    print("LifeLog System")
    print("Usage:")
    print("  python -m backend.app.main init-db        # Initialize database")
    print("  python -m backend.app.main daemon         # Run daemon")
    print("  python -m backend.app.main test-ingestion # Test data ingestion")
    print("  python -m backend.app.main test-processing # Test timeline processing")

if __name__ == "__main__":
    # Configure logging
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(levelname)s - [%(name)s] - %(message)s"
    )
    main()
