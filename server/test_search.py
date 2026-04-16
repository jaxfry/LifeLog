import asyncio
from app.core.db import engine
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import sessionmaker
from sqlalchemy import select
from app.models.data import DailyChapter
from app.core.vector_service import generate_embedding

async def test_run():
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with async_session() as session:
        embedding = await generate_embedding("What was I working on in blender?")
        print(f"Generated embedding of length {len(embedding)}")
        
        stmt_chapters = select(DailyChapter).where(DailyChapter.embedding.is_not(None)).order_by(DailyChapter.embedding.l2_distance(embedding)).limit(5)
        result_chapters = await session.execute(stmt_chapters)
        chapters = result_chapters.scalars().all()
        for c in chapters:
            print(f"Match: {c.title}: {c.summary}")

if __name__ == "__main__":
    asyncio.run(test_run())
