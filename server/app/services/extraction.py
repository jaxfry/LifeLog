import re
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from urllib.parse import urlparse

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import col, select, update

from app.core.logger import get_logger
from app.loader.contracts import ExtensionManifest
from app.models.auth import Device
from app.models.claims import ClaimEvidence, FactEvidence, MemoryClaim
from app.models.config import Extension
from app.models.ingest import Event, RawLog
from app.models.kernel import Entity, Measurement, Relation
from app.models.sources import SourceConnection
from app.services.derivations import fingerprint
from app.services.kernel import (
    add_entity_alias,
    create_entity,
    create_relation,
    get_current_entity_by_name,
    link_event,
)
from app.services.measurements import create_measurement, measurement_exists
from app.services.ontology import ontology_registry

logger = get_logger(__name__)

EXTRACTION_VERSION = 1


@dataclass
class DraftRelation:
    """A kernel relation proposed by an extractor, not yet persisted."""

    predicate: str
    object_entity_type: str
    object_name: str
    occurred_from: datetime | None = None
    occurred_until: datetime | None = None
    confidence: float = 1.0


Extractor = Callable[[Event], list[DraftRelation]]

EXTRACTORS: dict[str, Extractor] = {}


def register_extractor(event_type: str) -> Callable[[Extractor], Extractor]:
    """Decorator: register an extractor function for an event type."""

    def _decorator(fn: Extractor) -> Extractor:
        EXTRACTORS[event_type] = fn
        return fn

    return _decorator


@register_extractor("app_usage")
def _extract_app_usage(event: Event) -> list[DraftRelation]:
    """Facts: event --used_app--> application entity, valid over the event window."""
    app = (event.data or {}).get("app")
    if not app:
        return []
    occurred_from, occurred_until = _event_window(event)
    return [
        DraftRelation(
            predicate="used_app",
            object_entity_type="application",
            object_name=str(app),
            occurred_from=occurred_from,
            occurred_until=occurred_until,
        )
    ]


@register_extractor("browsing")
def _extract_browsing(event: Event) -> list[DraftRelation]:
    """Facts: event --browsed--> domain entity (from URL host)."""
    url = (event.data or {}).get("url")
    if not url:
        return []
    host = _domain_from_url(str(url))
    if not host:
        return []
    occurred_from, occurred_until = _event_window(event)
    return [
        DraftRelation(
            predicate="browsed",
            object_entity_type="domain",
            object_name=host,
            occurred_from=occurred_from,
            occurred_until=occurred_until,
        )
    ]


def _event_window(event: Event) -> tuple[datetime | None, datetime | None]:
    """Map an event's own timing to the fact's valid-time window."""
    occurred_from = event.start_time
    occurred_until = event.end_time
    duration = (event.data or {}).get("duration")
    if duration:
        try:
            occurred_until = occurred_from + timedelta(seconds=float(duration))
        except (TypeError, ValueError):
            occurred_until = None
    return occurred_from, occurred_until


