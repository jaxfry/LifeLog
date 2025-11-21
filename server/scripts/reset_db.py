import asyncio
import sys
import os

# Add the parent directory to sys.path so we can import app
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import text
from app.core.db import engine
from app.models.data import SQLModel

async def reset_db():
    async with engine.begin() as conn:
        print("Dropping all tables...")
        # We need to use cascade to handle foreign keys
        await conn.execute(text("DROP TABLE IF EXISTS timeline CASCADE"))
        await conn.execute(text("DROP TABLE IF EXISTS events CASCADE"))
        await conn.execute(text("DROP TABLE IF EXISTS sessions CASCADE"))
        await conn.execute(text("DROP TABLE IF EXISTS raw_logs CASCADE"))
        await conn.execute(text("DROP TABLE IF EXISTS devices CASCADE"))
        
        print("Creating all tables...")
        await conn.run_sync(SQLModel.metadata.create_all)
        
    print("Database reset complete.")

if __name__ == "__main__":
    asyncio.run(reset_db())
