#!/usr/bin/env python3
"""
Test script for the reprocessing pipeline.
Run this to verify all reprocessing functionality works correctly.
"""
import asyncio
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import sessionmaker

from app.core.db import engine
from app.core.rebuilder import (
    get_reprocessing_status,
    backfill_embeddings,
    reprocess_date_range,
    process_dirty_sessions
)
from app.core.logger import get_logger
from datetime import datetime, timedelta

logger = get_logger(__name__)

async def test_reprocessing_pipeline():
    """Test all reprocessing functions."""
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    
    async with async_session() as session:
        print("=" * 60)
        print("REPROCESSING PIPELINE TEST")
        print("=" * 60)
        
        # Test 1: Get Status
        print("\n1. Getting reprocessing status...")
        status = await get_reprocessing_status(session)
        print(f"   Timeline: {status['timeline']['total']} total, "
              f"{status['timeline']['missing_or_outdated_embeddings']} missing embeddings "
              f"({status['timeline']['percentage_complete']}% complete)")
        print(f"   Chapters: {status['chapters']['total']} total, "
              f"{status['chapters']['missing_or_outdated_embeddings']} missing embeddings "
              f"({status['chapters']['percentage_complete']}% complete)")
        print(f"   Sessions: {status['sessions']['dirty']} dirty, "
              f"{status['sessions']['pending']} pending")
        
        # Test 2: Process Dirty Sessions
        if status['sessions']['dirty'] > 0:
            print(f"\n2. Processing {status['sessions']['dirty']} dirty sessions...")
            await process_dirty_sessions(session)
            print("   ✓ Dirty sessions processed")
        else:
            print("\n2. No dirty sessions to process")
        
        # Test 3: Backfill Embeddings (only if there are missing embeddings)
        if status['timeline']['missing_or_outdated_embeddings'] > 0 or status['chapters']['missing_or_outdated_embeddings'] > 0:
            print(f"\n3. Backfilling embeddings...")
            print(f"   This will process {status['timeline']['missing_or_outdated_embeddings']} timeline entries")
            print(f"   and {status['chapters']['missing_or_outdated_embeddings']} chapters")
            
            # Uncomment to actually run the backfill (can be slow and use API credits)
            # stats = await backfill_embeddings(session, batch_size=10)
            # print(f"   ✓ Timeline: {stats['timeline_processed']} processed, {stats['timeline_failed']} failed")
            # print(f"   ✓ Chapters: {stats['chapters_processed']} processed, {stats['chapters_failed']} failed")
            
            print("   (Skipped - uncomment in script to run)")
        else:
            print("\n3. No embeddings to backfill - all data is up to date!")
        
        # Test 4: Get Final Status
        print("\n4. Getting final status...")
        final_status = await get_reprocessing_status(session)
        print(f"   Timeline: {final_status['timeline']['percentage_complete']}% complete")
        print(f"   Chapters: {final_status['chapters']['percentage_complete']}% complete")
        
        print("\n" + "=" * 60)
        print("TEST COMPLETE")
        print("=" * 60)

if __name__ == "__main__":
    asyncio.run(test_reprocessing_pipeline())