async def extract_event_facts(session: AsyncSession, event: Event) -> tuple[int, int]:
    """
    Run the registered extractor and manifest-declared mappings for an event.

    Idempotent: re-running for the same event creates no duplicates
    (per-relation dedupe via explicit lineage fields). Returns (entities_created,
    relations_created).
    """
    log = await session.get(RawLog, event.source_log_id)
    if log is None:
        logger.warning("RawLog %s missing for event %s; skipping extraction", event.source_log_id, event.id)
        return (0, 0)
    owner_user_id = await _suggestion_user(session, log)
    if owner_user_id is None:
        logger.warning(
            "RawLog %s has no unambiguous owner; preserving event but skipping memory projection",
            log.id,
        )
        event.memory_extraction_version = EXTRACTION_VERSION
        session.add(event)
        await session.flush()
        return (0, 0)
    identity_namespace = (
        f"source-connection:{log.source_connection_id}"
        if log.source_connection_id is not None
        else f"extension:{log.extension_id}"
    )

    entities_created = 0
    relations_created = 0
    created_entity_ids: list[uuid.UUID] = []
    entity_refs: dict[str, Entity] = {}
    named_drafts: list[tuple[str, DraftRelation]] = []
    relation_plans: list[dict] = []
    measurement_plans: list[dict] = []

    extractor = EXTRACTORS.get(event.event_type)
    if extractor is not None:
        named_drafts.extend((extractor.__name__, draft) for draft in extractor(event))

    extension = await session.get(Extension, log.extension_id)
    if extension is not None:
        manifest = ExtensionManifest.model_validate(extension.config)
        manifest_ontology = ontology_registry.with_manifest(manifest)
        occurred_from, occurred_until = _event_window(event)
        for index, mapping in enumerate(manifest.fact_mappings):
            if mapping.event_type != event.event_type:
                continue
            predicate, predicate_known = manifest_ontology.normalize_predicate(
                mapping.predicate
            )
            entity_type, entity_type_known = manifest_ontology.normalize_entity_type(
                mapping.object_entity_type
            )
            if not predicate_known or not entity_type_known:
                logger.warning(
                    "Skipping undeclared ontology mapping %s/%s in %s",
                    mapping.predicate,
                    mapping.object_entity_type,
                    log.extension_id,
                )
                continue
            value = _read_path(event.data or {}, mapping.value_path)
            if value is None:
                continue
            name = str(value).strip()
            if mapping.transform == "lowercase":
                name = name.casefold()
            elif mapping.transform == "domain":
                name = _domain_from_url(name) or ""
            named_drafts.append(
                (
                    f"manifest:{log.extension_id}:{index}",
                    DraftRelation(
                        predicate=predicate,
                        object_entity_type=entity_type,
                        object_name=name,
                        occurred_from=occurred_from,
                        occurred_until=occurred_until,
                        confidence=mapping.confidence,
                    ),
                )
            )
        for _index, mapping in enumerate(manifest.entity_mappings):
            if mapping.event_type != event.event_type:
                continue
            entity_type, entity_type_known = manifest_ontology.normalize_entity_type(
                mapping.entity_type
            )
            if not entity_type_known:
                logger.warning(
                    "Skipping undeclared entity type %s in %s",
                    mapping.entity_type,
                    log.extension_id,
                )
                continue
            name_value = _read_path(event.data or {}, mapping.name_path)
            if name_value is None:
                continue
            name = str(name_value).strip()
            if not name:
                continue
            identity = (
                _read_path(event.data or {}, mapping.identity_path)
                if mapping.identity_path
                else None
            )
            entity, created = await _get_or_create_entity(
                session,
                entity_type,
                name,
                mapping.confidence,
                owner_user_id=owner_user_id,
                identity_namespace=identity_namespace if identity is not None else None,
                external_identity=str(identity).strip() if identity is not None else None,
            )
            if created:
                entities_created += 1
                created_entity_ids.append(entity.id)
            metadata = {
                key: _read_path(event.data or {}, path)
                for key, path in mapping.metadata_paths.items()
            }
            await _apply_entity_identity(session, entity, identity, metadata)
            aliases_value = (
                _read_path(event.data or {}, mapping.aliases_path)
                if mapping.aliases_path
                else None
            )
            if isinstance(aliases_value, list):
                for alias in aliases_value:
                    if isinstance(alias, str) and alias.strip():
                        await add_entity_alias(session, entity.id, alias.strip())
            entity_refs[mapping.entity_ref] = entity
        for index, mapping in enumerate(manifest.relation_mappings):
            if mapping.event_type != event.event_type:
                continue
            predicate, predicate_known = manifest_ontology.normalize_predicate(
                mapping.predicate
            )
            if not predicate_known or not manifest_ontology.validate_relation(
                predicate,
                subject_kind="event" if mapping.subject == "record" else "entity",
                object_kind="event" if mapping.object == "record" else "entity",
            ):
                logger.warning(
                    "Skipping undeclared or incompatible predicate %s in %s",
                    mapping.predicate,
                    log.extension_id,
                )
                continue
            subject_id, subject_type = event.id, "event"
            if mapping.subject == "entity":
                entity = entity_refs.get(mapping.subject_entity_ref or "")
                if entity is None:
                    continue
                subject_id, subject_type = entity.id, "entity"
            object_id, object_type = event.id, "event"
            if mapping.object == "entity":
                entity = entity_refs.get(mapping.object_entity_ref or "")
                if entity is None:
                    continue
                object_id, object_type = entity.id, "entity"
            if subject_id == object_id and subject_type == object_type:
                continue
            relation_plans.append(
                {
                    "extractor": f"manifest:{log.extension_id}:relation:{index}",
                    "subject_id": subject_id,
                    "subject_type": subject_type,
                    "predicate": predicate,
                    "object_id": object_id,
                    "object_type": object_type,
                    "occurred_from": occurred_from,
                    "occurred_until": occurred_until,
                    "confidence": mapping.confidence,
                }
            )
        for index, mapping in enumerate(manifest.measurement_mappings):
            if mapping.event_type != event.event_type:
                continue
            entity = entity_refs.get(mapping.entity_ref)
            if entity is None:
                continue
            value = _read_path(event.data or {}, mapping.value_path)
            if value is None:
                continue
            numeric: float | None = None
            value_text: str | None = None
            if mapping.value_type == "text":
                value_text = str(value)
            else:
                try:
                    numeric = float(value)
                except (TypeError, ValueError):
                    continue
            unit_value = (
                _read_path(event.data or {}, mapping.unit_path)
                if mapping.unit_path
                else None
            )
            occurred_at = occurred_from
            if mapping.occurred_at_path:
                parsed = _parse_iso_datetime(
                    _read_path(event.data or {}, mapping.occurred_at_path)
                )
                if parsed is not None:
                    occurred_at = parsed
            measurement_plans.append(
                {
                    "extractor": f"manifest:{log.extension_id}:measurement:{index}",
                    "entity_id": entity.id,
                    "metric": mapping.metric,
                    "value": numeric,
                    "value_text": value_text,
                    "unit": str(unit_value) if unit_value is not None else None,
                    "occurred_at": occurred_at,
                    "confidence": mapping.confidence,
                }
            )

    if not named_drafts and not relation_plans and not measurement_plans:
        event.memory_extraction_version = EXTRACTION_VERSION
        session.add(event)
        await session.flush()
        await _suggest_merges_for_created(session, log, created_entity_ids)
        return (entities_created, 0)

    now = datetime.now(UTC).replace(tzinfo=None)
    await session.execute(
        update(Relation)
        .where(Relation.source_event_id == event.id)
        .where(Relation.extraction_version.is_not(None))
        .where(Relation.extraction_version != EXTRACTION_VERSION)
        .where(Relation.is_superseded == False)
        .values(is_superseded=True, invalidated_at=now)
    )
    await session.execute(
        update(Measurement)
        .where(Measurement.source_event_id == event.id)
        .where(Measurement.extraction_version.is_not(None))
        .where(Measurement.extraction_version != EXTRACTION_VERSION)
        .where(Measurement.is_superseded == False)
        .values(is_superseded=True)
    )

    for extractor_name, draft in named_drafts:
        if not draft.object_name:
            continue
        entity, created = await _get_or_create_entity(
            session,
            entity_type=draft.object_entity_type,
            name=draft.object_name,
            confidence=draft.confidence,
            owner_user_id=owner_user_id,
        )
        if created:
            entities_created += 1
            created_entity_ids.append(entity.id)
        existing_relation_id = await _relation_exists(
            session,
            event.id,
            draft.predicate,
            entity.id,
            extractor_name,
        )
        if existing_relation_id is not None:
            await _record_projection_claim(
                session,
                owner_user_id=owner_user_id,
                event=event,
                predicate=draft.predicate,
                object_entity_id=entity.id,
                occurred_from=draft.occurred_from,
                occurred_until=draft.occurred_until,
                confidence=draft.confidence,
                extractor=extractor_name,
                target_type="relation",
                target_id=existing_relation_id,
            )
            continue

        relation = await link_event(
            session,
            event_id=event.id,
            predicate=draft.predicate,
            object_id=entity.id,
            object_type="entity",
            occurred_from=draft.occurred_from,
            occurred_until=draft.occurred_until,
            confidence=draft.confidence,
            source_event_id=event.id,
            extractor=extractor_name,
            extraction_version=EXTRACTION_VERSION,
            data={"extension_id": log.extension_id, "source_log_id": str(log.id)},
        )
        await _record_projection_claim(
            session,
            owner_user_id=owner_user_id,
            event=event,
            predicate=draft.predicate,
            object_entity_id=entity.id,
            occurred_from=draft.occurred_from,
            occurred_until=draft.occurred_until,
            confidence=draft.confidence,
            extractor=extractor_name,
            target_type="relation",
            target_id=relation.id,
        )
        relations_created += 1

    for plan in relation_plans:
        existing_relation_id = await _entity_relation_exists(session, event.id, plan)
        if existing_relation_id is not None:
            await _record_projection_claim(
                session,
                owner_user_id=owner_user_id,
                event=event,
                predicate=plan["predicate"],
                subject_entity_id=(
                    plan["subject_id"] if plan["subject_type"] == "entity" else None
                ),
                object_entity_id=(
                    plan["object_id"] if plan["object_type"] == "entity" else None
                ),
                occurred_from=plan["occurred_from"],
                occurred_until=plan["occurred_until"],
                confidence=plan["confidence"],
                extractor=plan["extractor"],
                target_type="relation",
                target_id=existing_relation_id,
            )
            continue
        relation = await create_relation(
            session,
            subject_id=plan["subject_id"],
            subject_type=plan["subject_type"],
            predicate=plan["predicate"],
            object_id=plan["object_id"],
            object_type=plan["object_type"],
            occurred_from=plan["occurred_from"],
            occurred_until=plan["occurred_until"],
            confidence=plan["confidence"],
            source_event_id=event.id,
            extractor=plan["extractor"],
            extraction_version=EXTRACTION_VERSION,
            data={"extension_id": log.extension_id, "source_log_id": str(log.id)},
        )
        await _record_projection_claim(
            session,
            owner_user_id=owner_user_id,
            event=event,
            predicate=plan["predicate"],
            subject_entity_id=(
                plan["subject_id"] if plan["subject_type"] == "entity" else None
            ),
            object_entity_id=(
                plan["object_id"] if plan["object_type"] == "entity" else None
            ),
            occurred_from=plan["occurred_from"],
            occurred_until=plan["occurred_until"],
            confidence=plan["confidence"],
            extractor=plan["extractor"],
            target_type="relation",
            target_id=relation.id,
        )
        relations_created += 1

    for plan in measurement_plans:
        existing_measurement_id = await measurement_exists(
            session,
            source_event_id=event.id,
            source_file_id=None,
            entity_id=plan["entity_id"],
            metric=plan["metric"],
            extractor=plan["extractor"],
            extraction_version=EXTRACTION_VERSION,
        )
        if existing_measurement_id is not None:
            await _record_projection_claim(
                session,
                owner_user_id=owner_user_id,
                event=event,
                predicate=plan["metric"],
                subject_entity_id=plan["entity_id"],
                value={
                    "value": plan["value"],
                    "value_text": plan["value_text"],
                    "unit": plan["unit"],
                },
                occurred_from=plan["occurred_at"],
                occurred_until=plan["occurred_at"],
                confidence=plan["confidence"],
                extractor=plan["extractor"],
                target_type="measurement",
                target_id=existing_measurement_id,
                kind="measurement",
            )
            continue
        measurement = await create_measurement(
            session,
            entity_id=plan["entity_id"],
            metric=plan["metric"],
            value=plan["value"],
            value_text=plan["value_text"],
            unit=plan["unit"],
            occurred_at=plan["occurred_at"],
            confidence=plan["confidence"],
            source_event_id=event.id,
            extractor=plan["extractor"],
            extraction_version=EXTRACTION_VERSION,
        )
        await _record_projection_claim(
            session,
            owner_user_id=owner_user_id,
            event=event,
            predicate=plan["metric"],
            subject_entity_id=plan["entity_id"],
            value={
                "value": plan["value"],
                "value_text": plan["value_text"],
                "unit": plan["unit"],
            },
            occurred_from=plan["occurred_at"],
            occurred_until=plan["occurred_at"],
            confidence=plan["confidence"],
            extractor=plan["extractor"],
            target_type="measurement",
            target_id=measurement.id,
            kind="measurement",
        )

    if entities_created or relations_created:
        logger.info(
            "Extracted %d entities, %d relations from event %s (%s)",
            entities_created,
            relations_created,
            event.id,
            event.event_type,
        )
    event.memory_extraction_version = EXTRACTION_VERSION
    session.add(event)
    await session.flush()
    await _suggest_merges_for_created(session, log, created_entity_ids)
    return (entities_created, relations_created)


