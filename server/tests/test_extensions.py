import pytest
from app.core.ingestion import ingest_log
from app.models.data import RawLog
from sqlmodel import select

@pytest.mark.asyncio
async def test_ingest_log_deduplication(session):
    payload = {"data": "test"}
    device_id = "dev1"
    ext_id = "ext1"
    
    # First Ingest
    log1, created1 = await ingest_log(session, device_id, ext_id, payload)
    assert created1
    assert log1.id is not None
    
    # Second Ingest (Duplicate)
    log2, created2 = await ingest_log(session, device_id, ext_id, payload)
    assert not created2
    assert log2.id == log1.id
    
    # Verify only one log in DB
    stmt = select(RawLog)
    result = await session.execute(stmt)
    logs = result.scalars().all()
    assert len(logs) == 1

@pytest.mark.asyncio
async def test_ingest_log_different_payload(session):
    device_id = "dev1"
    ext_id = "ext1"
    
    log1, _ = await ingest_log(session, device_id, ext_id, {"data": "A"})
    log2, _ = await ingest_log(session, device_id, ext_id, {"data": "B"})
    
    assert log1.id != log2.id
