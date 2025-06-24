# backend/app/core/db.py
import duckdb
from pathlib import Path
import datetime
import logging
from backend.app.core.utils import with_db_write_retry

logger = logging.getLogger(__name__)

# Constants
_BACKEND_DIR = Path(__file__).parent.parent
DB_FILE = _BACKEND_DIR / "data/lifelog.db"
SCHEMA_FILE = _BACKEND_DIR / "data/schema.sql"


class DatabaseConnectionError(Exception):
    """Raised when database connection fails."""
    pass


class DatabaseInitializationError(Exception):
    """Raised when database initialization fails."""
    pass


class DatabaseExtensionManager:
    """Manages DuckDB extensions."""
    
    @staticmethod
    def load_extensions(con: duckdb.DuckDBPyConnection) -> None:
        """Load required extensions for the database."""
        try:
            if DatabaseExtensionManager._should_load_extensions(con):
                DatabaseExtensionManager._load_required_extensions(con)
        except Exception as e:
            logger.debug(f"Extensions could not be loaded (expected during initialization): {e}")
    
    @staticmethod
    def _should_load_extensions(con: duckdb.DuckDBPyConnection) -> bool:
        """Check if VSS extension needs to be loaded."""
        try:
            result = con.execute(
                "SELECT COUNT(*) FROM duckdb_extensions() WHERE extension_name = 'vss' AND loaded = true;"
            ).fetchone()
            return result is not None and result[0] == 0
        except Exception:
            return False
    
    @staticmethod
    def _load_required_extensions(con: duckdb.DuckDBPyConnection) -> None:
        """Load the required extensions."""
        con.execute("LOAD icu;")
        con.execute("LOAD vss;")
        con.execute("SET hnsw_enable_experimental_persistence = true;")


class DatabaseConfigurator:
    """Handles database configuration."""
    
    @staticmethod
    def configure_connection(con: duckdb.DuckDBPyConnection) -> None:
        """Apply required configuration to a database connection."""
        con.execute("SET TimeZone='UTC';")
        DatabaseExtensionManager.load_extensions(con)


def get_db_connection(read_only: bool = False) -> duckdb.DuckDBPyConnection:
    """Open a *new* DuckDB connection every time (fast & race-free)."""
    try:
        con = duckdb.connect(
            database=str(DB_FILE),
            read_only=read_only,
            config={"allow_unsigned_extensions": "true"},
        )
        DatabaseConfigurator.configure_connection(con)
        return con
    except Exception as e:
        raise DatabaseConnectionError(f"Failed to connect to database: {e}")


def close_db_connection(con: duckdb.DuckDBPyConnection):
    """Always close the specific connection you opened."""
    try:
        con.close()
    except Exception as e:
        logger.warning(f"Error closing connection: {e}")


class DatabaseInitializer:
    """Handles database initialization."""
    
    @staticmethod
    def initialize_database() -> None:
        """
        Initializes the database by running the schema.sql file.
        """
        DatabaseInitializer._remove_existing_database()
        logger.info(f"Initializing new database at: {DB_FILE}")
        
        try:
            # Use a direct connection for initialization, not thread-local
            con = duckdb.connect(database=str(DB_FILE), config={"allow_unsigned_extensions": "true"})
            DatabaseConfigurator.configure_connection(con)
            with open(SCHEMA_FILE, "r") as f:
                schema = f.read()
            con.execute(schema)
            con.close()
            logger.info("Database initialized successfully.")
        except Exception as e:
            raise DatabaseInitializationError(f"Failed to initialize database: {e}")

    @staticmethod
    def _remove_existing_database():
        """Removes the database file if it exists."""
        if DB_FILE.exists():
            DB_FILE.unlink()
            logger.debug(f"Removed existing database file: {DB_FILE}")

    @staticmethod
    def ensure_database_initialized() -> None:
        """
        Checks if the database exists and initializes it if not.
        This is a simplified startup check.
        """
        if not DB_FILE.exists():
            logger.info(f"Database file not found at {DB_FILE}. Initializing database...")
            try:
                DatabaseInitializer.initialize_database()
            except DatabaseInitializationError as e:
                logger.error(f"CRITICAL: Database initialization failed: {e}")
                raise


# ---------------------------------------------------------------------------
# METADATA FUNCTIONS
# ---------------------------------------------------------------------------

def get_meta(con: duckdb.DuckDBPyConnection, key: str) -> str | None:
    """Retrieves a value from the meta table."""
    try:
        result = con.execute("SELECT value FROM meta WHERE key = ?", [key]).fetchone()
        return result[0] if result else None
    except duckdb.Error as e:
        logger.error(f"Error getting meta key '{key}': {e}")
        return None

@with_db_write_retry()
def set_meta(con: duckdb.DuckDBPyConnection, key: str, value: str) -> None:
    """Sets a value in the meta table."""
    try:
        con.execute("INSERT OR REPLACE INTO meta (key, value) VALUES (?, ?)", [key, value])
    except duckdb.Error as e:
        logger.error(f"Error setting meta key '{key}' to '{value}': {e}")


# Legacy functions for backward compatibility
def initialize_database():
    """Legacy function - use DatabaseInitializer.initialize_database instead."""
    DatabaseInitializer.initialize_database()

def backup_database():
    """Legacy function - use DatabaseBackupManager.backup_database instead."""
    # return DatabaseBackupManager.backup_database() # Commented out due to missing definition
    logger.warning("DatabaseBackupManager.backup_database() called but is not implemented.")
    return None

if __name__ == "__main__":
    initialize_database()