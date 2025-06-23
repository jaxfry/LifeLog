# backend/app/core/db.py
import duckdb
from pathlib import Path
import datetime
import logging

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
    """
    Gets a configured connection to the DuckDB database.
    
    Args:
        read_only: Whether to open the connection in read-only mode
        
    Returns:
        Configured DuckDB connection
        
    Raises:
        DatabaseConnectionError: If connection cannot be established
    """
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

class DatabaseInitializer:
    """Handles database initialization."""
    
    @staticmethod
    def initialize_database() -> None:
        """
        Initializes the database by running the schema.sql file.
        
        Raises:
            DatabaseInitializationError: If initialization fails
        """
        DatabaseInitializer._remove_existing_database()
        logger.info(f"Initializing new database at: {DB_FILE}")
        
        try:
            con = get_db_connection()
            try:
                DatabaseInitializer._execute_schema(con)
                logger.info("Database initialized successfully.")
            finally:
                con.close()
        except Exception as e:
            DatabaseInitializer._cleanup_failed_initialization()
            raise DatabaseInitializationError(f"Database initialization failed: {e}")
    
    @staticmethod
    def _remove_existing_database() -> None:
        """Remove existing database file if it exists."""
        if DB_FILE.exists():
            logger.info(f"Removing existing database file: {DB_FILE}")
            DB_FILE.unlink()
    
    @staticmethod
    def _execute_schema(con: duckdb.DuckDBPyConnection) -> None:
        """Execute the schema SQL file."""
        try:
            with open(SCHEMA_FILE, 'r') as f:
                schema_sql = f.read()
                con.execute(schema_sql)
        except FileNotFoundError:
            raise DatabaseInitializationError(f"Schema file not found: {SCHEMA_FILE}")
        except duckdb.Error as e:
            raise DatabaseInitializationError(f"Schema execution failed: {e}")
    
    @staticmethod
    def _cleanup_failed_initialization() -> None:
        """Clean up database file after failed initialization."""
        if DB_FILE.exists():
            logger.warning("Cleaning up failed database initialization")
            DB_FILE.unlink()

class DatabaseBackupManager:
    """Handles database backup operations."""
    
    @staticmethod
    def backup_database() -> Path:
        """
        Creates a timestamped, compacted backup of the database.
        
        Returns:
            Path to the created backup file
            
        Raises:
            DatabaseConnectionError: If backup operation fails
        """
        backup_path = DatabaseBackupManager._generate_backup_path()
        logger.info(f"Backing up database to {backup_path}")
        
        try:
            with get_db_connection() as con:
                con.execute(f"VACUUM INTO '{backup_path}';")
            logger.info("Backup completed successfully")
            return backup_path
        except Exception as e:
            raise DatabaseConnectionError(f"Backup failed: {e}")
    
    @staticmethod
    def _generate_backup_path() -> Path:
        """Generate a timestamped backup file path."""
        backup_dir = _BACKEND_DIR / "data/backups"
        backup_dir.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.datetime.now().strftime("%Y-%m-%d_%H%M%S")
        return backup_dir / f"lifelog_{timestamp}.db"

# Legacy functions for backward compatibility
def initialize_database():
    """Legacy function - use DatabaseInitializer.initialize_database instead."""
    DatabaseInitializer.initialize_database()

def backup_database():
    """Legacy function - use DatabaseBackupManager.backup_database instead."""
    return DatabaseBackupManager.backup_database()

if __name__ == "__main__":
    initialize_database()