async def backfill_event_facts(
    session: AsyncSession,
    limit: int = 500,
) -> dict[str, int]:
    """Build the current memory projection for eligible Events lacking it."""
    statement = (
        select(Event)
        .where(Event.is_superseded == False)
        .where(
            (Event.memory_extraction_version.is_(None))
            | (Event.memory_extraction_version != EXTRACTION_VERSION)
        )
        .order_by(col(Event.created_at).asc())
        .limit(limit)
    )
    events = (await session.execute(statement)).scalars().all()
    entities_created = 0
    relations_created = 0
    for event in events:
        entity_count, relation_count = await extract_event_facts(session, event)
        entities_created += entity_count
        relations_created += relation_count
    await session.flush()
    return {
        "events_processed": len(events),
        "entities_created": entities_created,
        "relations_created": relations_created,
    }


async def _suggestion_user(session: AsyncSession, log: RawLog) -> uuid.UUID | None:
    """Resolve only explicit source/device ownership; never guess an active user."""
    if log.owner_user_id is not None:
        return log.owner_user_id
    if log.source_connection_id is not None:
        connection = await session.get(SourceConnection, log.source_connection_id)
        if connection is not None:
            return connection.user_id
    device = await session.get(Device, log.device_id)
    if device is not None and device.user_id is not None:
        return device.user_id
    return None


