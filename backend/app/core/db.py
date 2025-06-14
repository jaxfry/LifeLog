# lifelog/core/db.py
import duckdb
from pathlib import Path

DB_FILE = Path(__file__).parent.parent / "data/lifelog.db"
SCHEMA_FILE = Path(__file__).parent.parent / "data/schema.sql"

def get_db_connection() -> duckdb.DuckDBPyConnection:
    """Gets a connection to the DuckDB database."""
    # Add any necessary PRAGMA settings here
    con = duckdb.connect(database=str(DB_FILE), read_only=False)
    return con

def initialize_database():
    if DB_FILE.exists():
        print("Database already exists.")
        return

    # Enable extensions **before** we run INSTALL/LOAD in schema.sql
    con = duckdb.connect(
        database=str(DB_FILE),
        read_only=False,
        # This flag is available since DuckDB 0.9.2 and also enables loading
        # pre-compiled wheels like `icu`, `vss`, etc.
        config={"allow_unsigned_extensions": "true"},
    )

    # Fallback for older DuckDB builds (<0.9) that still need a PRAGMA:
    try:
        con.execute("PRAGMA enable_extension_loading")      # no “= true”
    except duckdb.CatalogException:
        # Already enabled or not required in this build → safe to ignore
        pass

    with open(SCHEMA_FILE) as f:
        for stmt in filter(None, map(str.strip, f.read().split(';'))):
            con.execute(stmt)

    con.close()
    print("Database initialized.")



if __name__ == "__main__":
    initialize_database()