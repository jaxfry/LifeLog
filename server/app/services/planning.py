from datetime import UTC, datetime, time, timedelta

from sqlalchemy import func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import col, select

from app.models.files import Commitment, CommitmentProgress, PlanBlock

PLANNER_VERSION = 1


async def generate_plan(
    session: AsyncSession,
    start_at: datetime,
    end_at: datetime,
    *,
    daily_capacity_minutes: int = 120,
    block_minutes: int = 45,
) -> list[PlanBlock]:
    """Create deterministic suggested blocks from due dates, effort, and progress."""
    if end_at <= start_at:
        raise ValueError("end_at must be after start_at")
    if not 15 <= daily_capacity_minutes <= 1440:
        raise ValueError("daily_capacity_minutes must be between 15 and 1440")
    if not 5 <= block_minutes <= daily_capacity_minutes:
        raise ValueError("block_minutes must be between 5 and daily capacity")

    old_suggestions = (
        await session.execute(
            select(PlanBlock)
            .where(PlanBlock.status == "suggested")
            .where(PlanBlock.start_at < end_at)
            .where(PlanBlock.end_at > start_at)
        )
    ).scalars().all()
    for block in old_suggestions:
        block.status = "cancelled"
        block.updated_at = _utcnow()
        session.add(block)

    commitments = (
        await session.execute(
            select(Commitment)
            .where(Commitment.status.in_(["suggested", "planned", "in_progress"]))
            .order_by(col(Commitment.due_at).asc().nulls_last(), col(Commitment.created_at).asc())
        )
    ).scalars().all()
    accepted_blocks = (
        await session.execute(
            select(PlanBlock)
            .where(PlanBlock.status.in_(["accepted", "completed"]))
            .where(PlanBlock.start_at < end_at)
            .where(PlanBlock.end_at > start_at)
        )
    ).scalars().all()

    generated: list[PlanBlock] = []
    cursor = start_at
    day_start_time = start_at.time()
    used_by_day: dict[str, int] = {}
    for block in accepted_blocks:
        key = block.start_at.date().isoformat()
        used_by_day[key] = used_by_day.get(key, 0) + int((block.end_at - block.start_at).total_seconds() // 60)
    for commitment in commitments:
        progress_minutes = (
            await session.execute(
                select(func.coalesce(func.sum(CommitmentProgress.amount), 0.0))
                .where(CommitmentProgress.commitment_id == commitment.id)
                .where(CommitmentProgress.unit == "minutes")
            )
        ).scalar_one()
        estimate = _estimated_minutes(commitment, block_minutes)
        remaining = max(estimate - int(progress_minutes), 0)
        while remaining > 0:
            cursor = _next_available(
                cursor,
                end_at,
                daily_capacity_minutes,
                used_by_day,
                [*accepted_blocks, *generated],
                day_start_time,
            )
            if cursor >= end_at or (commitment.due_at is not None and cursor >= commitment.due_at):
                break
            available_today = daily_capacity_minutes - used_by_day.get(cursor.date().isoformat(), 0)
            duration = min(block_minutes, remaining, available_today)
            block_end = min(cursor + timedelta(minutes=duration), end_at)
            if commitment.due_at is not None:
                block_end = min(block_end, commitment.due_at)
            next_existing = min(
                (block.start_at for block in [*accepted_blocks, *generated] if cursor < block.start_at < block_end),
                default=None,
            )
            if next_existing is not None:
                block_end = next_existing
            if block_end <= cursor:
                break
            block = PlanBlock(
                commitment_id=commitment.id,
                start_at=cursor,
                end_at=block_end,
                rationale=_rationale(commitment, remaining),
                planner_version=PLANNER_VERSION,
            )
            session.add(block)
            generated.append(block)
            actual_minutes = int((block_end - cursor).total_seconds() // 60)
            used_by_day[cursor.date().isoformat()] = used_by_day.get(cursor.date().isoformat(), 0) + actual_minutes
            remaining -= actual_minutes
            cursor = block_end

    await session.flush()
    return generated


def _next_available(
    cursor: datetime,
    end_at: datetime,
    daily_capacity: int,
    used_by_day: dict[str, int],
    existing: list[PlanBlock],
    day_start_time: time,
) -> datetime:
    while cursor < end_at:
        day_key = cursor.date().isoformat()
        if used_by_day.get(day_key, 0) >= daily_capacity:
            cursor = datetime.combine(cursor.date() + timedelta(days=1), day_start_time)
            continue
        overlap = next(
            (block for block in existing if block.start_at < cursor + timedelta(minutes=1) and block.end_at > cursor),
            None,
        )
        if overlap is not None:
            cursor = overlap.end_at
            continue
        return cursor
    return cursor


def _estimated_minutes(commitment: Commitment, default: int) -> int:
    value = (commitment.data or {}).get("estimated_minutes", default)
    try:
        return max(int(value), 0)
    except (TypeError, ValueError):
        return default


def _rationale(commitment: Commitment, remaining: int) -> str:
    due = commitment.due_at.isoformat() if commitment.due_at else "no fixed deadline"
    return f"{remaining} estimated minutes remain; {due}."


def _utcnow() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)
