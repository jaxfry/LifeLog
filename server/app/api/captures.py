import json
import os
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, File, Form, Header, HTTPException, Request, UploadFile, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import col, select
from starlette.datastructures import Headers

from app.core.config import settings
from app.core.database import get_session
from app.core.dependencies import CaptureActor, get_capture_actor
from app.core.files import create_attachment
from app.models.auth import User
from app.models.captures import Capture, CaptureArtifact, ProcessingJob, UploadSession
from app.models.context import ReviewItem
from app.models.files import FileAttachment
from app.models.sources import SourceConnection
from app.services.context import copy_context, copy_policy, get_owned_area, link_target, recognize_areas, set_policy
from app.services.jobs import complete_job, refresh_capture_status, start_job
from app.services.retrieval import upsert_search_document

router = APIRouter()
UPLOAD_SESSION_DIR = Path("storage/upload_sessions")


def _now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def _normalize_dt(value: datetime) -> datetime:
    if value.tzinfo is not None:
        return value.astimezone(UTC).replace(tzinfo=None)
    return value


def _parse_json_object(value: str | None, field: str) -> dict:
    if not value:
        return {}
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=400, detail=f"{field} must be valid JSON") from exc
    if not isinstance(parsed, dict):
        raise HTTPException(status_code=400, detail=f"{field} must be a JSON object")
    return parsed


class NoteCaptureCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    text: str = Field(min_length=1, max_length=1_000_000)
    captured_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    timezone: str | None = None
    intent: str | None = None
    context_hints: dict = Field(default_factory=dict)
    privacy: dict = Field(default_factory=dict)
    idempotency_key: str | None = Field(default=None, max_length=200)
    source_connection_id: uuid.UUID | None = None
    life_area_ids: list[uuid.UUID] = Field(default_factory=list)


class CaptureDraftCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: Literal["photo", "audio", "video", "file", "scan", "note"]
    captured_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    timezone: str | None = None
    intent: str | None = None
    context_hints: dict = Field(default_factory=dict)
    privacy: dict = Field(default_factory=dict)
    idempotency_key: str | None = Field(default=None, max_length=200)
    source_connection_id: uuid.UUID | None = None
    life_area_ids: list[uuid.UUID] = Field(default_factory=list)


class UploadSessionCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    filename: str = Field(min_length=1, max_length=500)
    mime_type: str = Field(min_length=1, max_length=200)
    total_bytes: int = Field(gt=0)