async def _record_projection_claim(
    session: AsyncSession,
    *,
    owner_user_id: uuid.UUID,
    event: Event,
    predicate: str,
    extractor: str,
    target_type: str,
    target_id: uuid.UUID,
    subject_entity_id: uuid.UUID | None = None,
    object_entity_id: uuid.UUID | None = None,
    value: dict | None = None,
    occurred_from: datetime | None = None,
    occurred_until: datetime | None = None,
    confidence: float = 1.0,
    kind: str = "relation",
) -> MemoryClaim:
    """Represent authoritative deterministic projections in the same claim ledger."""
    derivation_key = fingerprint(
        {
            "source_event_id": event.id,
            "predicate": predicate,
            "subject_entity_id": subject_entity_id,
            "object_entity_id": object_entity_id,
            "value": value,
            "extractor": extractor,
            "extraction_version": EXTRACTION_VERSION,
        }
    )
    claim = (
        await session.execute(
            select(MemoryClaim).where(
                MemoryClaim.owner_user_id == owner_user_id,
                MemoryClaim.derivation_key == derivation_key,
            )
        )
    ).scalar_one_or_none()
    if claim is None:
        claim = MemoryClaim(
            owner_user_id=owner_user_id,
            kind=kind,
            subject_entity_id=subject_entity_id,
            predicate=predicate,
            object_entity_id=object_entity_id,
            value=value,
            valid_from=occurred_from,
            valid_until=occurred_until,
            time_precision="event",
            extraction_confidence=confidence,
            quality_score=1.0,
            reconciliation_status="accepted",
            extractor=extractor,
            extraction_version=EXTRACTION_VERSION,
            ontology_version="1",
            derivation_key=derivation_key,
            canonical_target_type=target_type,
            canonical_target_id=target_id,
            data={
                "deterministic": True,
                "source_event_id": str(event.id),
                "event_subject": subject_entity_id is None,
            },
        )
        session.add(claim)
        await session.flush()
        session.add(ClaimEvidence(claim_id=claim.id, event_id=event.id, role="direct"))
        session.add(
            FactEvidence(
                target_type=target_type,
                target_id=target_id,
                claim_id=claim.id,
            )
        )
        await session.flush()
        from app.services.claims import index_claim

        await index_claim(session, claim)
    return claim


