import uuid
from datetime import UTC, datetime
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import col, select, update

from app.core.database import get_session
from app.core.dependencies import Pagination, get_current_user
from app.models.auth import User
from app.models.files import Commitment, CommitmentProgress, Notification, PlanBlock
from app.services.commitments import reminder_time
from app.services.planning import generate_plan

router = APIRouter()

CommitmentStatus = Literal["suggested", "planned", "in_progress", "completed", "cancelled"]


class CommitmentCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str = Field(min_length=1, max_length=500)
    description: str | None = None
    status: CommitmentStatus = "planned"
    due_at: datetime | None = None
    not_before: datetime | None = None
    data: dict = Field(default_factory=dict)


class CommitmentUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str | None = Field(default=None, min_length=1, max_length=500)
    description: str | None = None
    status: CommitmentStatus | None = None
    due_at: datetime | None = None
    not_before: datetime | None = None


class ProgressCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    event_id: uuid.UUID | None = None
    amount: float = 1.0
    unit: str = Field(default="observation", min_length=1, max_length=100)
    note: str | None = None
    confidence: float | None = Field(default=None, ge=0, le=1)
    observed_at: datetime | None = None


class PlanGenerate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    start_at: datetime
    end_at: datetime
    daily_capacity_minutes: int = Field(default=120, ge=15, le=1440)
    block_minutes: int = Field(default=45, ge=5, le=720)


class PlanBlockUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: Literal["suggested", "accepted", "completed", "skipped", "cancelled"]


