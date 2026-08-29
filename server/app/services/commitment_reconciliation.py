from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select, update

from app.loader.contracts import ExtensionManifest
from app.models.config import Extension
from app.models.files import Commitment, Notification, PlanBlock
from app.models.ingest import Event, RawLog
from app.models.sources import SourceConnection
from app.services.commitments import reminder_time
from app.services.context import copy_context
from app.services.inbox import upsert_review_item


def _now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def _read_path(value: dict, path: str | None) -> object | None:
    if not path:
        return None
    current: object = value
    for part in path.split("."):
        if not isinstance(current, dict) or part not in current:
            return None
        current = current[part]
    return current


def _parse_datetime(value: object | None) -> datetime | None:
    if value in (None, ""):
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None
    if parsed.tzinfo is not None:
        return parsed.astimezone(UTC).replace(tzinfo=None)
    return parsed


async def reconcile_event_commitments(session: AsyncSession, event: Event, raw_log: RawLog) -> int:
    """Project manifest mappings and surface consequential source revisions for review."""
    if raw_log.source_record_id is None:
        return 0
    extension = await session.get(Extension, raw_log.extension_id)
    if extension is None:
        return 0
    manifest = ExtensionManifest.model_validate(extension.config)
    connection = (
        await session.get(SourceConnection, raw_log.source_connection_id)
        if raw_log.source_connection_id is not None
        else None
    )
    if connection is None:
        return 0
    changes = 0
    for index, mapping in enumerate(manifest.commitment_mappings):
        if mapping.event_type != event.event_type:
            continue
        title_value = _read_path(event.data or {}, mapping.title_path)
        if title_value is None or not str(title_value).strip():
            continue
        title = str(title_value).strip()
        description_value = _read_path(event.data or {}, mapping.description_path)
        description = str(description_value).strip() if description_value is not None else None
        due_at = _parse_datetime(_read_path(event.data or {}, mapping.due_at_path))
        not_before = _parse_datetime(_read_path(event.data or {}, mapping.not_before_path))
        if due_at is not None and not_before is not None and due_at < not_before:
            continue
        mapping_key = f"manifest:{raw_log.extension_id}:commitment:{index}"
        current = (
            await session.execute(
                select(Commitment)
                .where(
                    Commitment.source_record_id == raw_log.source_record_id,
                    Commitment.mapping_key == mapping_key,
                    Commitment.superseded_by.is_(None),
                )
                .order_by(Commitment.created_at.desc())
                .limit(1)
            )
        ).scalars().first()
        if current is not None and (
            current.title,
            current.description,
            current.due_at,
            current.not_before,
        ) == (title, description, due_at, not_before):
            continue

        commitment = Commitment(
            owner_user_id=connection.user_id,
            title=title,
            description=description,
            due_at=due_at,
            not_before=not_before,
            status="completed" if current and current.status == "completed" else "suggested",
            completed_at=current.completed_at if current and current.status == "completed" else None,
            confidence=mapping.confidence,
            source_event_id=event.id,
            source_record_id=raw_log.source_record_id,
            mapping_key=mapping_key,
            data={
                "source_connection_id": str(raw_log.source_connection_id),
                "external_key": raw_log.external_key,
                "external_revision": raw_log.external_revision,
                "requires_review": current is not None,
            },
        )
        session.add(commitment)
        await session.flush()
        await copy_context(
            session,
            from_type="event",
            from_id=event.id,
            to_type="commitment",
            to_id=commitment.id,
        )

        if current is None:
            scheduled_for = reminder_time(commitment)
            if scheduled_for is not None:
                session.add(
                    Notification(
                        owner_user_id=connection.user_id,
                        commitment_id=commitment.id,
                        title=commitment.title,
                        body=commitment.description,
                        scheduled_for=scheduled_for,
                        payload={"type": "commitment_reminder", "source": "manifest"},
                    )
                )
        else:
            previous_status = current.status
            current.superseded_by = commitment.id
            if current.status != "completed":
                current.status = "cancelled"
            current.updated_at = _now()
            session.add(current)
            await session.execute(
                update(Notification)
                .where(Notification.commitment_id == current.id, Notification.status == "pending")
                .values(status="cancelled")
            )
            await session.execute(
                update(PlanBlock)
                .where(
                    PlanBlock.commitment_id == current.id,
                    PlanBlock.status.in_(("suggested", "accepted")),
                )
                .values(status="cancelled", updated_at=_now())
            )
            session.add(
                Notification(
                    owner_user_id=connection.user_id,
                    commitment_id=commitment.id,
                    title=f"Review source change: {commitment.title}",
                    body="A connected source changed this commitment. Review the new details before replanning.",
                    scheduled_for=_now(),
                    payload={
                        "type": "commitment_revision",
                        "previous_commitment_id": str(current.id),
                        "previous_due_at": current.due_at.isoformat() if current.due_at else None,
                        "new_due_at": due_at.isoformat() if due_at else None,
                        "external_key": raw_log.external_key,
                    },
                )
            )
            connection = (
                await session.get(SourceConnection, raw_log.source_connection_id)
                if raw_log.source_connection_id is not None
                else None
            )
            if connection is not None:
                await upsert_review_item(
                    session,
                    user_id=connection.user_id,
                    kind="commitment_revision",
                    source_type="commitment_revision",
                    source_id=commitment.id,
                    title=f"Review changed commitment: {commitment.title}",
                    summary="A connected source changed consequential commitment details.",
                    payload={
                        "previous_commitment_id": str(current.id),
                        "previous_status": previous_status,
                        "previous_due_at": current.due_at.isoformat() if current.due_at else None,
                        "new_due_at": due_at.isoformat() if due_at else None,
                        "external_key": raw_log.external_key,
                    },
                    consequential=True,
                )
        changes += 1
    await session.flush()
    return changes