async def _suggest_merges_for_created(
    session: AsyncSession,
    log: RawLog,
    created_entity_ids: list[uuid.UUID],
) -> None:
    """Real-time lookalike suggestions for freshly created entities.

    Never blocks ingestion: a suggestion failure is logged and ignored.
    """
    if not created_entity_ids:
        return
    user_id = await _suggestion_user(session, log)
    if user_id is None:
        return
    try:
        from app.services.inbox import suggest_entity_merges_for

        for entity_id in created_entity_ids:
            await suggest_entity_merges_for(session, user_id, entity_id, limit=3)
    except Exception:
        logger.info("Entity merge suggestion skipped for log %s", log.id)


async def _get_or_create_entity(
    session: AsyncSession,
    entity_type: str,
    name: str,
    confidence: float,
    owner_user_id: uuid.UUID | None,
    identity_namespace: str | None = None,
    external_identity: str | None = None,
) -> tuple[Entity, bool]:
    """Find an existing entity by (type, name) or create one.

    Variant spellings that resolve to an existing entity are recorded as
    aliases on it so future mentions match deterministically.
    """
    # Concurrent normalization jobs frequently discover the same identity. A
    # transaction-scoped advisory lock prevents check-then-insert races on PG;
    # the unique partial index remains the final invariant.
    if session.bind is not None and session.bind.dialect.name == "postgresql":
        # Lock once per owner's memory graph transaction. Per-entity locks can
        # deadlock when two batches discover the same set in different orders.
        lock_key = f"entity-owner:{owner_user_id}"
        await session.execute(
            text("SELECT pg_advisory_xact_lock(hashtextextended(:key, 0))"),
            {"key": lock_key},
        )
    existing = await get_current_entity_by_name(
        session,
        entity_type,
        name,
        owner_user_id=owner_user_id,
        identity_namespace=identity_namespace,
        external_identity=external_identity,
    )
    if existing is not None:
        if existing.name and existing.name.casefold() != name.casefold():
            await add_entity_alias(session, existing.id, name)
        return existing, False

    entity = await create_entity(
        session,
        entity_type=entity_type,
        name=name,
        confidence=confidence,
        data=None,
        owner_user_id=owner_user_id,
        identity_namespace=identity_namespace,
        external_identity=external_identity,
    )
    return entity, True


