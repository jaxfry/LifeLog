import re
import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import and_, or_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select, update

from app.core.logger import get_logger
from app.models.ingest import Event
from app.models.kernel import Entity, EntityAlias, Relation

logger = get_logger(__name__)

_VALID_TYPES = ("entity", "event")


def _now() -> datetime:
    """Naive-UTC now, matching the model convention."""
    return datetime.now(UTC).replace(tzinfo=None)


async def create_entity(
    session: AsyncSession,
    entity_type: str,
    name: str | None = None,
    data: dict[str, Any] | None = None,
    confidence: float | None = None,
) -> Entity:
    """Create a new entity in the kernel fact store."""
    entity_type = _clean_label(entity_type, "entity_type")
    name = name.strip() if name is not None else None
    if name == "":
        name = None
    _validate_confidence(confidence)
    entity = Entity(
        entity_type=entity_type,
        name=name,
        canonical_key=_normalized_key(name) if name else None,
        data=data,
        confidence=confidence,
    )
    session.add(entity)
    await session.flush()
    return entity


async def get_current_entity(
    session: AsyncSession,
    entity_id: uuid.UUID,
) -> Entity | None:
    """Fetch the current (non-superseded) version of an entity, if any."""
    statement = select(Entity).where(
        Entity.id == entity_id,
        Entity.is_superseded == False,
    )
    result = await session.execute(statement)
    return result.scalars().first()


async def get_current_entity_by_name(
    session: AsyncSession,
    entity_type: str,
    name: str,
) -> Entity | None:
    """Fetch the current entity of a type matching this name.

    Match order: exact (case-insensitive), then against known aliases and
    normalized token keys (separator-insensitive, e.g. "VS-Code" == "vs code").
    """
    exact = (
        await session.execute(
            select(Entity)
            .where(Entity.entity_type == entity_type)
            .where(Entity.canonical_key == _normalized_key(name))
            .where(Entity.is_superseded == False)
            .limit(1)
        )
    ).scalars().first()
    if exact is not None:
        return exact

    key = _normalized_key(name)
    alias_match = (
        await session.execute(
            select(Entity)
            .join(EntityAlias, EntityAlias.entity_id == Entity.id)
            .where(Entity.entity_type == entity_type)
            .where(Entity.is_superseded == False)
            .where(EntityAlias.canonical_key == key)
            .limit(1)
        )
    ).scalars().first()
    return alias_match


def _normalized_key(value: str) -> str:
    """Separator-insensitive lowercase token key, e.g. 'VS-Code' == 'vs code'."""
    return " ".join(re.findall(r"[a-z0-9]+", value.casefold()))


async def add_entity_alias(
    session: AsyncSession,
    entity_id: uuid.UUID,
    alias: str,
) -> Entity:
    """Record a variant name on an entity so future mentions resolve to it.

    Idempotent: skips aliases equal to the canonical name or already known
    (by normalized key). Returns the (possibly updated) entity.
    """
    result = await session.execute(select(Entity).where(Entity.id == entity_id))
    entity = result.scalars().first()
    if entity is None:
        raise ValueError(f"entity {entity_id} does not exist")
    if not alias or (entity.name and alias.casefold() == entity.name.casefold()):
        return entity

    alias_key = _normalized_key(alias)
    if not alias_key:
        return entity

    data = dict(entity.data or {})
    aliases = [a for a in data.get("aliases", []) if isinstance(a, str)]
    if any(_normalized_key(a) == alias_key for a in aliases):
        return entity
    if len(aliases) >= 32:
        aliases.pop(0)
    aliases.append(alias)
    data["aliases"] = aliases
    entity.data = data
    session.add(entity)
    existing_alias = (
        await session.execute(
            select(EntityAlias.id)
            .where(EntityAlias.entity_id == entity.id)
            .where(EntityAlias.canonical_key == alias_key)
        )
    ).scalars().first()
    if existing_alias is None:
        session.add(EntityAlias(entity_id=entity.id, alias=alias, canonical_key=alias_key))
    await session.flush()
    return entity


