from typing import Generator, Optional
import duckdb
from backend.app.core.db import get_db_connection

def get_db() -> Generator[duckdb.DuckDBPyConnection, None, None]:
    """
    Dependency to get a database connection.
    Ensures the connection is closed after the request.
    """
    db: Optional[duckdb.DuckDBPyConnection] = None
    try:
        db = get_db_connection()
        yield db
    finally:
        if db:
            db.close()

# In Pydantic v2, Annotated is preferred for dependency injection metadata.
# from typing import Annotated
# from fastapi import Depends
# DBDep = Annotated[duckdb.DuckDBPyConnection, Depends(get_db)]
# However, for simplicity now, we'll use Depends directly in route signatures.