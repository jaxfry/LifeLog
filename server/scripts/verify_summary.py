import asyncio
import os
from datetime import datetime
from sqlalchemy.orm import sessionmaker
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.core.db import engine
from app.models.data import DailySummary, Timeline
from app.core.daily_summary import generate_daily_summary

async def verify_daily_summary():
    target_date_str = "2025-11-21"
    target_date = datetime.strptime(target_date_str, "%Y-%m-%d")
    
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with async_session() as session:
        print(f"--- Verifying Data for {target_date_str} ---")
        
        # 1. Check if we have timeline entries
        stmt = select(Timeline).limit(5)
        result = await session.execute(stmt)
        entries = result.scalars().all()
        print(f"Found {len(entries)} sample timeline entries.")
        
        if not entries:
            print("WARNING: No timeline entries found. The summary will likely be empty.")
        
        # 2. Generate Summary
        print("Generating summary...")
        await generate_daily_summary(session, target_date)
        
        # 3. Fetch Result
        stmt = select(DailySummary).where(DailySummary.date == target_date)
        result = await session.execute(stmt)
        summary = result.scalars().first()
        
        if summary:
            print("\n=== Daily Summary Generated ===")
            print(f"Date: {summary.date.date()}")
            print(f"Mood: {summary.mood}")
            print(f"Productivity Score: {summary.productivity_score}/10")
            print("\nKey Activities:")
            for activity in summary.key_activities:
                print(f"- {activity}")
            print("\nNarrative:")
            print(summary.summary_text)
            print("===============================")
        else:
            print("ERROR: Failed to generate summary.")

if __name__ == "__main__":
    asyncio.run(verify_daily_summary())