async def get_entity_history(
    session: AsyncSession,
    entity_id: uuid.UUID,
) -> list[Entity]:
    """
    Return the full supersession chain for an entity, oldest first.

    If the given id is superseded, walks back to the oldest version; if it is
    the current version, walks forward via superseded_by pointers.
    """
    result = await session.execute(select(Entity).where(Entity.id == entity_id))
    node = result.scalars().first()
    if node is None:
        return []

    chain: list[Entity] = []
    seen: set[uuid.UUID] = set()

    async def append_predecessors(current: Entity) -> None:
        predecessors = (
            await session.execute(select(Entity).where(Entity.superseded_by == current.id))
        ).scalars().all()
        for predecessor in predecessors:
            if predecessor.id not in seen:
                seen.add(predecessor.id)
                await append_predecessors(predecessor)
                chain.append(predecessor)

    await append_predecessors(node)
    if node.id not in seen:
        seen.add(node.id)
        chain.append(node)

    current = node
    while current.superseded_by is not None:
        if current.superseded_by in seen:
            break
        nxt_result = await session.execute(
            select(Entity).where(Entity.id == current.superseded_by)
        )
        nxt = nxt_result.scalars().first()
        if nxt is None:
            break
        chain.append(nxt)
        seen.add(nxt.id)
        current = nxt

    return chain


async def get_entity_graph(
    session: AsyncSession,
    entity_id: uuid.UUID,
    depth: int = 1,
    include_superseded: bool = False,
    relation_limit: int = 500,
) -> tuple[list[Entity], list[Event], list[Relation], bool]:
    """Return a bounded, evidence-preserving neighborhood around an entity."""
    requested = await session.get(Entity, entity_id)
    if requested is None:
        return [], [], [], False

    root = requested
    seen_successors: set[uuid.UUID] = set()
    while root.superseded_by is not None and root.id not in seen_successors:
        seen_successors.add(root.id)
        successor = await session.get(Entity, root.superseded_by)
        if successor is None:
            break
        root = successor

    equivalent_ids: set[uuid.UUID] = {root.id}
    equivalent_frontier = {root.id}
    while equivalent_frontier:
        predecessors = (
            await session.execute(select(Entity.id).where(Entity.superseded_by.in_(equivalent_frontier)))
        ).scalars().all()
        equivalent_frontier = set(predecessors) - equivalent_ids
        equivalent_ids.update(equivalent_frontier)

    nodes: set[tuple[str, uuid.UUID]] = {("entity", node_id) for node_id in equivalent_ids}
    frontier = nodes.copy()
    relations: dict[uuid.UUID, Relation] = {}
    truncated = False
    for _ in range(depth):
        clauses = []
        for node_type, node_id in frontier:
            clauses.extend(
                [
                    and_(Relation.subject_type == node_type, Relation.subject_id == node_id),
                    and_(Relation.object_type == node_type, Relation.object_id == node_id),
                ]
            )
        if not clauses:
            break
        remaining = relation_limit - len(relations)
        if remaining <= 0:
            truncated = True
            break
        statement = select(Relation).where(or_(*clauses)).order_by(Relation.created_at.desc()).limit(remaining + 1)
        if not include_superseded:
            statement = statement.where(Relation.is_superseded == False)
        found = (await session.execute(statement)).scalars().all()
        if len(found) > remaining:
            truncated = True
            found = found[:remaining]
        next_frontier: set[tuple[str, uuid.UUID]] = set()
        for relation in found:
            relations[relation.id] = relation
            next_frontier.add((relation.subject_type, relation.subject_id))
            next_frontier.add((relation.object_type, relation.object_id))
        next_frontier -= nodes
        nodes |= next_frontier
        frontier = next_frontier

    entity_ids = [node_id for node_type, node_id in nodes if node_type == "entity"]
    event_ids = [node_id for node_type, node_id in nodes if node_type == "event"]
    entities = (
        (await session.execute(select(Entity).where(Entity.id.in_(entity_ids)))).scalars().all()
        if entity_ids
        else []
    )
    events = (
        (await session.execute(select(Event).where(Event.id.in_(event_ids)))).scalars().all()
        if event_ids
        else []
    )
    return list(entities), list(events), list(relations.values()), truncated


