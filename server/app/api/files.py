from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile, status
from fastapi.responses import FileResponse
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import col, or_, select

from app.core.config import settings
from app.core.database import get_session
from app.core.dependencies import Pagination, get_current_user, verify_device
from app.core.files import UPLOAD_DIR, create_attachment
from app.core.rate_limit import limiter
from app.models.auth import Device, User
from app.models.files import ContentChunk, FileAttachment, MemoryProposal
from app.services.artifacts import process_artifact, review_memory_proposal

router = APIRouter()


class ProposalReview(BaseModel):
    decision: Literal["accept", "reject"]


async def _owned_attachment(
    session: AsyncSession,
    file_id: UUID,
    owner_user_id: UUID,
) -> FileAttachment | None:
    """Return an attachment only when the authenticated user owns its evidence."""
    return (
        await session.execute(
            select(FileAttachment)
            .where(FileAttachment.id == file_id)
            .where(FileAttachment.owner_user_id == owner_user_id)
        )
    ).scalar_one_or_none()


async def _enqueue_artifact(request: Request, attachment: FileAttachment) -> None:
    arq_pool = getattr(request.app.state, "arq_pool", None)
    if arq_pool is not None:
        await arq_pool.enqueue_job("task_process_file", str(attachment.id))


@router.post("/upload", response_model=FileAttachment, status_code=status.HTTP_201_CREATED)
async def upload_file(
    request: Request,
    file: UploadFile = File(...),
    category: str | None = Form(None),
    tags: str | None = Form(None),
    description: str | None = Form(None),
    event_id: UUID | None = Form(None),
    timeline_id: UUID | None = Form(None),
    source_extension_id: str | None = Form(None),
    db_session: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> FileAttachment:
    tag_list = [t.strip() for t in tags.split(",")] if tags else []
    try:
        attachment = await create_attachment(
            session=db_session,
            file=file,
            owner_user_id=current_user.id,
            category=category,
            tags=tag_list,
            description=description,
            event_id=event_id,
            timeline_id=timeline_id,
            source_extension_id=source_extension_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    await db_session.commit()
    await db_session.refresh(attachment)
    await _enqueue_artifact(request, attachment)
    return attachment


@router.post("/device-upload", response_model=FileAttachment, status_code=status.HTTP_201_CREATED)
@limiter.limit(settings.RATE_LIMIT_INGEST)
async def device_upload_file(
    request: Request,
    file: UploadFile = File(...),
    source_extension_id: str = Form(...),
    category: str | None = Form(None),
    tags: str | None = Form(None),
    description: str | None = Form(None),
    db_session: AsyncSession = Depends(get_session),
    device: Device = Depends(verify_device),
) -> FileAttachment:
    """Device-authenticated capture path for `artifact_source` extensions."""
    if device.user_id is None:
        raise HTTPException(status_code=403, detail="Device is not assigned to a user")
    try:
        attachment = await create_attachment(
            session=db_session,
            file=file,
            owner_user_id=device.user_id,
            category=category,
            tags=[tag.strip() for tag in tags.split(",")] if tags else [],
            description=description,
            source_extension_id=source_extension_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    await db_session.commit()
    await db_session.refresh(attachment)
    await _enqueue_artifact(request, attachment)
    return attachment


@router.get("/{file_id}", response_model=FileAttachment)
async def get_file_metadata(
    file_id: UUID,
    db_session: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> FileAttachment:
    attachment = await _owned_attachment(db_session, file_id, current_user.id)
    if not attachment:
        raise HTTPException(status_code=404, detail="File not found")
    return attachment


@router.get("/{file_id}/download")
async def download_file(
    file_id: UUID,
    db_session: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> FileResponse:
    attachment = await _owned_attachment(db_session, file_id, current_user.id)
    if not attachment:
        raise HTTPException(status_code=404, detail="File not found")

    file_path = UPLOAD_DIR / attachment.stored_path
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="Physical file not found")

    return FileResponse(
        path=file_path,
        filename=attachment.filename,
        media_type=attachment.mime_type,
    )


@router.get("/", response_model=list[FileAttachment])
async def list_files(
    pagination: Pagination = Depends(),
    category: str | None = None,
    q: str | None = None,
    db_session: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> list[FileAttachment]:
    stmt = (
        select(FileAttachment)
        .where(FileAttachment.owner_user_id == current_user.id)
        .order_by(col(FileAttachment.created_at).desc())
    )

    if category:
        stmt = stmt.where(FileAttachment.category == category)
    if q:
        stmt = stmt.where(
            or_(
                col(FileAttachment.filename).ilike(f"%{q}%"),
                col(FileAttachment.description).ilike(f"%{q}%"),
            )
        )

    stmt = stmt.offset(pagination.offset).limit(pagination.limit)
    result = await db_session.execute(stmt)
    return result.scalars().all()


@router.post("/{file_id}/process", response_model=FileAttachment)
async def process_file(
    file_id: UUID,
    force: bool = False,
    db_session: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> FileAttachment:
    if await _owned_attachment(db_session, file_id, current_user.id) is None:
        raise HTTPException(status_code=404, detail="File not found")
    try:
        attachment = await process_artifact(db_session, file_id, force=force)
        await db_session.commit()
        await db_session.refresh(attachment)
        return attachment
    except ValueError as exc:
        await db_session.commit()
        raise HTTPException(status_code=409, detail=str(exc))
    except RuntimeError as exc:
        await db_session.commit()
        raise HTTPException(status_code=503, detail=str(exc))


@router.get("/{file_id}/content", response_model=list[ContentChunk])
async def get_file_content(
    file_id: UUID,
    db_session: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> list[ContentChunk]:
    if await _owned_attachment(db_session, file_id, current_user.id) is None:
        raise HTTPException(status_code=404, detail="File not found")
    chunks = (
        await db_session.execute(
            select(ContentChunk)
            .where(ContentChunk.file_id == file_id)
            .where(ContentChunk.is_superseded == False)
            .order_by(ContentChunk.sequence)
        )
    ).scalars().all()
    return chunks


@router.get("/{file_id}/memory-proposals", response_model=list[MemoryProposal])
async def get_file_memory_proposals(
    file_id: UUID,
    db_session: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> list[MemoryProposal]:
    if await _owned_attachment(db_session, file_id, current_user.id) is None:
        raise HTTPException(status_code=404, detail="File not found")
    return (
        await db_session.execute(
            select(MemoryProposal)
            .where(MemoryProposal.file_id == file_id)
            .order_by(MemoryProposal.created_at.desc())
        )
    ).scalars().all()


@router.post("/memory-proposals/{proposal_id}/review", response_model=MemoryProposal)
async def review_proposal(
    proposal_id: UUID,
    body: ProposalReview,
    db_session: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> MemoryProposal:
    proposal = await db_session.get(MemoryProposal, proposal_id)
    if proposal is None or await _owned_attachment(
        db_session, proposal.file_id, current_user.id
    ) is None:
        raise HTTPException(status_code=404, detail="Memory proposal not found")
    try:
        proposal = await review_memory_proposal(db_session, proposal_id, body.decision)
        await db_session.commit()
        await db_session.refresh(proposal)
        return proposal
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
