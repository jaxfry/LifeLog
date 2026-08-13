import uuid
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from urllib.parse import urlparse

from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import col, select, update

from app.core.logger import get_logger
from app.loader.contracts import ExtensionManifest
from app.models.config import Extension
from app.models.ingest import Event, RawLog
from app.models.kernel import Entity, Relation
from app.services.kernel import (
    add_entity_alias,
    create_entity,
    get_current_entity_by_name,
    link_event,
)

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
    Run the registered extractor for an event and write kernel facts.

    Idempotent: re-running for the same event creates no duplicates
    (per-relation dedupe via explicit lineage fields). Returns (entities_created,
    relations_created).
    """
    log = await session.get(RawLog, event.source_log_id)
    if log is None:
        logger.warning("RawLog %s missing for event %s; skipping extraction", event.source_log_id, event.id)
        return (0, 0)

    extractor = EXTRACTORS.get(event.event_type)
    named_drafts: list[tuple[str, DraftRelation]] = []
    if extractor is not None:
        named_drafts.extend((extractor.__name__, draft) for draft in extractor(event))
    extension = await session.get(Extension, log.extension_id)
    if extension is not None:
        manifest = ExtensionManifest.model_validate(extension.config)
        for index, mapping in enumerate(manifest.fact_mappings):
            if mapping.event_type != event.event_type:
                continue
            value = _read_path(event.data or {}, mapping.value_path)
            if value is None:
                continue
            name = str(value).strip()
            if mapping.transform == "lowercase":
                name = name.casefold()
            elif mapping.transform == "domain":
                name = _domain_from_url(name) or ""
            occurred_from, occurred_until = _event_window(event)
            named_drafts.append(
                (
                    f"manifest:{log.extension_id}:{index}",
                    DraftRelation(
                        predicate=mapping.predicate,
                        object_entity_type=mapping.object_entity_type,
                        object_name=name,
                        occurred_from=occurred_from,
                        occurred_until=occurred_until,
                        confidence=mapping.confidence,
                    ),
                )
            )

    if not named_drafts:
        event.memory_extraction_version = EXTRACTION_VERSION
        session.add(event)
        await session.flush()
        return (0, 0)

    await session.execute(
        update(Relation)
        .where(Relation.source_event_id == event.id)
        .where(Relation.extraction_version.is_not(None))
        .where(Relation.extraction_version != EXTRACTION_VERSION)
        .where(Relation.is_superseded == False)
        .values(is_superseded=True, invalidated_at=datetime.now(UTC).replace(tzinfo=None))
    )

    entities_created = 0
    relations_created = 0
    for extractor_name, draft in named_drafts:
        if not draft.object_name:
            continue
        entity, created = await _get_or_create_entity(
            session,
            entity_type=draft.object_entity_type,
            name=draft.object_name,
            confidence=draft.confidence,
        )
        if created:
            entities_created += 1
        if await _relation_exists(
            session,
            event.id,
            draft.predicate,
            entity.id,
            extractor_name,
        ):
            continue

        await link_event(
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
        relations_created += 1

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


async def _get_or_create_entity(
    session: AsyncSession,
    entity_type: str,
    name: str,
    confidence: float,
) -> tuple[Entity, bool]:
    """Find an existing entity by (type, name) or create one.

    Variant spellings that resolve to an existing entity are recorded as
    aliases on it so future mentions match deterministically.
    """
    existing = await get_current_entity_by_name(session, entity_type, name)
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
    )
    return entity, True


async def _relation_exists(
    session: AsyncSession,
    event_id: uuid.UUID,
    predicate: str,
    object_id: uuid.UUID,
    extractor: str,
) -> bool:
    """Check the explicit lineage key used by the database uniqueness rule."""
    statement = select(Relation.id).where(
        Relation.source_event_id == event_id,
        Relation.subject_id == event_id,
        Relation.predicate == predicate,
        Relation.object_id == object_id,
        Relation.extractor == extractor,
        Relation.extraction_version == EXTRACTION_VERSION,
    )
    return (await session.execute(statement)).scalars().first() is not None

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
