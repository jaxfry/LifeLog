import asyncio
import os
from sqlalchemy.orm import sessionmaker
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.db import engine
from app.models.config import SystemConfig

async def seed_config():
    async_session = sessionmaker(
        engine, class_=AsyncSession, expire_on_commit=False
    )
    async with async_session() as session:
        key = os.environ.get("GEMINI_API_KEY")
        if key:
            print(f"Seeding GEMINI_API_KEY from env...")
            config = await session.get(SystemConfig, "GEMINI_API_KEY")
            if not config:
                config = SystemConfig(key="GEMINI_API_KEY", value=key, description="API Key for Gemini LLM")
                session.add(config)
                await session.commit()
                print("Seeded successfully.")
            else:
                print("GEMINI_API_KEY already exists in DB.")
        else:
            print("GEMINI_API_KEY not found in env.")

if __name__ == "__main__":
    asyncio.run(seed_config())
