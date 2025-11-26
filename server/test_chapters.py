"""
Test script to manually trigger chapter generation for a specific date
"""
import asyncio
from datetime import datetime, timezone, timedelta
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import sessionmaker
from app.core.db import engine
from app.core.chapter_summarizer import generate_daily_chapters

async def test_chapter_generation():
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    
    async with async_session() as session:
        # Generate chapters for yesterday (when the timeline entries exist)
        # Based on the timeline data, entries are from Nov 26 UTC (Nov 25 local time -0800)
        target_date = datetime.now(timezone.utc)
        print(f"Generating chapters for {target_date.date()}...")
        await generate_daily_chapters(session, target_date)
        
        # Also try yesterday
        yesterday = datetime.now(timezone.utc) - timedelta(days=1)
        print(f"\nGenerating chapters for {yesterday.date()}...")
        await generate_daily_chapters(session, yesterday)
        
        print("\nDone!")

if __name__ == "__main__":
    asyncio.run(test_chapter_generation())