@router.get("/commitments", response_model=list[Commitment])
async def list_commitments(
    status_filter: CommitmentStatus | None = None,
    pagination: Pagination = Depends(),
    db_session: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> list[Commitment]:
    statement = select(Commitment).order_by(col(Commitment.due_at).asc(), col(Commitment.created_at).desc())
    if status_filter:
        statement = statement.where(Commitment.status == status_filter)
    return (
        await db_session.execute(statement.offset(pagination.offset).limit(pagination.limit))
    ).scalars().all()


@router.post("/commitments", response_model=Commitment, status_code=201)
async def create_commitment(
    body: CommitmentCreate,
    db_session: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> Commitment:
    commitment = Commitment(
        title=body.title,
        description=body.description,
        status=body.status,
        due_at=_normalize_dt(body.due_at),
        not_before=_normalize_dt(body.not_before),
        data=body.data,
    )
    _validate_window(commitment)
    db_session.add(commitment)
    await db_session.flush()
    await _sync_notification(db_session, commitment)
    await db_session.commit()
    await db_session.refresh(commitment)
    return commitment


@router.patch("/commitments/{commitment_id}", response_model=Commitment)
async def update_commitment(
    commitment_id: uuid.UUID,
    body: CommitmentUpdate,
    db_session: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> Commitment:
    commitment = await db_session.get(Commitment, commitment_id)
    if commitment is None:
        raise HTTPException(status_code=404, detail="Commitment not found")
    updates = body.model_dump(exclude_unset=True)
    for key, value in updates.items():
        if key in {"due_at", "not_before"}:
            value = _normalize_dt(value)
        setattr(commitment, key, value)
    if body.status == "completed" and commitment.completed_at is None:
        commitment.completed_at = _utcnow()
    elif body.status is not None and body.status != "completed":
        commitment.completed_at = None
    commitment.updated_at = _utcnow()
    _validate_window(commitment)
    db_session.add(commitment)
    await _sync_notification(db_session, commitment)
    await db_session.commit()
    await db_session.refresh(commitment)
    return commitment


@router.get("/commitments/{commitment_id}/progress", response_model=list[CommitmentProgress])
async def list_commitment_progress(
    commitment_id: uuid.UUID,
    db_session: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> list[CommitmentProgress]:
    return (
        await db_session.execute(
            select(CommitmentProgress)
            .where(CommitmentProgress.commitment_id == commitment_id)
            .order_by(col(CommitmentProgress.observed_at).asc())
        )
    ).scalars().all()


@router.post("/commitments/{commitment_id}/progress", response_model=CommitmentProgress, status_code=201)
async def record_commitment_progress(
    commitment_id: uuid.UUID,
    body: ProgressCreate,
    db_session: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> CommitmentProgress:
    commitment = await db_session.get(Commitment, commitment_id)
    if commitment is None:
        raise HTTPException(status_code=404, detail="Commitment not found")
    if body.event_id is not None:
        from app.models.ingest import Event

        if await db_session.get(Event, body.event_id) is None:
            raise HTTPException(status_code=400, detail="Event not found")
    progress = CommitmentProgress(
        commitment_id=commitment.id,
        event_id=body.event_id,
        amount=body.amount,
        unit=body.unit,
        note=body.note,
        confidence=body.confidence,
        observed_at=_normalize_dt(body.observed_at) or _utcnow(),
    )
    db_session.add(progress)
    if commitment.status in {"suggested", "planned"}:
        commitment.status = "in_progress"
        commitment.updated_at = _utcnow()
        db_session.add(commitment)
    await db_session.commit()
    await db_session.refresh(progress)
    return progress


@router.get("/plan", response_model=list[PlanBlock])
async def list_plan_blocks(
    start_at: datetime | None = None,
    end_at: datetime | None = None,
    pagination: Pagination = Depends(),
    db_session: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> list[PlanBlock]:
    statement = select(PlanBlock).where(PlanBlock.status != "cancelled")
    if start_at is not None:
        statement = statement.where(PlanBlock.end_at > _normalize_dt(start_at))
    if end_at is not None:
        statement = statement.where(PlanBlock.start_at < _normalize_dt(end_at))
    statement = statement.order_by(col(PlanBlock.start_at).asc())
    return (
        await db_session.execute(statement.offset(pagination.offset).limit(pagination.limit))
    ).scalars().all()


@router.post("/plan/generate", response_model=list[PlanBlock])
async def generate_suggested_plan(
    body: PlanGenerate,
    db_session: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> list[PlanBlock]:
    try:
        blocks = await generate_plan(
            db_session,
            _normalize_dt(body.start_at),
            _normalize_dt(body.end_at),
            daily_capacity_minutes=body.daily_capacity_minutes,
            block_minutes=body.block_minutes,
        )
        await db_session.commit()
        return blocks
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.patch("/plan/{block_id}", response_model=PlanBlock)
async def update_plan_block(
    block_id: uuid.UUID,
    body: PlanBlockUpdate,
    db_session: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> PlanBlock:
    block = await db_session.get(PlanBlock, block_id)
    if block is None:
        raise HTTPException(status_code=404, detail="Plan block not found")
    block.status = body.status
    block.updated_at = _utcnow()
    db_session.add(block)
    await db_session.commit()
    await db_session.refresh(block)
    return block


@router.get("/notifications", response_model=list[Notification])
async def list_notifications(
    due_only: bool = False,
    pagination: Pagination = Depends(),
    db_session: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> list[Notification]:
    statement = select(Notification).where(Notification.status == "pending")
    if due_only:
        statement = statement.where(Notification.scheduled_for <= _utcnow())
    statement = statement.order_by(col(Notification.scheduled_for).asc())
    return (
        await db_session.execute(statement.offset(pagination.offset).limit(pagination.limit))
    ).scalars().all()


@router.post("/notifications/{notification_id}/dismiss", response_model=Notification)
async def dismiss_notification(
    notification_id: uuid.UUID,
    db_session: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> Notification:
    notification = await db_session.get(Notification, notification_id)
    if notification is None:
        raise HTTPException(status_code=404, detail="Notification not found")
    notification.status = "dismissed"
    db_session.add(notification)
    await db_session.commit()
    await db_session.refresh(notification)
    return notification


async def _sync_notification(session: AsyncSession, commitment: Commitment) -> None:
    await session.execute(
        update(Notification)
        .where(Notification.commitment_id == commitment.id)
        .where(Notification.status == "pending")
        .values(status="cancelled")
    )
    if commitment.due_at is not None and commitment.status in {"suggested", "planned", "in_progress"}:
        scheduled_for = reminder_time(commitment)
        if scheduled_for is None:
            return
        session.add(
            Notification(
                commitment_id=commitment.id,
                title=commitment.title,
                body=commitment.description,
                scheduled_for=scheduled_for,
            )
        )
        await session.flush()


def _normalize_dt(value: datetime | None) -> datetime | None:
    if value is not None and value.tzinfo is not None:
        return value.astimezone(UTC).replace(tzinfo=None)
    return value


def _utcnow() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def _validate_window(commitment: Commitment) -> None:
    if (
        commitment.due_at is not None
        and commitment.not_before is not None
        and commitment.due_at < commitment.not_before
    ):
        raise HTTPException(status_code=400, detail="due_at must not be before not_before")
