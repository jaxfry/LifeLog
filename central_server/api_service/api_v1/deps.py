from typing import Generator, Optional
import duckdb
from backend.app.core.db import get_db_connection, close_db_connection

def get_db(read_only: bool = True) -> Generator[duckdb.DuckDBPyConnection, None, None]: # Default to read_only = True
    """
    Dependency to get a database connection. Defaults to a read-only connection.
    Ensures the connection is closed after the request and removed from thread-local storage.
    """
    db: Optional[duckdb.DuckDBPyConnection] = None
    try:
        db = get_db_connection(read_only=read_only) # Pass the read_only flag
        yield db
    finally:
        # close_db_connection will handle closing the connection
        # and clearing it from _db_local storage.
        close_db_connection(db)


def get_db_writable() -> Generator[duckdb.DuckDBPyConnection, None, None]:
    """
    Dependency to get a read-write database connection.
    Ensures the connection is closed after the request and removed from thread-local storage.
    """
    db: Optional[duckdb.DuckDBPyConnection] = None
    try:
        db = get_db_connection(read_only=False) # Explicitly request read-write
        yield db
    finally:
        close_db_connection(db)

# In Pydantic v2, Annotated is preferred for dependency injection metadata.
# from typing import Annotated
# from fastapi import Depends
# DBDep = Annotated[duckdb.DuckDBPyConnection, Depends(get_db)]
# However, for simplicity now, we'll use Depends directly in route signatures.