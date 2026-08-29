import hashlib
import json
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from app.models.intelligence import DirtyScope


def _now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


async def mark_dirty_scope(
    session: AsyncSession,
    *,
    owner_user_id: uuid.UUID,
    reason: str,
    occurred_from: datetime | None = None,
    occurred_until: datetime | None = None,
    entity_ids: list[uuid.UUID] | None = None,
    source_refs: list[dict[str, Any]] | None = None,
    materiality: float = 0.0,
    quiet_period: timedelta = timedelta(minutes=30),
) -> DirtyScope:
    """Coalesce equivalent invalidations so late data does not cause AI churn."""
    normalized_entities = sorted(str(value) for value in (entity_ids or []))
    normalized_sources = source_refs or []
    dependency_hash = hashlib.sha256(
        json.dumps(
            {
                "reason": reason,
                "occurred_from": occurred_from,
                "occurred_until": occurred_until,
                "entity_ids": normalized_entities,
                "source_refs": normalized_sources,
            },
            sort_keys=True,
            default=str,
            separators=(",", ":"),
        ).encode()
    ).hexdigest()
    scope = (
        await session.execute(
            select(DirtyScope).where(
                DirtyScope.owner_user_id == owner_user_id,
                DirtyScope.dependency_hash == dependency_hash,
                DirtyScope.status.in_(("pending", "queued", "running")),
            )
        )
    ).scalar_one_or_none()
    now = _now()
    if scope is None:
        scope = DirtyScope(
            owner_user_id=owner_user_id,
            reason=reason,
            occurred_from=occurred_from,
            occurred_until=occurred_until,
            entity_ids=normalized_entities,
            source_refs=normalized_sources,
            dependency_hash=dependency_hash,
            materiality=max(0.0, min(1.0, materiality)),
            quiet_until=now + quiet_period,
        )
    else:
        scope.materiality = max(scope.materiality, max(0.0, min(1.0, materiality)))
        scope.quiet_until = max(scope.quiet_until or now, now + quiet_period)
        scope.updated_at = now
    session.add(scope)
    await session.flush()
    return scope
