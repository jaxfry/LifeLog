from sqlmodel import SQLModel
from sqlmodel.ext.asyncio.session import AsyncSession as SQLModelAsyncSession
from sqlalchemy.ext.asyncio import (
	create_async_engine,  # <-- Use async engine
	async_sessionmaker,
)
import logging
from .core.config import settings
from pgvector.sqlalchemy import Vector
from sqlalchemy import text

# Read the database URL from our central settings object
DATABASE_URL = settings.DATABASE_URL

# Ensure an async driver is used for Postgres URLs when creating an async engine.
# Accept common forms like "postgres://..." or "postgresql://..." and coerce to asyncpg.
if DATABASE_URL.startswith("postgres://"):
	logging.warning("DATABASE_URL uses 'postgres://' scheme; coercing to 'postgresql+asyncpg://' for async support.")
	DATABASE_URL = "postgresql+asyncpg://" + DATABASE_URL[len("postgres://"):]
elif DATABASE_URL.startswith("postgresql://") and "+asyncpg" not in DATABASE_URL:
	logging.warning("DATABASE_URL missing async driver; coercing to 'postgresql+asyncpg://' for async support.")
	DATABASE_URL = "postgresql+asyncpg://" + DATABASE_URL[len("postgresql://"):]

# The engine is the single point of entry to our database
# We create an async engine now. `echo=True` logs SQL queries.
engine = create_async_engine(DATABASE_URL, echo=True)

# Central async session factory for the app. Using expire_on_commit=False avoids
# attribute refreshes after commits (which can trigger IO in unexpected places).
async_session = async_sessionmaker(
	bind=engine,
	expire_on_commit=False,
	class_=SQLModelAsyncSession,
)


async def init_db() -> None:
	"""Initialize database schema in development by creating all tables.

	This is a convenience for local/dev environments where Alembic hasn't been run.
	In production, prefer Alembic migrations.
	"""
	# Import models to register tables with SQLModel.metadata
	from . import models as _models  # noqa: F401
	async with engine.begin() as conn:
		# Create pgvector extension only when using Postgres; skip for SQLite and others
		if DATABASE_URL.startswith("postgresql+asyncpg://"):
			try:
				await conn.execute(text('CREATE EXTENSION IF NOT EXISTS vector'))
			except Exception as e:
				# Don't block table creation if extension isn't available yet
				import logging
				logging.warning(f"Skipping pgvector extension init: {e}")
		# Always attempt to create tables even if extension creation failed
		await conn.run_sync(SQLModel.metadata.create_all)

# We will keep this synchronous version for Alembic for now, as it's simpler.
# Alembic's env.py will create its own engine.
# So we can remove the old synchronous engine from here.