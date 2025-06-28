# central_server/processing_service/db_session.py
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker, Session as SQLAlchemySession
from contextlib import contextmanager
from typing import Iterator, Generator, AsyncGenerator # Added for type hinting
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
import sys
if sys.version_info >= (3, 10):
    from contextlib import asynccontextmanager
else:
    from async_generator import asynccontextmanager
import logging

try:
    # Try relative import for Docker context
    from .logic.settings import settings
except ImportError:
    # Fall back to absolute import for local context
    from logic.settings import settings

logger = logging.getLogger(__name__)

# Create a synchronous engine instance
# For async operations, you would use create_async_engine from sqlalchemy.ext.asyncio
engine = create_engine(
    settings.SQLALCHEMY_DATABASE_URL,
    pool_pre_ping=True,  # Enable connection health checking
    pool_recycle=3600    # Recycle connections after 1 hour (optional)
)

# Create an async engine instance
async_engine = create_async_engine(
    settings.SQLALCHEMY_DATABASE_URL.replace('postgresql://', 'postgresql+asyncpg://'),
    pool_pre_ping=True,
    pool_recycle=3600
)

# Create a configured "Session" class
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Create a configured async session class
AsyncSessionLocal = async_sessionmaker(
    bind=async_engine,
    expire_on_commit=False,
    class_=AsyncSession
)

@contextmanager
def get_db_session() -> Generator[SQLAlchemySession, None, None]: # Changed type hint
    """
    Provide a transactional scope around a series of operations.
    Commits the transaction if it succeeds, rolls back and RE-RAISES the
    exception if it fails.
    """
    db = SessionLocal()
    try:
        yield db
        db.commit()
        logger.debug("Database session committed.")
    except Exception as e:
        db.rollback()
        logger.error(f"Database session rolled back due to error: {e}", exc_info=True)
        raise # <<< CRITICAL: Re-raise the exception
    finally:
        db.close()
        logger.debug("Database session closed.")

@asynccontextmanager
async def get_db_session_async() -> AsyncGenerator[AsyncSession, None]:
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
            logger.debug("Async database session committed.")
        except Exception as e:
            await session.rollback()
            logger.error(f"Async database session rolled back due to error: {e}", exc_info=True)
            raise
        finally:
            await session.close()
            logger.debug("Async database session closed.")

# Optional: A simple function to test DB connection if needed
def check_db_connection():
    try:
        with engine.connect() as connection:
            logger.info("Successfully connected to the PostgreSQL database.")
            return True
    except Exception as e:
        logger.error(f"Failed to connect to the PostgreSQL database: {e}", exc_info=True)
        return False

async def check_db_connection_async():
    try:
        async with async_engine.connect() as conn:
            await conn.execute(text('SELECT 1'))
            logger.info("Successfully connected to the PostgreSQL database (async).")
            return True
    except Exception as e:
        logger.error(f"Failed to connect to the PostgreSQL database (async): {e}", exc_info=True)
        return False

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    logger.info("Checking database connection...")
    if check_db_connection():
        logger.info("Database connection check successful.")
        # Example usage of get_db_session
        try:
            with get_db_session() as db:
                # You can perform a simple query here if models are defined and tables exist
                # For example, if Project model is defined:
                # from central_server.processing_service.db_models import Project
                # project_count = db.query(Project).count()
                # logger.info(f"Found {project_count} projects in the database.")
                logger.info("Successfully obtained and used a database session.")
        except Exception as e:
            logger.error(f"Error during example session usage: {e}")
    else:
        logger.error("Database connection check failed.")
