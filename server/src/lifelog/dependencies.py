from typing import AsyncGenerator # <-- Use AsyncGenerator
from sqlmodel.ext.asyncio.session import AsyncSession # <-- Use AsyncSession
from sqlalchemy.ext.asyncio import create_async_engine
from .core.config import settings

# We need a separate engine instance for the dependency, or use the one from db.py
# Let's import it to be consistent
from .db import engine

async def get_session() -> AsyncGenerator[AsyncSession, None]:
    """Dependency to get an async database session."""
    async with AsyncSession(engine) as session:
        yield session