import uuid

import pytest
from httpx import AsyncClient

from app.models.config import Extension


@pytest.mark.asyncio
@pytest.mark.integration
async def test_artifact_source_extension_can_device_upload(
    mock_device_auth,
    async_client: AsyncClient,
    session,
    tmp_path,
    monkeypatch,
):
    from app.core import files as file_storage

    monkeypatch.setattr(file_storage, "UPLOAD_DIR", tmp_path)
    extension_id = f"com.lifelog.capture{uuid.uuid4().hex[:8]}"
    session.add(
        Extension(
            id=extension_id,
            version="1.0.0",
            config={"capabilities": ["artifact_source"]},
        )
    )
    await session.commit()

    response = await async_client.post(
        "/api/v1/files/device-upload",
        data={"source_extension_id": extension_id, "category": "notes"},
        files={"file": ("note.txt", b"Remember this", "text/plain")},
    )

    assert response.status_code == 201
    assert response.json()["source_extension_id"] == extension_id
    assert response.json()["processing_status"] == "pending"


@pytest.mark.asyncio
@pytest.mark.integration
async def test_device_upload_rejects_non_artifact_extension(
    mock_device_auth,
    async_client: AsyncClient,
    session,
):
    extension_id = f"com.lifelog.normalizer{uuid.uuid4().hex[:8]}"
    session.add(Extension(id=extension_id, version="1.0.0", config={"capabilities": ["normalizer"]}))
    await session.commit()

    response = await async_client.post(
        "/api/v1/files/device-upload",
        data={"source_extension_id": extension_id},
        files={"file": ("note.txt", b"No", "text/plain")},
    )
    assert response.status_code == 400
