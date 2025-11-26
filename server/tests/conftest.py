"""
Shared test fixtures and configuration for pytest.
"""
import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport
from sqlalchemy import text
from app.main import app
from app.core.db import engine
from sqlalchemy.orm import sessionmaker
from sqlmodel.ext.asyncio.session import AsyncSession
from app.api.deps import get_current_superuser, verify_api_key
from app.models.config import User, Device
import uuid

@pytest_asyncio.fixture(autouse=True)
async def cleanup_engine():
    """Cleanup database engine after each test."""
    yield
    await engine.dispose()

@pytest_asyncio.fixture
async def async_client():
    """Create an async HTTP client for testing."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://localhost") as client:
        yield client

# @pytest_asyncio.fixture(autouse=True)
# async def db_cleanup():
#     """Clean up database tables before each test."""
#     async with engine.begin() as conn:
#         # Truncate all tables. Order matters due to FKs.
#         # Or use CASCADE.
#         await conn.execute(text("TRUNCATE TABLE timeline, events, sessions, raw_logs, system_config, failures RESTART IDENTITY CASCADE"))
#     yield


@pytest_asyncio.fixture
async def session():
    """
    Create a new database session for a test.
    """
    async_session = sessionmaker(
        engine, class_=AsyncSession, expire_on_commit=False
    )
    async with async_session() as s:
        yield s

@pytest.fixture
def mock_superuser():
    """Override get_current_superuser dependency."""
    user = User(id=uuid.uuid4(), username="admin", is_superuser=True, is_active=True, hashed_password="xxx")
    app.dependency_overrides[get_current_superuser] = lambda: user
    yield user
    app.dependency_overrides.pop(get_current_superuser, None)

@pytest.fixture
def mock_device_auth():
    """Override verify_api_key dependency."""
    device = Device(id="test_device_1", name="Test Device", type="test", api_key_hash="hash")
    app.dependency_overrides[verify_api_key] = lambda: device
    yield device
    app.dependency_overrides.pop(verify_api_key, None)