async def persist_inferred_concepts(
    session: AsyncSession,
    concepts: list[dict],
    evidence_map: dict[str, object],
    events: list[Event],
) -> int:
    """Persist AI-proposed concepts only when they cite durable event evidence."""
    event_by_id = {event.id: event for event in events}
    created_relations = 0
    for concept in concepts:
        name = str(concept.get("name") or "").strip()
        raw_type = re.sub(r"[^a-z]+", "_", str(concept.get("type") or "topic").casefold()).strip("_")
        type_aliases = {
            "academic_task": "assignment",
            "task": "assignment",
            "club": "organization",
            "extracurricular": "organization",
            "literary_work": "media",
            "text": "media",
            "game": "media",
            "subject": "topic",
            "physics_topic": "topic",
            "programming": "topic",
            "lms": "application",
            "platform": "application",
            "tool": "application",
        }
        entity_type = type_aliases.get(raw_type, raw_type)
        allowed_types = {
            "course", "assignment", "project", "person", "organization",
            "topic", "place", "media", "activity", "application", "resource",
        }
        refs = [str(ref) for ref in concept.get("evidence_refs", [])]
        evidence_events = [
            event_by_id[event_id]
            for ref in refs
            if (event_id := evidence_map.get(ref)) in event_by_id
        ]
        if not name or not evidence_events or entity_type not in allowed_types:
            continue
        first_log = await session.get(RawLog, evidence_events[0].source_log_id)
        if first_log is None:
            continue
        owner_user_id = await _suggestion_user(session, first_log)
        confidence = min(1.0, max(0.0, float(concept.get("confidence", 0.75))))
        entity, _created = await _get_or_create_entity(
            session,
            entity_type=entity_type,
            name=name,
            confidence=confidence,
            owner_user_id=owner_user_id,
        )
        for event in evidence_events:
            extractor = "timeline:concepts:v1"
            if await _relation_exists(session, event.id, "concerns", entity.id, extractor):
                continue
            await link_event(
                session,
                event_id=event.id,
                predicate="concerns",
                object_id=entity.id,
                object_type="entity",
                occurred_from=event.start_time,
                occurred_until=event.end_time,
                confidence=confidence,
                source_event_id=event.id,
                extractor=extractor,
                extraction_version=EXTRACTION_VERSION,
                data={"inferred_by": "timeline_generation", "evidence_ref": True},
            )
            created_relations += 1
    return created_relations


