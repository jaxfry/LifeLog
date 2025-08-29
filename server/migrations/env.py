import asyncio
from logging.config import fileConfig

from alembic import context
from sqlalchemy import pool
from sqlalchemy.ext.asyncio import create_async_engine
from sqlmodel import SQLModel

# this is the Alembic Config object, which provides
# access to the values within the .ini file in use.
config = context.config

# Interpret the config file for Python logging.
# This line sets up loggers basically.
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# --- CUSTOM SETUP FOR OUR LIFELOG APP ---

# 1. Import our models so Alembic knows about them
# We can import the base model and Alembic will find all subclasses
from lifelog.models import *  # Import all models from your models file
from lifelog.core.config import settings # Import our central settings

# 2. Get the database URL from our central settings object
# This ensures Alembic uses the same database as our app
database_url = settings.DATABASE_URL
if not database_url:
    raise ValueError("DATABASE_URL environment variable is not set for Alembic")

config.set_main_option("sqlalchemy.url", str(database_url))

# The target_metadata is what Alembic compares the database against
# to detect changes. SQLModel.metadata contains all our table definitions.
target_metadata = SQLModel.metadata

# --- END CUSTOM SETUP ---

def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode."""
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection):
    context.configure(connection=connection, target_metadata=target_metadata)

    with context.begin_transaction():
        context.run_migrations()


async def run_migrations_online() -> None:
    """Run migrations in 'online' mode."""
    connectable = create_async_engine(
        database_url,
        poolclass=pool.NullPool,
    )

    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)

    await connectable.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    asyncio.run(run_migrations_online())