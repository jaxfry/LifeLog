import pytest
from app.core.ingestion import ingest_log
from app.models.data import RawLog
from sqlmodel import select

@pytest.mark.asyncio
async def test_ingest_log_deduplication(async_client, session):
    payload = {"data": "test_dedup"}
    device_id = "dev_dedup"
    ext_id = "ext_dedup"
    
    # First Ingest
    log1, created1 = await ingest_log(session, device_id, ext_id, payload)
    assert created1
    assert log1.id is not None
    await session.commit()
    
    # Second Ingest (Duplicate)
    log2, created2 = await ingest_log(session, device_id, ext_id, payload)
    assert not created2
    assert log2.id == log1.id
    
    # Verify only one log in DB with this payload
    stmt = select(RawLog).where(RawLog.device_id == device_id)
    result = await session.execute(stmt)
    logs = result.scalars().all()
    assert len(logs) == 1

@pytest.mark.asyncio
async def test_ingest_log_different_payload(async_client, session):
    device_id = "dev_diff"
    ext_id = "ext_diff"
    
    log1, _ = await ingest_log(session, device_id, ext_id, {"data": "A"})
    await session.commit()
    log2, _ = await ingest_log(session, device_id, ext_id, {"data": "B"})
    await session.commit()
    
    assert log1.id != log2.id
