"""
Shared test fixtures and configuration for pytest.

IMPORTANT: Tests use an in-memory SQLite database by default to ensure
production data is NEVER touched. For integration tests that require
PostgreSQL features (like pgvector), set TEST_DATABASE_URL explicitly.
"""
import os
import sys

import pytest
import pytest_asyncio
import sqlalchemy.dialects.sqlite

# Register SQLite handlers for Postgres-specific types
_sqlite_compiler = sqlalchemy.dialects.sqlite.base.SQLiteTypeCompiler
_sqlite_compiler.visit_JSONB = _sqlite_compiler.visit_JSON
try:
    from pgvector.sqlalchemy import Vector  # noqa: F401  (used via setattr below)
    _sqlite_compiler.visit_VECTOR = _sqlite_compiler.visit_JSON
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

# Tests never run in production mode; provide a test SECRET_KEY
os.environ.setdefault("SECRET_KEY", "test-secret-key-not-for-production")
os.environ.setdefault("DEBUG", "true")

import uuid

from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import NullPool
from sqlmodel import SQLModel

# Import models to register them with SQLModel metadata
from app.models import (  # noqa: F401
    accounting,
    auth,
    config,
    ingest,
    kernel,
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
    await session.rollback()
    if "sqlite" in TEST_DATABASE_URL:
        await session.execute(text("PRAGMA foreign_keys = OFF"))
    for table in reversed(SQLModel.metadata.sorted_tables):
        await session.execute(table.delete())
    if "sqlite" in TEST_DATABASE_URL:
        await session.execute(text("PRAGMA foreign_keys = ON"))
    await session.commit()

@pytest_asyncio.fixture
async def async_client():
    """Create an async HTTP client for testing."""
    # Import here to use our overridden DATABASE_URL
    from app.core.database import get_session
    from app.main import app

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

@pytest_asyncio.fixture
async def mock_user(session):
    """Override get_current_user dependency with a regular (non-superuser) user."""
    from app.core.dependencies import CaptureActor, get_capture_actor, get_current_user
    from app.main import app
    from app.models.auth import User

    user = User(id=uuid.uuid4(), username="regular", is_superuser=False, is_active=True, hashed_password="xxx")
    session.add(user)
    await session.commit()
    app.dependency_overrides[get_current_user] = lambda: user
    app.dependency_overrides[get_capture_actor] = lambda: CaptureActor(user=user)
    yield user
    app.dependency_overrides.pop(get_current_user, None)
    app.dependency_overrides.pop(get_capture_actor, None)


@pytest_asyncio.fixture
async def mock_superuser(session):
    """Override get_current_superuser dependency."""
    from app.core.dependencies import get_current_superuser
    from app.main import app
    from app.models.auth import User

    user = User(id=uuid.uuid4(), username="admin", is_superuser=True, is_active=True, hashed_password="xxx")
    session.add(user)
    await session.commit()
    app.dependency_overrides[get_current_superuser] = lambda: user
    yield user
    app.dependency_overrides.pop(get_current_superuser, None)

@pytest.fixture
def mock_device_auth():
    """Override verify_api_key dependency."""
    from app.core.dependencies import CaptureActor, get_capture_actor, verify_device
    from app.main import app
    from app.models.auth import Device, User

    owner = User(username="device-owner", hashed_password="x")
    device = Device(
        id="test-device-1",
        user_id=owner.id,
        name="Test Device",
        device_type="test",
        api_key_hash="hash",
    )
    app.dependency_overrides[verify_device] = lambda: device
    app.dependency_overrides[get_capture_actor] = lambda: CaptureActor(user=owner, device=device)
    yield device
    app.dependency_overrides.pop(verify_device, None)
    app.dependency_overrides.pop(get_capture_actor, None)