async def create_relation(
    session: AsyncSession,
    subject_id: uuid.UUID,
    subject_type: str,
    predicate: str,
    object_id: uuid.UUID,
    object_type: str,
    occurred_from: datetime | None = None,
    occurred_until: datetime | None = None,
    confidence: float | None = None,
    source_event_id: uuid.UUID | None = None,
    source_file_id: uuid.UUID | None = None,
    source_chunk_id: uuid.UUID | None = None,
    extractor: str | None = None,
    extraction_version: int | None = None,
    data: dict[str, Any] | None = None,
) -> Relation:
    """Create a relation between two kernel endpoints (entities or events)."""
    if subject_type not in _VALID_TYPES:
        raise ValueError(
            f"subject_type must be one of {_VALID_TYPES}, got {subject_type!r}"
        )
    if object_type not in _VALID_TYPES:
        raise ValueError(
            f"object_type must be one of {_VALID_TYPES}, got {object_type!r}"
        )

    predicate = _clean_label(predicate, "predicate")
    _validate_confidence(confidence)
    if occurred_from is not None and occurred_until is not None and occurred_until < occurred_from:
        raise ValueError("occurred_until must not be before occurred_from")
    if extraction_version is not None and extraction_version < 1:
        raise ValueError("extraction_version must be at least 1")

    await _ensure_reference_exists(session, subject_id, subject_type, "subject")
    await _ensure_reference_exists(session, object_id, object_type, "object")
    if source_event_id is not None:
        await _ensure_reference_exists(session, source_event_id, "event", "source")

    relation = Relation(
        subject_id=subject_id,
        subject_type=subject_type,
        predicate=predicate,
        object_id=object_id,
        object_type=object_type,
        occurred_from=occurred_from,
        occurred_until=occurred_until,
        confidence=confidence,
        source_event_id=source_event_id,
        source_file_id=source_file_id,
        source_chunk_id=source_chunk_id,
        extractor=extractor,
        extraction_version=extraction_version,
        data=data,
    )
    session.add(relation)
    await session.flush()
    return relation


async def link_event(
    session: AsyncSession,
    event_id: uuid.UUID,
    predicate: str,
    object_id: uuid.UUID,
    object_type: str,
    **kwargs: Any,
) -> Relation:
    """Convenience wrapper: create a relation whose subject is an event."""
    return await create_relation(
        session,
        subject_id=event_id,
        subject_type="event",
        predicate=predicate,
        object_id=object_id,
        object_type=object_type,
        occurred_from=kwargs.get("occurred_from"),
        occurred_until=kwargs.get("occurred_until"),
        confidence=kwargs.get("confidence"),
        source_event_id=kwargs.get("source_event_id", event_id),
        source_file_id=kwargs.get("source_file_id"),
        source_chunk_id=kwargs.get("source_chunk_id"),
        extractor=kwargs.get("extractor"),
        extraction_version=kwargs.get("extraction_version"),
        data=kwargs.get("data"),
    )


