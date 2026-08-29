import uuid
from unittest.mock import AsyncMock, patch

import pytest
from sqlmodel import select

from app.models.auth import Device, User
from app.models.captures import Capture, CaptureArtifact, ProcessingJob, UploadSession
from app.models.files import FileAttachment
from app.models.retrieval import SearchDocument


async def _persist_user(session, user) -> None:
    session.add(user)
    await session.commit()


@pytest.mark.asyncio
@pytest.mark.integration
async def test_note_capture_is_immediately_searchable(async_client, session, mock_user):
    await _persist_user(session, mock_user)
    response = await async_client.post(
        "/api/v1/captures/notes",
        json={
            "text": "Remember the chain rule practice problems",
            "intent": "class_note",
            "context_hints": {"course": "Calculus 12"},
            "idempotency_key": "note-1",
        },
    )
    assert response.status_code == 201
    detail = response.json()
    assert detail["capture"]["status"] == "ready"
    assert detail["capture"]["context_hints"] == {"course": "Calculus 12"}
    assert detail["jobs"][0]["status"] == "completed"
    document = (await session.execute(select(SearchDocument))).scalars().one()
    assert "chain rule" in document.content

    duplicate = await async_client.post(
        "/api/v1/captures/notes",
        json={"text": "Ignored duplicate", "idempotency_key": "note-1"},
    )
    assert duplicate.status_code == 201
    assert duplicate.json()["capture"]["id"] == detail["capture"]["id"]
    assert len((await session.execute(select(Capture))).scalars().all()) == 1


@pytest.mark.asyncio
@pytest.mark.integration
async def test_file_capture_preserves_original_and_structured_hints(
    async_client,
    session,
    mock_user,
):
    await _persist_user(session, mock_user)
    response = await async_client.post(
        "/api/v1/captures",
        data={
            "kind": "photo",
            "captured_at": "2026-09-01T09:00:00-07:00",
            "intent": "assignment",
            "context_hints": '{"course":"Calculus 12"}',
        },
        files=[("files", ("assignment.txt", b"Due Friday", "text/plain"))],
    )
    assert response.status_code == 201
    detail = response.json()
    assert detail["capture"]["status"] == "preserved"
    assert detail["artifacts"][0]["user_metadata"]["context_hints"] == {
        "course": "Calculus 12"
    }
    assert detail["jobs"][0]["stage"] == "content_extraction"
    assert detail["jobs"][0]["status"] == "pending"


@pytest.mark.asyncio
@pytest.mark.integration
async def test_resumable_upload_enforces_offsets_and_finalizes(
    async_client,
    session,
    mock_user,
):
    await _persist_user(session, mock_user)
    draft = await async_client.post(
        "/api/v1/captures/drafts",
        json={"kind": "audio", "intent": "class_recording"},
    )
    capture_id = draft.json()["capture"]["id"]
    upload_response = await async_client.post(
        f"/api/v1/captures/{capture_id}/uploads",
        json={"filename": "class.txt", "mime_type": "text/plain", "total_bytes": 11},
    )
    assert upload_response.status_code == 201
    upload_id = upload_response.json()["id"]

    first = await async_client.put(
        f"/api/v1/captures/{capture_id}/uploads/{upload_id}",
        content=b"hello ",
        headers={"Upload-Offset": "0", "Content-Type": "application/offset+octet-stream"},
    )
    assert first.status_code == 200
    assert first.json()["received_bytes"] == 6
    mismatch = await async_client.put(
        f"/api/v1/captures/{capture_id}/uploads/{upload_id}",
        content=b"world",
        headers={"Upload-Offset": "0"},
    )
    assert mismatch.status_code == 409
    second = await async_client.put(
        f"/api/v1/captures/{capture_id}/uploads/{upload_id}",
        content=b"world",
        headers={"Upload-Offset": "6"},
    )
    assert second.status_code == 200

    completed = await async_client.post(
        f"/api/v1/captures/{capture_id}/uploads/{upload_id}/complete"
    )
    assert completed.status_code == 200
    assert completed.json()["capture"]["status"] == "preserved"
    assert len(completed.json()["artifacts"]) == 1
    upload = await session.get(UploadSession, uuid.UUID(upload_id))
    assert upload is not None and upload.status == "complete"
    assert len((await session.execute(select(CaptureArtifact))).scalars().all()) == 1

    next_upload = await async_client.post(
        f"/api/v1/captures/{capture_id}/uploads",
        json={"filename": "class-2.txt", "mime_type": "text/plain", "total_bytes": 1},
    )
    next_upload_id = next_upload.json()["id"]
    assert (
        await async_client.put(
            f"/api/v1/captures/{capture_id}/uploads/{next_upload_id}",
            content=b"!",
            headers={"Upload-Offset": "0"},
        )
    ).status_code == 200
    assert (
        await async_client.post(
            f"/api/v1/captures/{capture_id}/uploads/{next_upload_id}/complete"
        )
    ).status_code == 200
    artifacts = (
        await session.execute(
            select(CaptureArtifact)
            .where(CaptureArtifact.capture_id == uuid.UUID(capture_id))
            .order_by(CaptureArtifact.sequence)
        )
    ).scalars().all()
    assert [artifact.sequence for artifact in artifacts] == [0, 1]


