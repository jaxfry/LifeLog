from typing import AsyncGenerator  # <-- Use AsyncGenerator
from sqlmodel.ext.asyncio.session import AsyncSession  # Use SQLModel's AsyncSession for .exec

# Use the central session factory from db.py
from .db import async_session


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency to provide an AsyncSession per-request."""
    async with async_session() as session:
        yield session