async def supersede_entity(
    session: AsyncSession,
    entity_id: uuid.UUID,
    replacement_id: uuid.UUID | None = None,
) -> None:
    """Mark an entity superseded; kernel facts are never deleted."""
    if replacement_id == entity_id:
        raise ValueError("replacement entity must differ from the superseded entity")

    result = await session.execute(select(Entity).where(Entity.id == entity_id))
    entity = result.scalars().first()
    if entity is None:
        raise ValueError(f"entity {entity_id} does not exist")
    if entity.is_superseded:
        raise ValueError(f"entity {entity_id} is already superseded")

    if replacement_id is not None:
        replacement = await session.get(Entity, replacement_id)
        if replacement is None:
            raise ValueError(f"replacement entity {replacement_id} does not exist")
        if await _entity_chain_contains(session, replacement, entity_id):
            raise ValueError("supersession would create a cycle")
        if replacement.is_superseded:
            raise ValueError("replacement entity must be current")
        if replacement.entity_type != entity.entity_type:
            raise ValueError("replacement entity must have the same entity_type")

    entity.is_superseded = True
    entity.superseded_by = replacement_id
    session.add(entity)
    await session.flush()
    logger.info("Superseded entity %s -> %s", entity_id, replacement_id)


async def supersede_event(
    session: AsyncSession,
    event_id: uuid.UUID,
    replacement_id: uuid.UUID | None = None,
) -> None:
    """
    Mark an event superseded and supersede the kernel facts derived from it.

    Relations extracted from a superseded event must not outlive it; the
    entities it referenced may be shared by other events and are kept.
    """
    if replacement_id == event_id:
        raise ValueError("replacement event must differ from the superseded event")

    result = await session.execute(select(Event).where(Event.id == event_id))
    event = result.scalars().first()
    if event is None:
        raise ValueError(f"event {event_id} does not exist")
    if event.is_superseded:
        raise ValueError(f"event {event_id} is already superseded")
    if replacement_id is not None:
        replacement = await session.get(Event, replacement_id)
        if replacement is None:
            raise ValueError(f"replacement event {replacement_id} does not exist")
        if replacement.is_superseded:
            raise ValueError("replacement event must be current")

    event.is_superseded = True
    event.superseded_by = replacement_id
    session.add(event)

    invalidated_at = _now()
    await session.execute(
        update(Relation)
        .where(
            or_(
                Relation.source_event_id == event_id,
                and_(Relation.subject_type == "event", Relation.subject_id == event_id),
                and_(Relation.object_type == "event", Relation.object_id == event_id),
            )
        )
        .where(Relation.invalidated_at.is_(None))
        .values(is_superseded=True, invalidated_at=invalidated_at)
    )
    await session.flush()
    logger.info("Superseded event %s -> %s", event_id, replacement_id)


async def supersede_relation(
    session: AsyncSession,
    relation_id: uuid.UUID,
    replacement_id: uuid.UUID | None = None,
) -> None:
    """Mark a relation superseded; kernel facts are never deleted.

    Sets ``invalidated_at`` to the replacement's creation time or the current
    knowledge time if there is no replacement.
    """
    if replacement_id == relation_id:
        raise ValueError("replacement relation must differ from the superseded relation")

    result = await session.execute(select(Relation).where(Relation.id == relation_id))
    relation = result.scalars().first()
    if relation is None:
        raise ValueError(f"relation {relation_id} does not exist")
    if relation.is_superseded:
        raise ValueError(f"relation {relation_id} is already superseded")

    invalid_at: datetime | None = None
    if replacement_id is not None:
        result = await session.execute(select(Relation).where(Relation.id == replacement_id))
        replacement = result.scalars().first()
        if replacement is None:
            raise ValueError(f"replacement relation {replacement_id} does not exist")
        if replacement.is_superseded:
            raise ValueError("replacement relation must be current")
        invalid_at = replacement.created_at
    if invalid_at is None:
        invalid_at = _now()

    relation.is_superseded = True
    relation.superseded_by = replacement_id
    relation.invalidated_at = relation.invalidated_at or invalid_at
    session.add(relation)
    await session.flush()
    logger.info("Superseded relation %s -> %s", relation_id, replacement_id)