class UploadSessionOut(BaseModel):
    """Wire shape for the iOS tus client, which decodes camelCase keys."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    receivedBytes: int = Field(alias="received_bytes")
    status: str
    contentHash: str | None = Field(alias="content_hash")


class ClassificationReview(BaseModel):
    model_config = ConfigDict(extra="forbid")

    label: str = Field(min_length=1, max_length=200)


class CaptureDetail(BaseModel):
    capture: Capture
    artifacts: list[FileAttachment]
    jobs: list[ProcessingJob]


async def _owned_capture(session: AsyncSession, capture_id: uuid.UUID, user: User) -> Capture:
    capture = await session.get(Capture, capture_id)
    if capture is None or capture.user_id != user.id:
        raise HTTPException(status_code=404, detail="Capture not found")
    return capture


async def _validate_connection(
    session: AsyncSession,
    connection_id: uuid.UUID | None,
    user: User,
) -> SourceConnection | None:
    if connection_id is None:
        return None
    connection = await session.get(SourceConnection, connection_id)
    if connection is None or connection.user_id != user.id:
        raise HTTPException(status_code=400, detail="Invalid source connection")
    return connection


async def _detail(session: AsyncSession, capture: Capture) -> CaptureDetail:
    links = (
        await session.execute(
            select(CaptureArtifact)
            .where(CaptureArtifact.capture_id == capture.id)
            .order_by(CaptureArtifact.sequence)
        )
    ).scalars().all()
    files = []
    for link in links:
        attachment = await session.get(FileAttachment, link.file_id)
        if attachment is not None:
            files.append(attachment)
    jobs = (
        await session.execute(
            select(ProcessingJob)
            .where(ProcessingJob.capture_id == capture.id)
            .order_by(ProcessingJob.created_at)
        )
    ).scalars().all()
    return CaptureDetail(capture=capture, artifacts=files, jobs=list(jobs))


async def _enqueue_file(request: Request, file_id: uuid.UUID) -> None:
    pool = getattr(request.app.state, "arq_pool", None)
    if pool is not None:
        await pool.enqueue_job("task_process_file", str(file_id))


def _add_artifact_jobs(
    session: AsyncSession,
    capture: Capture,
    attachment: FileAttachment,
) -> None:
    for stage, processor in (
        ("content_extraction", "core.artifact"),
        ("classification", "core.artifact_classifier"),
        ("memory_enrichment", "core.artifact_memory"),
    ):
        session.add(
            ProcessingJob(
                capture_id=capture.id,
                target_type="file_attachment",
                target_id=attachment.id,
                stage=stage,
                processor=processor,
                input_version=attachment.processing_version,
            )
        )


async def _new_capture(
    session: AsyncSession,
    user: User,
    *,
    kind: str,
    captured_at: datetime,
    timezone: str | None,
    intent: str | None,
    context_hints: dict,
    privacy: dict,
    idempotency_key: str | None,
    source_connection_id: uuid.UUID | None,
    device_id: str | None = None,
    life_area_ids: list[uuid.UUID] | None = None,
    text_content: str | None = None,
) -> tuple[Capture, bool]:
    await _validate_connection(session, source_connection_id, user)
    if idempotency_key:
        existing = (
            await session.execute(
                select(Capture).where(
                    Capture.user_id == user.id,
                    Capture.idempotency_key == idempotency_key,
                )
            )
        ).scalars().first()
        if existing is not None:
            return existing, False
    capture = Capture(
        user_id=user.id,
        device_id=device_id,
        kind=kind,
        captured_at=_normalize_dt(captured_at),
        timezone=timezone,
        intent=intent,
        context_hints=context_hints,
        privacy=privacy,
        idempotency_key=idempotency_key,
        source_connection_id=source_connection_id,
        text_content=text_content,
    )
    session.add(capture)
    await session.flush()
    explicit_ids = set(life_area_ids or [])
    for area_id in explicit_ids:
        if await get_owned_area(session, area_id, user.id) is None:
            raise HTTPException(status_code=400, detail=f"Unknown Life Area: {area_id}")
        await link_target(session, area_id, "capture", capture.id, source="user")
    recognition_text = " ".join(
        filter(None, [intent, text_content, json.dumps(context_hints, default=str)])
    )
    for area, confidence in await recognize_areas(session, user.id, recognition_text):
        if area.id not in explicit_ids:
            await link_target(
                session,
                area.id,
                "capture",
                capture.id,
                source="recognition_rule",
                confidence=confidence,
            )
    visibility = privacy.get("visibility")
    if visibility in ("global", "selected_areas", "private"):
        allowed_area_ids: list[uuid.UUID] = []
        try:
            allowed_area_ids = [
                uuid.UUID(str(area_id)) for area_id in (privacy.get("allowed_area_ids") or [])
            ]
        except (TypeError, ValueError) as exc:
            raise HTTPException(
                status_code=400,
                detail="privacy.allowed_area_ids must contain UUIDs",
            ) from exc
        for area_id in allowed_area_ids:
            if await get_owned_area(session, area_id, user.id) is None:
                raise HTTPException(status_code=400, detail=f"Unknown Life Area: {area_id}")
        await set_policy(
            session,
            user.id,
            "capture",
            capture.id,
            visibility=visibility,
            allowed_area_ids=allowed_area_ids,
            sensitivity=privacy.get("sensitivity"),
            reason=privacy.get("reason"),
        )
    return capture, True


@router.post("/captures/notes", response_model=CaptureDetail, status_code=status.HTTP_201_CREATED)
async def create_note_capture(
    body: NoteCaptureCreate,
    session: AsyncSession = Depends(get_session),
    actor: CaptureActor = Depends(get_capture_actor),
) -> CaptureDetail:
    capture, created = await _new_capture(
        session,
        actor.user,
        kind="note",
        captured_at=body.captured_at,
        timezone=body.timezone,
        intent=body.intent,
        context_hints=body.context_hints,
        privacy=body.privacy,
        idempotency_key=body.idempotency_key,
        source_connection_id=body.source_connection_id,
        device_id=actor.device.id if actor.device else None,
        life_area_ids=body.life_area_ids,
        text_content=body.text,
    )
    if created:
        job = await start_job(
            session,
            target_type="capture",
            target_id=capture.id,
            capture_id=capture.id,
            stage="text_indexing",
            processor="core.note",
        )
        await upsert_search_document(
            session,
            source_type="capture",
            source_id=capture.id,
            title=body.intent or "Note",
            content=body.text,
            occurred_at=capture.captured_at,
            metadata={
                "kind": "note",
                "context_hints": body.context_hints,
                "owner_user_id": str(actor.user.id),
            },
        )
        await complete_job(session, job, output_refs={"search_document": str(capture.id)})
        capture.status = "ready"
        capture.updated_at = _now()
        session.add(capture)
        await session.commit()
    return await _detail(session, capture)


@router.post("/captures/drafts", response_model=CaptureDetail, status_code=status.HTTP_201_CREATED)
async def create_capture_draft(
    body: CaptureDraftCreate,
    session: AsyncSession = Depends(get_session),
    actor: CaptureActor = Depends(get_capture_actor),
) -> CaptureDetail:
    capture, created = await _new_capture(
        session,
        actor.user,
        kind=body.kind,
        captured_at=body.captured_at,
        timezone=body.timezone,
        intent=body.intent,
        context_hints=body.context_hints,
        privacy=body.privacy,
        idempotency_key=body.idempotency_key,
        source_connection_id=body.source_connection_id,
        device_id=actor.device.id if actor.device else None,
        life_area_ids=body.life_area_ids,
    )
    if created:
        await session.commit()
    return await _detail(session, capture)


@router.post("/captures", response_model=CaptureDetail, status_code=status.HTTP_201_CREATED)
async def create_capture(
    request: Request,
    kind: Annotated[Literal["photo", "audio", "video", "file", "scan", "note"], Form()],
    captured_at: Annotated[datetime, Form()],
    files: Annotated[list[UploadFile], File()],
    timezone: Annotated[str | None, Form()] = None,
    intent: Annotated[str | None, Form()] = None,
    context_hints: Annotated[str | None, Form()] = None,
    privacy: Annotated[str | None, Form()] = None,
    idempotency_key: Annotated[str | None, Form()] = None,
    source_connection_id: Annotated[uuid.UUID | None, Form()] = None,
    life_area_ids: Annotated[str | None, Form()] = None,
    session: AsyncSession = Depends(get_session),
    actor: CaptureActor = Depends(get_capture_actor),
) -> CaptureDetail:
    if not files:
        raise HTTPException(status_code=400, detail="At least one file is required")
    hints = _parse_json_object(context_hints, "context_hints")
    privacy_data = _parse_json_object(privacy, "privacy")
    try:
        area_ids = [uuid.UUID(value) for value in json.loads(life_area_ids or "[]")]
    except (ValueError, TypeError, json.JSONDecodeError) as exc:
        raise HTTPException(status_code=400, detail="life_area_ids must be a JSON UUID list") from exc
    capture, created = await _new_capture(
        session,
        actor.user,
        kind=kind,
        captured_at=captured_at,
        timezone=timezone,
        intent=intent,
        context_hints=hints,
        privacy=privacy_data,
        idempotency_key=idempotency_key,
        source_connection_id=source_connection_id,
        device_id=actor.device.id if actor.device else None,
        life_area_ids=area_ids,
    )
    if not created:
        return await _detail(session, capture)
    extension_id = None
    if source_connection_id:
        connection = await session.get(SourceConnection, source_connection_id)
        extension_id = connection.extension_id if connection else None
    for sequence, upload in enumerate(files):
        attachment = await create_attachment(
            session,
            upload,
            owner_user_id=actor.user.id,
            category=intent,
            source_extension_id=extension_id,
            user_metadata={"capture_id": str(capture.id), "context_hints": hints},
        )
        session.add(
            CaptureArtifact(
                capture_id=capture.id,
                file_id=attachment.id,
                sequence=sequence,
            )
        )
        await copy_context(
            session,
            from_type="capture",
            from_id=capture.id,
            to_type="file_attachment",
            to_id=attachment.id,
        )
        await copy_policy(
            session,
            user_id=actor.user.id,
            from_type="capture",
            from_id=capture.id,
            to_type="file_attachment",
            to_id=attachment.id,
        )
        _add_artifact_jobs(session, capture, attachment)
    capture.status = "preserved"
    capture.updated_at = _now()
    session.add(capture)
    await session.commit()
    detail = await _detail(session, capture)
    for attachment in detail.artifacts:
        await _enqueue_file(request, attachment.id)
    return detail


@router.get("/captures", response_model=list[Capture])
async def list_captures(
    limit: int = 50,
    session: AsyncSession = Depends(get_session),
    actor: CaptureActor = Depends(get_capture_actor),
) -> list[Capture]:
    return list(
        (
            await session.execute(
                select(Capture)
                .where(Capture.user_id == actor.user.id)
                .order_by(col(Capture.created_at).desc())
                .limit(min(max(limit, 1), 500))
            )
        ).scalars().all()
    )


@router.get("/captures/{capture_id}", response_model=CaptureDetail)
async def get_capture(
    capture_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    actor: CaptureActor = Depends(get_capture_actor),
) -> CaptureDetail:
    capture = await _owned_capture(session, capture_id, actor.user)
    await refresh_capture_status(session, capture.id)
    return await _detail(session, capture)


@router.post("/captures/{capture_id}/retry", response_model=CaptureDetail)
async def retry_capture_processing(
    capture_id: uuid.UUID,
    request: Request,
    session: AsyncSession = Depends(get_session),
    actor: CaptureActor = Depends(get_capture_actor),
) -> CaptureDetail:
    capture = await _owned_capture(session, capture_id, actor.user)
    pool = getattr(request.app.state, "arq_pool", None)
    if pool is None:
        raise HTTPException(status_code=503, detail="Background worker queue is unavailable")
    detail = await _detail(session, capture)
    if not detail.artifacts:
        raise HTTPException(status_code=409, detail="Capture has no artifact processing to retry")
    for attachment in detail.artifacts:
        attachment.processing_status = "failed"
        attachment.processing_error = None
        attachment.updated_at = _now()
        session.add(attachment)
    capture.status = "processing"
    capture.processing_error = None
    capture.updated_at = _now()
    session.add(capture)
    await session.commit()
    for attachment in detail.artifacts:
        await pool.enqueue_job("task_process_file", str(attachment.id))
    return await _detail(session, capture)


@router.post("/captures/{capture_id}/classification", response_model=CaptureDetail)
async def review_capture_classification(
    capture_id: uuid.UUID,
    body: ClassificationReview,
    session: AsyncSession = Depends(get_session),
    actor: CaptureActor = Depends(get_capture_actor),
) -> CaptureDetail:
    capture = await _owned_capture(session, capture_id, actor.user)
    if not capture.classification:
        raise HTTPException(status_code=409, detail="Capture has not been classified")
    capture.classification = {
        **capture.classification,
        "label": body.label,
        "confidence": 1.0,
        "needs_review": False,
        "source": "user_confirmation",
    }
    capture.updated_at = _now()
    session.add(capture)
    review_item = (
        await session.execute(
            select(ReviewItem).where(
                ReviewItem.user_id == actor.user.id,
                ReviewItem.source_type == "capture_classification",
                ReviewItem.source_id == capture.id,
                ReviewItem.status == "pending",
            )
        )
    ).scalars().first()
    if review_item is not None:
        review_item.status = "accepted"
        review_item.decided_at = _now()
        review_item.updated_at = _now()
        session.add(review_item)
    await refresh_capture_status(session, capture.id)
    await session.commit()
    return await _detail(session, capture)


@router.post("/captures/{capture_id}/cancel", response_model=CaptureDetail)
async def cancel_capture(
    capture_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    actor: CaptureActor = Depends(get_capture_actor),
) -> CaptureDetail:
    capture = await _owned_capture(session, capture_id, actor.user)
    capture.status = "cancelled"
    capture.updated_at = _now()
    session.add(capture)
    jobs = (
        await session.execute(
            select(ProcessingJob).where(
                ProcessingJob.capture_id == capture.id,
                ProcessingJob.status.in_(("pending", "running")),
            )
        )
    ).scalars().all()
    for job in jobs:
        job.status = "cancelled"
        job.error_type = "UserCancelled"
        job.error_message = "Capture cancelled by user"
        job.completed_at = _now()
        job.updated_at = _now()
        session.add(job)
    uploads = (
        await session.execute(
            select(UploadSession).where(
                UploadSession.capture_id == capture.id,
                UploadSession.status.in_(("pending", "uploading")),
            )
        )
    ).scalars().all()
    for upload in uploads:
        upload.status = "cancelled"
        upload.updated_at = _now()
        session.add(upload)
        Path(upload.temp_path).unlink(missing_ok=True)
    await session.commit()
    return await _detail(session, capture)


@router.post(
    "/captures/{capture_id}/uploads",
    response_model=UploadSessionOut,
    status_code=status.HTTP_201_CREATED,
)
async def create_upload_session(
    capture_id: uuid.UUID,
    body: UploadSessionCreate,
    session: AsyncSession = Depends(get_session),
    actor: CaptureActor = Depends(get_capture_actor),
) -> UploadSession:
    await _owned_capture(session, capture_id, actor.user)
    max_bytes = settings.MAX_ARTIFACT_SIZE_MB * 1024 * 1024
    if body.total_bytes > max_bytes:
        raise HTTPException(status_code=413, detail=f"Upload exceeds {settings.MAX_ARTIFACT_SIZE_MB} MB")
    UPLOAD_SESSION_DIR.mkdir(parents=True, exist_ok=True)
    upload_id = uuid.uuid4()
    temp_path = UPLOAD_SESSION_DIR / f"{upload_id}.part"
    temp_path.touch(exist_ok=False)
    upload = UploadSession(
        id=upload_id,
        capture_id=capture_id,
        filename=body.filename,
        mime_type=body.mime_type,
        total_bytes=body.total_bytes,
        temp_path=str(temp_path),
        expires_at=_now() + timedelta(hours=settings.UPLOAD_SESSION_TTL_HOURS),
    )
    session.add(upload)
    await session.commit()
    await session.refresh(upload)
    return upload


@router.put("/captures/{capture_id}/uploads/{upload_id}", response_model=UploadSessionOut)
async def append_upload_chunk(
    capture_id: uuid.UUID,
    upload_id: uuid.UUID,
    request: Request,
    upload_offset: Annotated[int, Header(alias="Upload-Offset", ge=0)],
    session: AsyncSession = Depends(get_session),
    actor: CaptureActor = Depends(get_capture_actor),
) -> UploadSession:
    await _owned_capture(session, capture_id, actor.user)
    upload = (
        await session.execute(
            select(UploadSession).where(UploadSession.id == upload_id).with_for_update()
        )
    ).scalars().first()
    if upload is None or upload.capture_id != capture_id:
        raise HTTPException(status_code=404, detail="Upload session not found")
    if upload.status in ("complete", "cancelled", "expired"):
        raise HTTPException(status_code=409, detail=f"Upload is {upload.status}")
    if upload.expires_at < _now():
        upload.status = "expired"
        session.add(upload)
        await session.commit()
        raise HTTPException(status_code=410, detail="Upload session expired")
    if upload_offset != upload.received_bytes:
        raise HTTPException(
            status_code=409,
            detail={"message": "Upload offset mismatch", "expected_offset": upload.received_bytes},
        )
    chunk = await request.body()
    if not chunk:
        raise HTTPException(status_code=400, detail="Chunk is empty")
    if upload.received_bytes + len(chunk) > upload.total_bytes:
        raise HTTPException(status_code=413, detail="Chunk exceeds declared upload size")
    with open(upload.temp_path, "ab") as stream:
        stream.write(chunk)
        stream.flush()
        os.fsync(stream.fileno())
    upload.received_bytes += len(chunk)
    upload.status = "uploading"
    upload.updated_at = _now()
    session.add(upload)
    await session.commit()
    await session.refresh(upload)
    return upload


@router.get("/captures/{capture_id}/uploads/{upload_id}", response_model=UploadSessionOut)
async def get_upload_session(
    capture_id: uuid.UUID,
    upload_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    actor: CaptureActor = Depends(get_capture_actor),
) -> UploadSession:
    await _owned_capture(session, capture_id, actor.user)
    upload = await session.get(UploadSession, upload_id)
    if upload is None or upload.capture_id != capture_id:
        raise HTTPException(status_code=404, detail="Upload session not found")
    return upload


@router.delete("/captures/{capture_id}/uploads/{upload_id}", status_code=status.HTTP_204_NO_CONTENT)
async def cancel_upload_session(
    capture_id: uuid.UUID,
    upload_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    actor: CaptureActor = Depends(get_capture_actor),
) -> None:
    await _owned_capture(session, capture_id, actor.user)
    upload = await session.get(UploadSession, upload_id)
    if upload is None or upload.capture_id != capture_id:
        raise HTTPException(status_code=404, detail="Upload session not found")
    if upload.status == "complete":
        raise HTTPException(status_code=409, detail="Completed uploads cannot be cancelled")
    upload.status = "cancelled"
    upload.updated_at = _now()
    session.add(upload)
    await session.commit()
    Path(upload.temp_path).unlink(missing_ok=True)


@router.post("/captures/{capture_id}/uploads/{upload_id}/complete", response_model=CaptureDetail)
async def complete_upload(
    capture_id: uuid.UUID,
    upload_id: uuid.UUID,
    request: Request,
    session: AsyncSession = Depends(get_session),
    actor: CaptureActor = Depends(get_capture_actor),
) -> CaptureDetail:
    capture = await _owned_capture(session, capture_id, actor.user)
    capture = (
        await session.execute(select(Capture).where(Capture.id == capture.id).with_for_update())
    ).scalar_one()
    upload = (
        await session.execute(
            select(UploadSession).where(UploadSession.id == upload_id).with_for_update()
        )
    ).scalars().first()
    if upload is None or upload.capture_id != capture_id:
        raise HTTPException(status_code=404, detail="Upload session not found")
    if upload.status == "complete":
        raise HTTPException(status_code=409, detail="Upload is already complete")
    if upload.status in ("cancelled", "expired", "failed"):
        raise HTTPException(status_code=409, detail=f"Upload is {upload.status}")
    if upload.received_bytes != upload.total_bytes:
        raise HTTPException(
            status_code=409,
            detail={"message": "Upload is incomplete", "received_bytes": upload.received_bytes},
        )
    connection = await _validate_connection(session, capture.source_connection_id, actor.user)
    with open(upload.temp_path, "rb") as stream:
        file = UploadFile(
            file=stream,
            filename=upload.filename,
            headers=Headers({"content-type": upload.mime_type}),
        )
        attachment = await create_attachment(
            session,
            file,
            owner_user_id=actor.user.id,
            source_extension_id=connection.extension_id if connection else None,
            user_metadata={"capture_id": str(capture.id), "context_hints": capture.context_hints},
        )
    upload.status = "complete"
    upload.content_hash = attachment.content_hash
    upload.updated_at = _now()
    session.add(upload)
    current_sequence = (
        await session.execute(
            select(func.max(CaptureArtifact.sequence)).where(CaptureArtifact.capture_id == capture.id)
        )
    ).scalar_one()
    session.add(
        CaptureArtifact(
            capture_id=capture.id,
            file_id=attachment.id,
            sequence=(current_sequence if current_sequence is not None else -1) + 1,
        )
    )
    await copy_context(
        session,
        from_type="capture",
        from_id=capture.id,
        to_type="file_attachment",
        to_id=attachment.id,
    )
    await copy_policy(
        session,
        user_id=actor.user.id,
        from_type="capture",
        from_id=capture.id,
        to_type="file_attachment",
        to_id=attachment.id,
    )
    _add_artifact_jobs(session, capture, attachment)
    capture.status = "preserved"
    capture.updated_at = _now()
    session.add(capture)
    await session.commit()
    Path(upload.temp_path).unlink(missing_ok=True)
    await _enqueue_file(request, attachment.id)
    return await _detail(session, capture)
