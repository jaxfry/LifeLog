import uuid
from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import col, select

from app.models.kernel import Entity, Measurement


def _now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


async def create_measurement(
    session: AsyncSession,
    *,
    entity_id: uuid.UUID,
    metric: str,
    value: float | None = None,
    value_text: str | None = None,
    unit: str | None = None,
    occurred_at: datetime | None = None,
    confidence: float | None = None,
    source_event_id: uuid.UUID | None = None,
    source_file_id: uuid.UUID | None = None,
    extractor: str | None = None,
    extraction_version: int | None = None,
) -> Measurement:
    """Write one numeric or text fact about an entity; never updated in place."""
    if value is None and value_text is None:
        raise ValueError("measurement requires a numeric value or text value")
    entity = await session.get(Entity, entity_id)
    if entity is None:
        raise ValueError("measurement entity does not exist")
    measurement = Measurement(
        owner_user_id=entity.owner_user_id,
        entity_id=entity_id,
        metric=metric,
        value=value,
        value_text=value_text,
        unit=unit,
        occurred_at=occurred_at,
        confidence=confidence,
        source_event_id=source_event_id,
        source_file_id=source_file_id,
        extractor=extractor,
        extraction_version=extraction_version,
    )
    session.add(measurement)
    await session.flush()
    return measurement


async def measurement_exists(
    session: AsyncSession,
    *,
    source_event_id: uuid.UUID | None,
    source_file_id: uuid.UUID | None,
    entity_id: uuid.UUID,
    metric: str,
    extractor: str,
    extraction_version: int,
) -> uuid.UUID | None:
    statement = select(Measurement.id).where(
        Measurement.entity_id == entity_id,
        Measurement.metric == metric,
        Measurement.extractor == extractor,
        Measurement.extraction_version == extraction_version,
    )
    if source_event_id is not None:
        statement = statement.where(Measurement.source_event_id == source_event_id)
    if source_file_id is not None:
        statement = statement.where(Measurement.source_file_id == source_file_id)
    return (await session.execute(statement.limit(1))).scalars().first()


async def aggregate_measurements(
    session: AsyncSession,
    *,
    entity_id: uuid.UUID | None = None,
    entity_type: str | None = None,
    metric: str | None = None,
    occurred_from: datetime | None = None,
    occurred_until: datetime | None = None,
    area_id: uuid.UUID | None = None,
    user_id: uuid.UUID | None = None,
    limit: int = 50_000,
) -> list[dict]:
    """Current numeric facts grouped by entity and metric, with summary statistics."""
    statement = select(Measurement, Entity).join(
        Entity, Measurement.entity_id == Entity.id
    ).where(Measurement.is_superseded == False, Measurement.value.is_not(None))
    if entity_id:
        from app.services.kernel import entity_family_ids

        family = await entity_family_ids(session, entity_id)
        statement = statement.where(Measurement.entity_id.in_(family))
    if entity_type:
        statement = statement.where(Entity.entity_type == entity_type)
    if metric:
        statement = statement.where(Measurement.metric == metric)
    if user_id is not None:
        statement = statement.where(Measurement.owner_user_id == user_id)
    if occurred_from:
        statement = statement.where(Measurement.occurred_at >= occurred_from)
    if occurred_until:
        statement = statement.where(Measurement.occurred_at <= occurred_until)
    rows = (await session.execute(statement.order_by(col(Measurement.occurred_at).desc()).limit(limit))).all()

    groups: dict[tuple[uuid.UUID, str], dict] = {}
    requested_entity: Entity | None = None
    if entity_id is not None:
        from app.services.kernel import resolve_current_entity

        requested_entity = await resolve_current_entity(session, entity_id)
    for measurement, entity in rows:
        from app.services.kernel import resolve_current_entity

        current = requested_entity or await resolve_current_entity(session, entity.id)
        if current is None:
            continue
        if user_id is not None and current.owner_user_id != user_id:
            continue
        if area_id is not None and user_id is not None:
            from app.services.context import target_visible

            if not await target_visible(
                session,
                user_id=user_id,
                target_type="entity",
                target_id=current.id,
                area_id=area_id,
            ):
                continue
        entity = current
        key = (entity.id, measurement.metric)
        group = groups.setdefault(
            key,
            {
                "entity_id": entity.id,
                "entity_name": entity.name,
                "metric": measurement.metric,
                "unit": measurement.unit,
                "values": [],
            },
        )
        group["values"].append(measurement.value)

    results = []
    for _key, group in groups.items():
        values = group["values"]
        results.append(
            {
                "entity_id": group["entity_id"],
                "entity_name": group["entity_name"],
                "metric": group["metric"],
                "unit": group["unit"],
                "count": len(values),
                "sum": round(sum(values), 6),
                "average": round(sum(values) / len(values), 6),
                "minimum": round(min(values), 6),
                "maximum": round(max(values), 6),
                "latest": round(values[0], 6),
            }
        )
    results.sort(key=lambda item: (item["entity_name"] or "", item["metric"]))
    return results