async def merge_entities(
    session: AsyncSession,
    survivor_id: uuid.UUID,
    merged_id: uuid.UUID,
) -> None:
    """
    Merge merged_id into survivor_id as a single transaction.

    Marks merged_id superseded and records its names on the survivor. Historical
    relations are deliberately not rewritten: their original endpoint is part
    of the evidence trail and can be resolved through ``superseded_by``.
    """
    if survivor_id == merged_id:
        raise ValueError("survivor and merged entities must differ")

    result = await session.execute(select(Entity).where(Entity.id == survivor_id))
    survivor = result.scalars().first()
    if survivor is None:
        raise ValueError(f"survivor entity {survivor_id} does not exist")

    result = await session.execute(select(Entity).where(Entity.id == merged_id))
    merged = result.scalars().first()
    if merged is None:
        raise ValueError(f"merged entity {merged_id} does not exist")
    if survivor.is_superseded or merged.is_superseded:
        raise ValueError("both entities must be current")
    if survivor.entity_type != merged.entity_type:
        raise ValueError("entities must have the same entity_type")

    merged.is_superseded = True
    merged.superseded_by = survivor_id
    session.add(merged)

    survivor_data = dict(survivor.data or {})
    merged_from_ids = survivor_data.get("merged_from_ids")
    if merged_from_ids is None or not isinstance(merged_from_ids, list):
        merged_from_ids = []
    if str(merged_id) not in merged_from_ids:
        merged_from_ids.append(str(merged_id))
    survivor_data["merged_from_ids"] = merged_from_ids
    aliases = [alias for alias in survivor_data.get("aliases", []) if isinstance(alias, str)]
    for alias in [merged.name, *((merged.data or {}).get("aliases", []))]:
        if isinstance(alias, str) and alias and not any(
            _normalized_key(existing) == _normalized_key(alias) for existing in aliases
        ):
            aliases.append(alias)
    if aliases:
        survivor_data["aliases"] = aliases[-32:]
    survivor.data = survivor_data
    session.add(survivor)
    for alias in aliases[-32:]:
        alias_key = _normalized_key(alias)
        existing_alias = (
            await session.execute(
                select(EntityAlias.id)
                .where(EntityAlias.entity_id == survivor.id)
                .where(EntityAlias.canonical_key == alias_key)
            )
        ).scalars().first()
        if existing_alias is None:
            session.add(EntityAlias(entity_id=survivor.id, alias=alias, canonical_key=alias_key))

    await session.flush()
    logger.info("Merged entity %s into %s", merged_id, survivor_id)


async def _ensure_reference_exists(
    session: AsyncSession,
    ref_id: uuid.UUID,
    ref_type: str,
    role: str,
) -> None:
    """Verify that an entity or event with the given id exists."""
    model: type[Entity] | type[Event] = Entity if ref_type == "entity" else Event
    result = await session.execute(select(model.id).where(model.id == ref_id))
    if result.scalars().first() is None:
        raise ValueError(f"{role} {ref_type} with id {ref_id} does not exist")


def _clean_label(value: str, field: str) -> str:
    cleaned = value.strip()
    if not cleaned:
        raise ValueError(f"{field} must not be empty")
    if len(cleaned) > 100:
        raise ValueError(f"{field} must be at most 100 characters")
    return cleaned


def _validate_confidence(confidence: float | None) -> None:
    if confidence is not None and not 0 <= confidence <= 1:
        raise ValueError("confidence must be between 0 and 1")


async def _entity_chain_contains(
    session: AsyncSession,
    entity: Entity,
    target_id: uuid.UUID,
) -> bool:
    seen: set[uuid.UUID] = set()
    current = entity
    while current.superseded_by is not None and current.id not in seen:
        seen.add(current.id)
        if current.superseded_by == target_id:
            return True
        next_entity = await session.get(Entity, current.superseded_by)
        if next_entity is None:
            return False
        current = next_entity
    return False
