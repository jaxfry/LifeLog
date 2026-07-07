"""
Shared test fixtures and configuration for pytest.

IMPORTANT: Tests use an in-memory SQLite database by default to ensure
production data is NEVER touched. For integration tests that require
PostgreSQL features (like pgvector), set TEST_DATABASE_URL explicitly.
"""
import pytest
import pytest_asyncio
import os
import sys
import sqlalchemy.dialects.sqlite
from sqlalchemy.dialects.postgresql import JSONB

# Register SQLite handlers for Postgres-specific types
_sqlite_compiler = sqlalchemy.dialects.sqlite.base.SQLiteTypeCompiler
setattr(_sqlite_compiler, "visit_JSONB", _sqlite_compiler.visit_JSON)
try:
    from pgvector.sqlalchemy import Vector
    setattr(_sqlite_compiler, "visit_VECTOR", _sqlite_compiler.visit_JSON)
except ImportError:
    pass

# =============================================================================
# CRITICAL SAFETY CHECK: Prevent tests from running against production database
# =============================================================================
_PRODUCTION_DB_MARKERS = ["lifelog_db", "prod", "production"]
_current_db_url = os.environ.get("DATABASE_URL", "")

def _is_production_database(url: str) -> bool:
    """Check if the URL appears to be a production database."""
    url_lower = url.lower()
    # Check for production markers
    for marker in _PRODUCTION_DB_MARKERS:
        if marker in url_lower:
            # Allow if explicitly set as test database
            if "test" in url_lower:
                return False
            return True
    return False

# Block tests if DATABASE_URL looks like production and TEST_DATABASE_URL is not set
if _is_production_database(_current_db_url) and not os.environ.get("TEST_DATABASE_URL"):
    print("\n" + "=" * 70)
    print("ERROR: Refusing to run tests against production database!")
    print(f"DATABASE_URL appears to be production: {_current_db_url[:50]}...")
    print("\nTo run tests, either:")
    print("  1. Set TEST_DATABASE_URL to a test database")
    print("  2. Unset DATABASE_URL to use in-memory SQLite")
    print("=" * 70 + "\n")
    sys.exit(1)

# =============================================================================
# Test Database Configuration
# =============================================================================
# Use TEST_DATABASE_URL if set, otherwise use in-memory SQLite for safety
import tempfile

_TEST_DB_FILE = os.environ.get("TEST_DB_FILE") or os.path.join(
    tempfile.gettempdir(), f"lifelog_test_{os.getpid()}.db"
)

TEST_DATABASE_URL = os.environ.get(
    "TEST_DATABASE_URL",
    f"sqlite+aiosqlite:///{_TEST_DB_FILE}",
)

# Override the DATABASE_URL for tests BEFORE importing app modules
os.environ["DATABASE_URL"] = TEST_DATABASE_URL

from httpx import AsyncClient, ASGITransport
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import NullPool
from sqlmodel import SQLModel
import uuid

# Import models to register them with SQLModel metadata
from app.models import (  # noqa: F401
    accounting,
    auth,
    config,
    ingest,
    processing,
)

# Create test engine
test_engine = create_async_engine(
    TEST_DATABASE_URL,
    echo=False,
    future=True,
    poolclass=NullPool if "postgresql" in TEST_DATABASE_URL else None,
)

# Create async session factory
TestAsyncSessionLocal = sessionmaker(
    test_engine, 
    class_=AsyncSession, 
    expire_on_commit=False,
    autocommit=False,
    autoflush=False,
)

@pytest.fixture(scope="session")
def event_loop():
    """Create an event loop for the test session."""
    import asyncio
    policy = asyncio.get_event_loop_policy()
    loop = policy.new_event_loop()
    yield loop
    loop.close()


def _cleanup_test_db():
    if "sqlite" in TEST_DATABASE_URL and not TEST_DATABASE_URL.startswith("sqlite+aiosqlite:///:memory"):
        try:
            os.unlink(_TEST_DB_FILE)
        except OSError:
            pass

@pytest_asyncio.fixture(scope="session", autouse=True)
async def setup_test_database():
    """Create all tables at the start of the test session."""
    async with test_engine.begin() as conn:
        # Enable pgvector if using PostgreSQL
        if "postgresql" in TEST_DATABASE_URL:
            await conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
        await conn.run_sync(SQLModel.metadata.create_all)
    
    yield
    
    # Cleanup after all tests
    async with test_engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.drop_all)

    await test_engine.dispose()
    _cleanup_test_db()

@pytest_asyncio.fixture
async def session():
    """Create a new database session for a test."""
    async with TestAsyncSessionLocal() as s:
        yield s
        await s.rollback()

@pytest_asyncio.fixture(autouse=True)
async def cleanup_tables(session):
    """Clean up all data after each test to ensure isolation."""
    yield
    if "sqlite" in TEST_DATABASE_URL:
        await session.execute(text("PRAGMA foreign_keys = OFF"))
        for table in reversed(SQLModel.metadata.sorted_tables):
            await session.execute(table.delete())
        await session.execute(text("PRAGMA foreign_keys = ON"))
        await session.commit()

@pytest_asyncio.fixture
async def async_client():
    """Create an async HTTP client for testing."""
    # Import here to use our overridden DATABASE_URL
    from app.main import app
    from app.core.db import get_session
    
    # Create a fresh session for each request
    async def get_test_session():
        async with TestAsyncSessionLocal() as s:
            yield s
            await s.rollback()
    
    # Override the database session
    app.dependency_overrides[get_session] = get_test_session
    
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://localhost") as client:
        yield client
    
    # Clean up override
    app.dependency_overrides.pop(get_session, None)

@pytest.fixture
def mock_superuser():
    """Override get_current_superuser dependency."""
    from app.main import app
    from app.api.deps import get_current_superuser
    from app.models.config import User
    
    user = User(id=uuid.uuid4(), username="admin", is_superuser=True, is_active=True, hashed_password="xxx")
    app.dependency_overrides[get_current_superuser] = lambda: user
    yield user
    app.dependency_overrides.pop(get_current_superuser, None)

@pytest.fixture
def mock_device_auth():
    """Override verify_api_key dependency."""
    from app.main import app
    from app.api.deps import verify_api_key
    from app.models.config import Device
    
    device = Device(id="test_device_1", name="Test Device", type="test", api_key_hash="hash")
    app.dependency_overrides[verify_api_key] = lambda: device
    yield device
    app.dependency_overrides.pop(verify_api_key, None)

