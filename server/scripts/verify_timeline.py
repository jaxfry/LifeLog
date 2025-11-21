import asyncio
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from sqlmodel import select
from app.models.data import Timeline, Session
import os

DATABASE_URL = os.environ.get("DATABASE_URL", "postgresql+asyncpg://lifelog:lifelogpassword@db:5432/lifelog_db")

async def verify():
    engine = create_async_engine(DATABASE_URL)
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with async_session() as session:
        stmt = select(Timeline).order_by(Timeline.created_at.desc()).limit(5)
        result = await session.execute(stmt)
        timelines = result.scalars().all()
        
        print(f"Found {len(timelines)} timeline entries.")
        for t in timelines:
            print(f" - [{t.start_time} to {t.end_time}] {t.activity}: {t.notes}")

if __name__ == "__main__":
    asyncio.run(verify())