@pytest.mark.asyncio
@pytest.mark.integration
async def test_artifact_processing_reports_progressive_capture_state(
    async_client,
    session,
    mock_user,
):
    await _persist_user(session, mock_user)
    response = await async_client.post(
        "/api/v1/captures",
        data={"kind": "file", "captured_at": "2026-09-01T09:00:00Z"},
        files=[("files", ("notes.txt", b"Cellular respiration notes", "text/plain"))],
    )
    capture_id = response.json()["capture"]["id"]
    attachment_id = response.json()["artifacts"][0]["id"]
    with patch(
        "app.services.artifacts.extract_memory",
        AsyncMock(side_effect=RuntimeError("AI not configured")),
    ):
        processed = await async_client.post(f"/api/v1/files/{attachment_id}/process")
    assert processed.status_code == 200
    detail = await async_client.get(f"/api/v1/captures/{capture_id}")
    assert detail.status_code == 200
    assert detail.json()["capture"]["status"] == "awaiting_review"
    statuses = {job["stage"]: job["status"] for job in detail.json()["jobs"]}
    assert statuses == {
        "content_extraction": "completed",
        "classification": "completed",
        "memory_enrichment": "skipped",
    }
    reviewed = await async_client.post(
        f"/api/v1/captures/{capture_id}/classification",
        json={"label": "class_notes"},
    )
    assert reviewed.status_code == 200
    assert reviewed.json()["capture"]["status"] == "partially_ready"
    attachment = await session.get(FileAttachment, uuid.UUID(attachment_id))
    assert attachment is not None and attachment.processing_status == "ready"
    assert len((await session.execute(select(ProcessingJob))).scalars().all()) == 3

    from app.main import app

    pool = AsyncMock()
    app.state.arq_pool = pool
    try:
        retried = await async_client.post(f"/api/v1/captures/{capture_id}/retry")
    finally:
        del app.state.arq_pool
    assert retried.status_code == 200
    assert retried.json()["capture"]["status"] == "processing"
    pool.enqueue_job.assert_awaited_once_with("task_process_file", attachment_id)


@pytest.mark.asyncio
@pytest.mark.integration
async def test_device_authenticated_capture_records_device_owner(async_client, session):
    from app.core.security import hash_api_key

    owner = User(username="phone-owner", hashed_password="x")
    session.add(owner)
    await session.flush()
    device = Device(
        id="phone-1",
        user_id=owner.id,
        name="Phone",
        device_type="mobile",
        api_key_hash=hash_api_key("phone-secret-key"),
    )
    session.add(device)
    await session.commit()
    response = await async_client.post(
        "/api/v1/captures/notes",
        headers={"X-API-Key": "phone-secret-key"},
        json={"text": "Captured offline from my phone", "idempotency_key": "phone-note-1"},
    )
    assert response.status_code == 201
    assert response.json()["capture"]["device_id"] == device.id
    assert response.json()["capture"]["user_id"] == str(owner.id)


@pytest.mark.asyncio
@pytest.mark.integration
async def test_failed_stage_cancels_dependent_stages(async_client, session, mock_user):
    await _persist_user(session, mock_user)
    response = await async_client.post(
        "/api/v1/captures",
        data={"kind": "file", "captured_at": "2026-09-01T09:00:00Z"},
        files=[("files", ("empty.txt", b"", "text/plain"))],
    )
    attachment_id = response.json()["artifacts"][0]["id"]
    processed = await async_client.post(f"/api/v1/files/{attachment_id}/process")
    assert processed.status_code == 409
    detail = await async_client.get(f"/api/v1/captures/{response.json()['capture']['id']}")
    statuses = {job["stage"]: job["status"] for job in detail.json()["jobs"]}
    assert statuses == {
        "content_extraction": "failed",
        "classification": "cancelled",
        "memory_enrichment": "cancelled",
    }
    assert detail.json()["capture"]["status"] == "failed"
