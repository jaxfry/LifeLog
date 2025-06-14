"""Test for basic DuckDB connection and query using get_db_connection."""
import pytest
from backend.app.core.db import get_db_connection

def test_basic_connection():
    con = get_db_connection()
    try:
        # Query sqlite_master equivalent in DuckDB: information_schema.tables
        result = con.execute("SELECT table_name FROM information_schema.tables LIMIT 1;").fetchall()
        assert isinstance(result, list)
    finally:
        con.close()
