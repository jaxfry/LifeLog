import asyncio
import sys
import os

# Add the parent directory to sys.path so we can import app
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import text
from app.core.db import engine
from app.models.data import SQLModel

async def reset_db():
    if os.environ.get("ALLOW_DB_RESET") != "1":
        print("ERROR: Database reset is disabled. Set ALLOW_DB_RESET=1 to allow.")
        return
    async with engine.begin() as conn:
        print("Dropping data tables...")
        # We need to use cascade to handle foreign keys
        await conn.execute(text("DROP TABLE IF EXISTS daily_chapters CASCADE"))
        await conn.execute(text("DROP TABLE IF EXISTS daily_summaries CASCADE"))
        await conn.execute(text("DROP TABLE IF EXISTS timeline CASCADE"))
        await conn.execute(text("DROP TABLE IF EXISTS events CASCADE"))
        await conn.execute(text("DROP TABLE IF EXISTS sessions CASCADE"))
        await conn.execute(text("DROP TABLE IF EXISTS raw_logs CASCADE"))
        # Preserving devices, system_config, prompts, extensions, users
        
        print("Creating all tables...")
        await conn.run_sync(SQLModel.metadata.create_all)
        
    print("Database reset complete (Config preserved).")

if __name__ == "__main__":
    asyncio.run(reset_db())
