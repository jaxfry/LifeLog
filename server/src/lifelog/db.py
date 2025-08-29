from sqlmodel import SQLModel
from sqlalchemy.ext.asyncio import create_async_engine # <-- Use async engine
from .core.config import settings

# Read the database URL from our central settings object
DATABASE_URL = settings.DATABASE_URL

# The engine is the single point of entry to our database
# We create an async engine now. `echo=True` logs SQL queries.
engine = create_async_engine(DATABASE_URL, echo=True)

# We will keep this synchronous version for Alembic for now, as it's simpler.
# Alembic's env.py will create its own engine.
# So we can remove the old synchronous engine from here.