async def _relation_exists(
    session: AsyncSession,
    event_id: uuid.UUID,
    predicate: str,
    object_id: uuid.UUID,
    extractor: str,
) -> uuid.UUID | None:
    """Check the explicit lineage key used by the database uniqueness rule."""
    statement = select(Relation.id).where(
        Relation.source_event_id == event_id,
        Relation.subject_id == event_id,
        Relation.predicate == predicate,
        Relation.object_id == object_id,
        Relation.extractor == extractor,
        Relation.extraction_version == EXTRACTION_VERSION,
    )
    return (await session.execute(statement)).scalars().first()

async def _entity_relation_exists(
    session: AsyncSession,
    event_id: uuid.UUID,
    plan: dict,
) -> uuid.UUID | None:
    """Check the lineage key for a manifest-declared entity/record relation."""
    statement = select(Relation.id).where(
        Relation.source_event_id == event_id,
        Relation.subject_id == plan["subject_id"],
        Relation.subject_type == plan["subject_type"],
        Relation.predicate == plan["predicate"],
        Relation.object_id == plan["object_id"],
        Relation.object_type == plan["object_type"],
        Relation.extractor == plan["extractor"],
        Relation.extraction_version == EXTRACTION_VERSION,
    )
    return (await session.execute(statement)).scalars().first()


async def _apply_entity_identity(
    session: AsyncSession,
    entity: Entity,
    identity: object | None,
    metadata: dict[str, object],
) -> bool:
    """Persist external identity and mapped metadata on an entity when changed."""
    data = dict(entity.data or {})
    changed = False
    if identity is not None:
        identity_str = str(identity).strip()
        if identity_str and data.get("external_identity") != identity_str:
            data["external_identity"] = identity_str
            changed = True
    existing_metadata = data.get("metadata") or {}
    for key, value in metadata.items():
        if value is None:
            continue
        if existing_metadata.get(key) != value:
            existing_metadata = {**existing_metadata, key: value}
            changed = True
    if changed:
        data["metadata"] = existing_metadata
        entity.data = data
        session.add(entity)
        await session.flush()
    return changed


def _parse_iso_datetime(value: object) -> datetime | None:
    if value is None:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is not None:
        return parsed.astimezone(UTC).replace(tzinfo=None)
    return parsed


def _domain_from_url(url: str) -> str | None:
    """Extract a normalized host (lowercase, no scheme/path/userinfo/port/www)."""
    try:
        parsed = urlparse(url)
        host = parsed.netloc or parsed.path.split("/", 1)[0]
    except ValueError:
        return None
    if not host:
        return None
    host = host.split("@")[-1].split(":")[0].lower()
    if host.startswith("www."):
        host = host[4:]
    return host or None


def _read_path(value: dict, path: str) -> object | None:
    current: object = value
    for part in path.split("."):
        if not isinstance(current, dict) or part not in current:
            return None
        current = current[part]
    return current
