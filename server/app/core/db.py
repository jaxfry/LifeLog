import asyncio
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from app.core.logger import get_logger
import os

DATABASE_URL = os.environ.get("DATABASE_URL", "postgresql+asyncpg://lifelog:lifelogpassword@localhost:5432/lifelog_db")

engine = create_async_engine(DATABASE_URL, echo=True, future=True)

from sqlalchemy import text

logger = get_logger(__name__)

async def init_db():
    retries = 5
    delay = 5
    for i in range(retries):
        try:
            async with engine.begin() as conn:
                # Enable pgvector extension
                await conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
                # await conn.run_sync(SQLModel.metadata.drop_all)
                # await conn.run_sync(SQLModel.metadata.create_all) # We use Alembic for migrations now
            logger.info("Database initialized successfully.")
            return
        except Exception as e:
            if i == retries - 1:
                logger.error(f"Could not connect to database after {retries} attempts.")
                raise e
            logger.info(f"Database connection failed. Retrying in {delay} seconds... (Attempt {i+1}/{retries})")
            await asyncio.sleep(delay)

async def get_session() -> AsyncSession:
    async_session = sessionmaker(
        engine, class_=AsyncSession, expire_on_commit=False
    )
    async with async_session() as session:
        yield session
