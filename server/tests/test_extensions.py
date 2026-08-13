import json
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from unittest.mock import MagicMock

import pytest
from sqlmodel import select

from app.core.extension_utils import sync_extensions_db
from app.models.config import Extension
from app.models.ingest import RawLog
from app.services.extension_runtime import configure_extension_pollers
from app.services.ingestion import ingest_log


@pytest.mark.asyncio
async def test_ingest_log_deduplication(async_client, session):
    payload = {"data": "test_dedup"}
    device_id = "dev_dedup"
    ext_id = "ext_dedup"

    # First Ingest
    log1, created1 = await ingest_log(session, device_id, ext_id, payload)
    assert created1
    assert log1.id is not None

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
    log2, _ = await ingest_log(session, device_id, ext_id, {"data": "B"})

    assert log1.id != log2.id


@pytest.mark.asyncio
async def test_ingest_log_payload_hash_stability(async_client, session):
    from app.services.ingestion import calculate_payload_hash

    payload = {"b": 2, "a": 1, "nested": {"z": "last", "a": "first"}}
    h1 = calculate_payload_hash(payload)
    h2 = calculate_payload_hash({"a": 1, "b": 2, "nested": {"a": "first", "z": "last"}})
    assert h1 == h2

    log, created = await ingest_log(session, "dev_hash", "ext_hash", payload)
    assert created
    assert log.payload_hash == h1


@pytest.mark.asyncio
async def test_sync_extensions_db_populates_api_version(tmp_path, session, monkeypatch):
    from app.core import extension_utils

    ext_dir = tmp_path / "com.lifelog.test"
    ext_dir.mkdir()
    (ext_dir / "manifest.json").write_text(
        json.dumps({"id": "com.lifelog.test", "version": "1.2.0", "api_version": "2"})
    )
    monkeypatch.setattr(extension_utils, "EXTENSIONS_DIR", str(tmp_path))

    await sync_extensions_db(session)

    ext = await session.get(Extension, "com.lifelog.test")
    assert ext is not None
    assert ext.version == "1.2.0"
    assert ext.api_version == "2"
    assert ext.is_active is True
    assert ext.archived_at is None


@pytest.mark.asyncio
async def test_sync_extensions_db_defaults_api_version(tmp_path, session, monkeypatch):
    from app.core import extension_utils

    ext_dir = tmp_path / "com.lifelog.legacy"
    ext_dir.mkdir()
    (ext_dir / "manifest.json").write_text(json.dumps({"id": "com.lifelog.legacy", "version": "0.1.0"}))
    monkeypatch.setattr(extension_utils, "EXTENSIONS_DIR", str(tmp_path))

    await sync_extensions_db(session)

    ext = await session.get(Extension, "com.lifelog.legacy")
    assert ext is not None
    assert ext.api_version == "1"


@pytest.mark.asyncio
async def test_configure_extension_pollers_registers_manifest_cron(session, monkeypatch):
    from app.services import extension_runtime

    session.add(
        Extension(
            id="com.lifelog.school",
            version="1.0.0",
            scheduler_cron="*/15 * * * *",
            config={
                "id": "com.lifelog.school",
                "version": "1.0.0",
                "capabilities": ["collector", "normalizer"],
                "scheduler_cron": "*/15 * * * *",
            },
        )
    )
    await session.commit()

    @asynccontextmanager
    async def session_factory():
        yield session

    monkeypatch.setattr(extension_runtime, "async_session_factory", session_factory)
    scheduler = MagicMock()
    assert await configure_extension_pollers(scheduler) == 1
    kwargs = scheduler.add_job.call_args.kwargs
    assert kwargs["id"] == "extension-poller:com.lifelog.school"
    assert kwargs["max_instances"] == 1


@pytest.mark.asyncio
async def test_sync_extensions_db_archives_missing_extension(tmp_path, session, monkeypatch):
    from app.core import extension_utils

    session.add(Extension(id="gone.ext", version="1.0.0", api_version="1", is_active=True))
    await session.commit()
    monkeypatch.setattr(extension_utils, "EXTENSIONS_DIR", str(tmp_path))

    await sync_extensions_db(session)

    ext = await session.get(Extension, "gone.ext")
    assert ext is not None
    assert ext.is_active is False
    assert ext.archived_at is not None


@pytest.mark.asyncio
async def test_sync_extensions_db_reactivation_clears_archived_at(tmp_path, session, monkeypatch):
    from app.core import extension_utils

    ext_dir = tmp_path / "com.lifelog.test"
    ext_dir.mkdir()
    (ext_dir / "manifest.json").write_text(
        json.dumps({"id": "com.lifelog.test", "version": "2.0.0", "api_version": "1"})
    )
    session.add(
        Extension(
            id="com.lifelog.test",
            version="1.0.0",
            api_version="1",
            is_active=False,
            archived_at=datetime.now(UTC).replace(tzinfo=None),
        )
    )
    await session.commit()
    monkeypatch.setattr(extension_utils, "EXTENSIONS_DIR", str(tmp_path))

    await sync_extensions_db(session)

    ext = await session.get(Extension, "com.lifelog.test")
    assert ext is not None
    assert ext.is_active is True
    assert ext.archived_at is None
    assert ext.version == "2.0.0"
