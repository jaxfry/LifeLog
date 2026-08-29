import re
import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import and_, or_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select, update

from app.core.logger import get_logger
from app.models.context import ContextLink, MemoryPolicy
from app.models.ingest import Event
from app.models.kernel import Entity, EntityAlias, EntityMerge, Relation
from app.models.retrieval import SearchDocument
from app.services.context import copy_context, copy_policies

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
    owner_user_id: uuid.UUID | None = None,
    identity_namespace: str | None = None,
    external_identity: str | None = None,
) -> Entity:
    """Create a new entity in the kernel fact store."""
    entity_type = _clean_label(entity_type, "entity_type")
    name = name.strip() if name is not None else None
    if name == "":
        name = None
    _validate_confidence(confidence)
    entity = Entity(
        owner_user_id=owner_user_id,
        entity_type=entity_type,
        name=name,
        canonical_key=_normalized_key(name) if name else None,
        identity_namespace=identity_namespace,
        external_identity=external_identity,
        data=data,
        confidence=confidence,
    )
    session.add(entity)
    await session.flush()
    from app.services.retrieval import upsert_search_document

    await upsert_search_document(
        session,
        source_type="entity",
        source_id=entity.id,
        title=entity.name,
        content=f"{entity.entity_type}: {entity.name or ''}\n{entity.data or {}}",
        metadata={
            "entity_type": entity.entity_type,
            "owner_user_id": str(entity.owner_user_id) if entity.owner_user_id else None,
        },
    )
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


async def resolve_current_entity(
    session: AsyncSession,
    entity_id: uuid.UUID,
) -> Entity | None:
    """Walk a supersession chain forward to the entity that is current today."""
    seen: set[uuid.UUID] = set()
    current = await session.get(Entity, entity_id)
    if current is None:
        return None
    while current.superseded_by is not None and current.id not in seen:
        seen.add(current.id)
        next_entity = await session.get(Entity, current.superseded_by)
        if next_entity is None:
            break
        current = next_entity
    return current


async def entity_family_ids(
    session: AsyncSession,
    entity_id: uuid.UUID,
) -> set[uuid.UUID]:
    """The current entity's id plus every superseded predecessor resolving to it."""
    current = await resolve_current_entity(session, entity_id)
    if current is None:
        return {entity_id}
    ids: set[uuid.UUID] = {current.id}
    frontier: set[uuid.UUID] = {current.id}
    while frontier:
        predecessors = set(
            (
                await session.execute(
                    select(Entity.id).where(Entity.superseded_by.in_(frontier))
                )
            ).scalars().all()
        )
        new = predecessors - ids
        if not new:
            break
        ids |= new
        frontier = new
    return ids


