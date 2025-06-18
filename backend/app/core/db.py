# backend/app/core/db.py
import duckdb
from pathlib import Path
import datetime

# Consistent paths
_BACKEND_DIR = Path(__file__).parent.parent
DB_FILE = _BACKEND_DIR / "data/lifelog.db"
SCHEMA_FILE = _BACKEND_DIR / "data/schema.sql"

def get_db_connection(read_only: bool = False) -> duckdb.DuckDBPyConnection:
    """Gets a connection to the DuckDB database."""
    con = duckdb.connect(
        database=str(DB_FILE),
        read_only=read_only,
        # This is the modern way to enable unsigned extensions
        config={"allow_unsigned_extensions": "true"},
    )
    # This ensures our AT TIME ZONE clauses work correctly regardless of host TZ
    con.execute("SET TimeZone='UTC';")
    return con

def initialize_database():
    """Initializes the database by running the schema.sql file."""
    # First, delete the old, broken DB file if it exists
    if DB_FILE.exists():
        print(f"Old database file found. Deleting to re-create with corrected schema: {DB_FILE}")
        DB_FILE.unlink()

    print(f"Initializing new database at: {DB_FILE}")
    
    # get_db_connection handles creating the file and setting the timezone
    con = get_db_connection()
    
    try:
        with open(SCHEMA_FILE, 'r') as f:
            # Read the whole file and execute as a single block
            # DuckDB's execute can handle multiple statements separated by semicolons.
            schema_sql = f.read()
            con.execute(schema_sql)
        print("Database initialized successfully.")
    except duckdb.Error as e:
        print(f"!!! An error occurred during database initialization: {e}")
        print("Please check your schema.sql file for errors.")
        # Clean up the potentially broken DB file
        con.close()
        if DB_FILE.exists():
            DB_FILE.unlink()
        raise # Re-raise the exception to stop execution
    finally:
        con.close()


def backup_database():
    """Creates a timestamped, compacted backup of the database."""
    backup_dir = _BACKEND_DIR / "data/backups"
    backup_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.datetime.now().strftime("%Y-%m-%d_%H%M%S")
    backup_path = backup_dir / f"lifelog_{timestamp}.db"
    
    print(f"Backing up database to {backup_path}...")
    # Use a fresh connection for the backup operation
    with get_db_connection() as con:
        con.execute(f"VACUUM INTO '{backup_path}';")
    print("Backup complete.")


if __name__ == "__main__":
    initialize_database()