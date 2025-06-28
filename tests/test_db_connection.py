"""Test for basic Postgres connection and query using SQLAlchemy async session."""
import pytest
import asyncio
from backend.app.core.db import get_db
from sqlalchemy import text

@pytest.mark.asyncio
async def test_basic_connection():
    async for session in get_db():
        result = await session.execute(text("SELECT table_name FROM information_schema.tables LIMIT 1;"))
        rows = result.fetchall()
        assert isinstance(rows, list)