async def get_current_entity_by_name(
    session: AsyncSession,
    entity_type: str,
    name: str,
    *,
    owner_user_id: uuid.UUID | None = None,
    identity_namespace: str | None = None,
    external_identity: str | None = None,
) -> Entity | None:
    """Fetch the current entity of a type matching this name.

    Source identity is resolved before names and follows supersession, so a
    retired external key keeps resolving to the merge survivor. Name matching
    is exact (case-insensitive), then against aliases and normalized token keys.
    """
    if external_identity is not None and identity_namespace is not None:
        identity_match = (
            await session.execute(
                select(Entity)
                .where(Entity.entity_type == entity_type)
                .where(Entity.owner_user_id == owner_user_id)
                .where(Entity.identity_namespace == identity_namespace)
                .where(Entity.external_identity == external_identity)
                .order_by(Entity.is_superseded, Entity.created_at.desc())
                .limit(1)
            )
        ).scalars().first()
        if identity_match is None:
            return None
        return await resolve_current_entity(session, identity_match.id)

    exact = (
        await session.execute(
            select(Entity)
            .where(Entity.entity_type == entity_type)
            .where(Entity.owner_user_id == owner_user_id)
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
            .where(Entity.owner_user_id == owner_user_id)
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
        statement = (
            select(Relation)
            .where(
                or_(*clauses),
                Relation.owner_user_id == root.owner_user_id,
            )
            .order_by(Relation.created_at.desc())
            .limit(remaining + 1)
        )
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
        (
            await session.execute(
                select(Entity).where(
                    Entity.id.in_(entity_ids),
                    Entity.owner_user_id == root.owner_user_id,
                )
            )
        ).scalars().all()
        if entity_ids
        else []
    )
    events = (
        (
            await session.execute(
                select(Event).where(
                    Event.id.in_(event_ids),
                    Event.owner_user_id == root.owner_user_id,
                )
            )
        ).scalars().all()
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
    owner_user_id: uuid.UUID | None = None,
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

    subject_owner = await _reference_owner(session, subject_id, subject_type)
    object_owner = await _reference_owner(session, object_id, object_type)
    if owner_user_id is not None and (
        subject_owner != owner_user_id or object_owner != owner_user_id
    ):
        raise ValueError("relation endpoints must be owned by the authenticated user")
    endpoint_owners = {
        owner for owner in (subject_owner, object_owner) if owner is not None
    }
    if len(endpoint_owners) > 1:
        raise ValueError("relation endpoints must belong to the same user")
    inferred_owner = next(iter(endpoint_owners), None)
    if owner_user_id is not None and inferred_owner not in (None, owner_user_id):
        raise ValueError("relation endpoint belongs to another user")
    owner_user_id = owner_user_id or inferred_owner

    relation = Relation(
        owner_user_id=owner_user_id,
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
    lineage = next(
        (
            (source_type, source_id)
            for source_type, source_id in (
                ("event", source_event_id),
                ("artifact_chunk", source_chunk_id),
                ("file_attachment", source_file_id),
            )
            if source_id is not None
        ),
        None,
    )
    if lineage is not None:
        source_type, source_id = lineage
        await copy_context(
            session,
            from_type=source_type,
            from_id=source_id,
            to_type="relation",
            to_id=relation.id,
        )
        await copy_policies(
            session,
            from_type=source_type,
            from_id=source_id,
            to_type="relation",
            to_id=relation.id,
        )
        if subject_type == "entity":
            await copy_context(
                session,
                from_type=source_type,
                from_id=source_id,
                to_type="entity",
                to_id=subject_id,
            )
            await copy_policies(
                session,
                from_type=source_type,
                from_id=source_id,
                to_type="entity",
                to_id=subject_id,
            )
        if object_type == "entity":
            await copy_context(
                session,
                from_type=source_type,
                from_id=source_id,
                to_type="entity",
                to_id=object_id,
            )
            await copy_policies(
                session,
                from_type=source_type,
                from_id=source_id,
                to_type="entity",
                to_id=object_id,
            )
    return relation


async def _reference_owner(
    session: AsyncSession,
    reference_id: uuid.UUID,
    reference_type: str,
) -> uuid.UUID | None:
    if reference_type == "entity":
        reference = await session.get(Entity, reference_id)
    else:
        reference = await session.get(Event, reference_id)
    return reference.owner_user_id if reference is not None else None


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
        owner_user_id=kwargs.get("owner_user_id"),
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
    *,
    decided_by_user_id: uuid.UUID | None = None,
    review_item_id: uuid.UUID | None = None,
) -> EntityMerge:
    """
    Merge merged_id into survivor_id as a single transaction.

    Marks merged_id superseded and records its names on the survivor. Historical
    relations are deliberately not rewritten: their original endpoint is part
    of the evidence trail and can be resolved through ``superseded_by``.
    """
    if survivor_id == merged_id:
        raise ValueError("survivor and merged entities must differ")

    # Stable lock ordering prevents opposing concurrent merges from deadlocking.
    locked = (
        await session.execute(
            select(Entity)
            .where(Entity.id.in_(sorted((survivor_id, merged_id), key=str)))
            .order_by(Entity.id)
            .with_for_update()
        )
    ).scalars().all()
    by_id = {entity.id: entity for entity in locked}
    survivor = by_id.get(survivor_id)
    merged = by_id.get(merged_id)
    if survivor is None:
        raise ValueError(f"survivor entity {survivor_id} does not exist")
    if merged is None:
        raise ValueError(f"merged entity {merged_id} does not exist")
    if survivor.is_superseded or merged.is_superseded:
        raise ValueError("both entities must be current")
    if survivor.entity_type != merged.entity_type:
        raise ValueError("entities must have the same entity_type")
    if survivor.owner_user_id != merged.owner_user_id:
        raise ValueError("entities must have the same owner")
    if decided_by_user_id is not None and survivor.owner_user_id != decided_by_user_id:
        raise ValueError("user does not own both entities")

    survivor_links = (
        await session.execute(
            select(ContextLink).where(
                ContextLink.target_type == "entity",
                ContextLink.target_id == survivor.id,
            )
        )
    ).scalars().all()
    merged_links = (
        await session.execute(
            select(ContextLink).where(
                ContextLink.target_type == "entity",
                ContextLink.target_id == merged.id,
            )
        )
    ).scalars().all()
    survivor_policies = (
        await session.execute(
            select(MemoryPolicy).where(
                MemoryPolicy.target_type == "entity",
                MemoryPolicy.target_id == survivor.id,
            )
        )
    ).scalars().all()
    merged_policies = (
        await session.execute(
            select(MemoryPolicy).where(
                MemoryPolicy.target_type == "entity",
                MemoryPolicy.target_id == merged.id,
            )
        )
    ).scalars().all()
    snapshot = {
        "survivor_data": dict(survivor.data or {}),
        "survivor_policy_ids": [str(policy.id) for policy in survivor_policies],
        "survivor_policies": [_policy_snapshot(policy) for policy in survivor_policies],
        "moved_context_link_ids": [],
        "deleted_context_links": [],
        "added_alias_ids": [],
    }

    merged.is_superseded = True
    merged.superseded_by = survivor_id
    session.add(merged)

    survivor_data = _merge_entity_data(survivor, merged)
    aliases = [alias for alias in survivor_data.get("aliases", []) if isinstance(alias, str)]
    for alias in [merged.name, *((merged.data or {}).get("aliases", []))]:
        if isinstance(alias, str) and alias and not any(
            _normalized_key(existing) == _normalized_key(alias) for existing in aliases
        ):
            aliases.append(alias)
    if aliases:
        survivor_data["aliases"] = aliases[-32:]
    survivor.data = survivor_data
    snapshot["applied_survivor_data"] = survivor_data
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
            alias_row = EntityAlias(entity_id=survivor.id, alias=alias, canonical_key=alias_key)
            session.add(alias_row)
            await session.flush()
            snapshot["added_alias_ids"].append(str(alias_row.id))

    # The merged entity's recall document is retired; the survivor's document is
    # refreshed so searching any former name still finds the current entity.
    merged_docs = (
        await session.execute(
            select(SearchDocument).where(
                SearchDocument.source_type == "entity",
                SearchDocument.source_id == merged_id,
                SearchDocument.is_superseded == False,
            )
        )
    ).scalars().all()
    for document in merged_docs:
        document.is_superseded = True
        session.add(document)
    from app.services.retrieval import upsert_search_document

    survivor_names = ", ".join(filter(None, [survivor.name, *aliases]))
    await upsert_search_document(
        session,
        source_type="entity",
        source_id=survivor.id,
        title=survivor.name,
        content=f"{survivor.entity_type}: {survivor_names}\n{survivor_data or {}}",
        metadata={
            "entity_type": survivor.entity_type,
            "owner_user_id": str(survivor.owner_user_id) if survivor.owner_user_id else None,
        },
    )

    # Context follows the survivor while retaining enough provenance to reverse.
    survivor_link_keys = {(link.life_area_id, link.target_type) for link in survivor_links}
    for link in merged_links:
        if (link.life_area_id, link.target_type) in survivor_link_keys:
            snapshot["deleted_context_links"].append(_context_link_snapshot(link))
            await session.delete(link)
        else:
            snapshot["moved_context_link_ids"].append(str(link.id))
            link.target_id = survivor.id
            session.add(link)

    await _reconcile_entity_policies(
        session,
        survivor,
        survivor_policies,
        merged_policies,
    )
    merge = EntityMerge(
        survivor_id=survivor.id,
        merged_id=merged.id,
        decided_by_user_id=decided_by_user_id,
        review_item_id=review_item_id,
        snapshot=snapshot,
    )
    session.add(merge)

    await session.flush()
    logger.info("Merged entity %s into %s", merged_id, survivor_id)
    return merge


async def reverse_entity_merge(
    session: AsyncSession,
    merge_id: uuid.UUID,
    *,
    decided_by_user_id: uuid.UUID | None = None,
) -> EntityMerge:
    """Reverse an identity decision without rewriting historical facts."""
    merge = (
        await session.execute(
            select(EntityMerge).where(EntityMerge.id == merge_id).with_for_update()
        )
    ).scalars().first()
    if merge is None:
        raise ValueError("entity merge does not exist")
    if merge.status != "applied":
        raise ValueError("entity merge has already been reversed")
    entities = (
        await session.execute(
            select(Entity)
            .where(Entity.id.in_(sorted((merge.survivor_id, merge.merged_id), key=str)))
            .order_by(Entity.id)
            .with_for_update()
        )
    ).scalars().all()
    by_id = {entity.id: entity for entity in entities}
    survivor = by_id.get(merge.survivor_id)
    merged = by_id.get(merge.merged_id)
    if survivor is None or merged is None:
        raise ValueError("merged entities no longer exist")
    if decided_by_user_id is not None and survivor.owner_user_id != decided_by_user_id:
        raise ValueError("user does not own this merge")
    if not merged.is_superseded or merged.superseded_by != survivor.id:
        raise ValueError("entity supersession has changed since this merge")
    if dict(survivor.data or {}) != dict(merge.snapshot.get("applied_survivor_data") or {}):
        raise ValueError("survivor metadata changed after the merge; resolve it before reversing")
    if merged.identity_namespace and merged.external_identity:
        identity_conflict = (
            await session.execute(
                select(Entity.id).where(
                    Entity.id != merged.id,
                    Entity.owner_user_id == merged.owner_user_id,
                    Entity.entity_type == merged.entity_type,
                    Entity.identity_namespace == merged.identity_namespace,
                    Entity.external_identity == merged.external_identity,
                    Entity.is_superseded == False,
                )
            )
        ).scalars().first()
        if identity_conflict is not None:
            raise ValueError("external identity was reused after the merge")

    merged.is_superseded = False
    merged.superseded_by = None
    survivor.data = dict(merge.snapshot.get("survivor_data") or {})
    session.add(merged)
    session.add(survivor)
    for alias_id in merge.snapshot.get("added_alias_ids") or []:
        alias = await session.get(EntityAlias, uuid.UUID(alias_id))
        if alias is not None and alias.entity_id == survivor.id:
            await session.delete(alias)
    for link_id in merge.snapshot.get("moved_context_link_ids") or []:
        link = await session.get(ContextLink, uuid.UUID(link_id))
        if link is not None and link.target_id == survivor.id:
            link.target_id = merged.id
            session.add(link)
    for value in merge.snapshot.get("deleted_context_links") or []:
        existing = (
            await session.execute(
                select(ContextLink.id).where(
                    ContextLink.life_area_id == uuid.UUID(value["life_area_id"]),
                    ContextLink.target_type == value["target_type"],
                    ContextLink.target_id == uuid.UUID(value["target_id"]),
                )
            )
        ).scalars().first()
        if existing is None and await session.get(ContextLink, uuid.UUID(value["id"])) is None:
            session.add(_context_link_from_snapshot(value))
    await _restore_survivor_policies(session, survivor.id, merge.snapshot)
    await _refresh_entity_search_document(session, survivor)
    await _refresh_entity_search_document(session, merged)
    merge.status = "reversed"
    merge.reversed_at = _now()
    session.add(merge)
    await session.flush()
    return merge


def _merge_entity_data(survivor: Entity, merged: Entity) -> dict[str, Any]:
    data = dict(survivor.data or {})
    merged_data = dict(merged.data or {})
    merged_from = [value for value in data.get("merged_from_ids", []) if isinstance(value, str)]
    if str(merged.id) not in merged_from:
        merged_from.append(str(merged.id))
    data["merged_from_ids"] = merged_from

    aliases = [value for value in data.get("aliases", []) if isinstance(value, str)]
    for alias in [merged.name, *merged_data.get("aliases", [])]:
        if isinstance(alias, str) and alias and not any(
            _normalized_key(existing) == _normalized_key(alias) for existing in aliases
        ):
            aliases.append(alias)
    if aliases:
        data["aliases"] = aliases[-32:]

    conflicts = dict(data.get("attribute_conflicts") or {})
    for key, value in merged_data.items():
        if key in {"aliases", "merged_from_ids", "attribute_conflicts"}:
            continue
        if key not in data:
            data[key] = value
        elif data[key] != value:
            values = list(conflicts.get(key) or [])
            candidate = {"entity_id": str(merged.id), "value": value}
            if candidate not in values:
                values.append(candidate)
            conflicts[key] = values
    if conflicts:
        data["attribute_conflicts"] = conflicts

    identities = list(data.get("external_identities") or [])
    for entity in (survivor, merged):
        if entity.identity_namespace and entity.external_identity:
            identity = {
                "namespace": entity.identity_namespace,
                "external_identity": entity.external_identity,
                "entity_id": str(entity.id),
            }
            if identity not in identities:
                identities.append(identity)
    if identities:
        data["external_identities"] = identities
    return data


def _policy_snapshot(policy: MemoryPolicy) -> dict[str, Any]:
    return {
        "id": str(policy.id),
        "user_id": str(policy.user_id),
        "visibility": policy.visibility,
        "allowed_area_ids": list(policy.allowed_area_ids or []),
        "sensitivity": policy.sensitivity,
        "reason": policy.reason,
    }


def _context_link_snapshot(link: ContextLink) -> dict[str, Any]:
    return {
        "id": str(link.id),
        "life_area_id": str(link.life_area_id),
        "target_type": link.target_type,
        "target_id": str(link.target_id),
        "role": link.role,
        "source": link.source,
        "confidence": link.confidence,
        "data": dict(link.data or {}),
    }


def _context_link_from_snapshot(value: dict[str, Any]) -> ContextLink:
    return ContextLink(
        id=uuid.UUID(value["id"]),
        life_area_id=uuid.UUID(value["life_area_id"]),
        target_type=value["target_type"],
        target_id=uuid.UUID(value["target_id"]),
        role=value["role"],
        source=value["source"],
        confidence=value["confidence"],
        data=value.get("data") or {},
    )


async def _reconcile_entity_policies(
    session: AsyncSession,
    survivor: Entity,
    survivor_policies: list[MemoryPolicy],
    merged_policies: list[MemoryPolicy],
) -> None:
    """Never make a survivor more permissive than either source identity."""
    by_user = {policy.user_id: policy for policy in survivor_policies}
    rank = {"global": 0, "selected_areas": 1, "private": 2}
    for merged_policy in merged_policies:
        policy = by_user.get(merged_policy.user_id)
        if policy is None:
            policy = MemoryPolicy(
                user_id=merged_policy.user_id,
                target_type="entity",
                target_id=survivor.id,
            )
            by_user[merged_policy.user_id] = policy
            session.add(policy)
        prior_visibility = policy.visibility
        if rank[merged_policy.visibility] > rank[prior_visibility]:
            policy.visibility = merged_policy.visibility
        if policy.visibility == "selected_areas":
            existing = set(policy.allowed_area_ids or [])
            incoming = set(merged_policy.allowed_area_ids or [])
            if prior_visibility == "global":
                existing = incoming
            elif merged_policy.visibility != "global":
                existing &= incoming
            policy.allowed_area_ids = sorted(existing)
        elif policy.visibility == "private":
            policy.allowed_area_ids = []
        policy.sensitivity = policy.sensitivity or merged_policy.sensitivity
        reasons = [reason for reason in (policy.reason, merged_policy.reason) if reason]
        policy.reason = " | ".join(dict.fromkeys(reasons)) or "Conservative entity merge policy"
        policy.updated_at = _now()
        session.add(policy)


async def _restore_survivor_policies(
    session: AsyncSession,
    survivor_id: uuid.UUID,
    snapshot: dict[str, Any],
) -> None:
    prior = {uuid.UUID(value["id"]): value for value in snapshot.get("survivor_policies") or []}
    current = (
        await session.execute(
            select(MemoryPolicy).where(
                MemoryPolicy.target_type == "entity",
                MemoryPolicy.target_id == survivor_id,
            )
        )
    ).scalars().all()
    for policy in current:
        value = prior.pop(policy.id, None)
        if value is None:
            await session.delete(policy)
            continue
        policy.visibility = value["visibility"]
        policy.allowed_area_ids = value["allowed_area_ids"]
        policy.sensitivity = value.get("sensitivity")
        policy.reason = value.get("reason")
        policy.updated_at = _now()
        session.add(policy)
    for policy_id, value in prior.items():
        session.add(
            MemoryPolicy(
                id=policy_id,
                user_id=uuid.UUID(value["user_id"]),
                target_type="entity",
                target_id=survivor_id,
                visibility=value["visibility"],
                allowed_area_ids=value["allowed_area_ids"],
                sensitivity=value.get("sensitivity"),
                reason=value.get("reason"),
            )
        )


async def _refresh_entity_search_document(session: AsyncSession, entity: Entity) -> None:
    from app.services.retrieval import upsert_search_document

    aliases = [value for value in (entity.data or {}).get("aliases", []) if isinstance(value, str)]
    names = ", ".join(filter(None, [entity.name, *aliases]))
    await upsert_search_document(
        session,
        source_type="entity",
        source_id=entity.id,
        title=entity.name,
        content=f"{entity.entity_type}: {names}\n{entity.data or {}}",
        metadata={
            "entity_type": entity.entity_type,
            "owner_user_id": str(entity.owner_user_id) if entity.owner_user_id else None,
        },
    )


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


async def aggregate_duration(
    session: AsyncSession,
    *,
    entity_id: uuid.UUID | None = None,
    entity_type: str | None = None,
    predicate: str | None = None,
    occurred_from: datetime | None = None,
    occurred_until: datetime | None = None,
    area_id: uuid.UUID | None = None,
    user_id: uuid.UUID | None = None,
    limit: int = 50_000,
) -> list[dict]:
    """Valid-time rollup of relation durations, optionally scoped to an area."""
    statement = select(Relation).where(
        Relation.is_superseded == False,
        Relation.invalidated_at.is_(None),
        Relation.occurred_from.is_not(None),
        Relation.occurred_until.is_not(None),
    )
    if entity_id:
        family = await entity_family_ids(session, entity_id)
        statement = statement.where(
            or_(Relation.subject_id.in_(family), Relation.object_id.in_(family))
        )
    if predicate:
        statement = statement.where(Relation.predicate == predicate)
    if user_id is not None:
        statement = statement.where(Relation.owner_user_id == user_id)
    if occurred_from:
        statement = statement.where(Relation.occurred_until >= occurred_from)
    if occurred_until:
        statement = statement.where(Relation.occurred_from <= occurred_until)
    relations = (await session.execute(statement.limit(limit))).scalars().all()

    requested = await resolve_current_entity(session, entity_id) if entity_id is not None else None
    entities: dict[uuid.UUID, Entity] = {}
    totals: dict[uuid.UUID, float] = {}
    for relation in relations:
        raw_target_id = (
            relation.object_id if relation.object_type == "entity" else relation.subject_id
        )
        entity = requested or await resolve_current_entity(session, raw_target_id)
        if entity is None or (entity_type and entity.entity_type != entity_type):
            continue
        if user_id is not None and entity.owner_user_id != user_id:
            continue
        if area_id is not None and user_id is not None:
            from app.services.context import target_visible

            if not await target_visible(
                session,
                user_id=user_id,
                target_type="entity",
                target_id=entity.id,
                area_id=area_id,
            ):
                continue
        target_id = entity.id
        entities[target_id] = entity
        start = max(relation.occurred_from, occurred_from) if occurred_from else relation.occurred_from
        end = min(relation.occurred_until, occurred_until) if occurred_until else relation.occurred_until
        if start is not None and end is not None and end > start:
            totals[target_id] = totals.get(target_id, 0.0) + (end - start).total_seconds()
    return [
        {
            "entity_id": str(entity_id_),
            "entity_type": entities[entity_id_].entity_type,
            "name": entities[entity_id_].name,
            "seconds": seconds,
            "hours": seconds / 3600,
        }
        for entity_id_, seconds in sorted(totals.items(), key=lambda item: item[1], reverse=True)
    ]
