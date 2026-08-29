import re
import uuid
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import and_, func, or_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import col, select

from app.core.config import settings
from app.core.logger import get_logger
from app.models.ingest import Event
from app.models.kernel import Entity, EntityAlias, Relation
from app.models.processing import DailySummary, TimelineEntry
from app.models.retrieval import SearchDocument
from app.services.ai import embedding_with_fallback, embeddings_with_fallback
from app.services.context import target_visible
from app.services.model_router import ModelRole, model_router

logger = get_logger(__name__)


@dataclass
class RecallHit:
    source_type: str
    source_id: uuid.UUID
    title: str | None
    content: str
    occurred_at: datetime | None
    score: float
    reasons: list[str]
    metadata: dict


async def upsert_search_document(
    session: AsyncSession,
    *,
    source_type: str,
    source_id: uuid.UUID,
    content: str,
    title: str | None = None,
    occurred_at: datetime | None = None,
    logical_date: str | None = None,
    version: int = 1,
    metadata: dict | None = None,
    generate_embedding: bool = False,
) -> SearchDocument:
    """Write the rebuildable retrieval projection without owning source truth."""
    existing = (
        await session.execute(
            select(SearchDocument).where(
                SearchDocument.source_type == source_type,
                SearchDocument.source_id == source_id,
                SearchDocument.version == version,
            )
        )
    ).scalars().first()
    document = existing or SearchDocument(
        source_type=source_type,
        source_id=source_id,
        version=version,
        content=content,
    )
    content_changed = existing is not None and document.content != content
    document.title = title
    metadata = metadata or {}
    raw_owner = metadata.get("owner_user_id")
    if raw_owner is not None:
        document.owner_user_id = uuid.UUID(str(raw_owner))
    document.content = content
    document.occurred_at = occurred_at
    document.logical_date = logical_date
    document.metadata_ = {**(document.metadata_ or {}), **metadata}
    document.is_superseded = False
    if content_changed:
        document.embedding = None
        document.embedding_model = None
    if generate_embedding and document.embedding is None:
        try:
            document.embedding = await embedding_with_fallback(content)
            deployment = model_router.require(ModelRole.EMBEDDING)[0]
            document.embedding_model = (
                f"{deployment.provider}:{deployment.model}:truncate-{settings.EMBEDDING_DIMENSIONS}"
            )
        except Exception as exc:
            # Semantic recall is optional infrastructure. Lexical indexing must survive.
            logger.info("Embedding unavailable for %s/%s: %s", source_type, source_id, exc)
    session.add(document)
    await session.flush()
    return document


async def embed_pending_documents(session: AsyncSession, *, limit: int = 100) -> int:
    """Bounded semantic enrichment, intentionally outside source transactions."""
    if not model_router.deployments_for(ModelRole.EMBEDDING):
        return 0
    documents = (
        await session.execute(
            select(SearchDocument)
            .where(
                SearchDocument.is_superseded == False,
                SearchDocument.embedding.is_(None),
                col(SearchDocument.source_type).in_(
                    (
                        "daily_summary",
                        "timeline",
                        "capture",
                        "entity",
                        "artifact_chunk",
                        "evidence_span",
                        "memory_claim",
                    )
                ),
            )
            .order_by(
                (SearchDocument.source_type == "daily_summary").desc(),
                (SearchDocument.source_type == "timeline").desc(),
                col(SearchDocument.created_at).asc(),
            )
            .limit(limit)
        )
    ).scalars().all()
    if not documents:
        return 0
    try:
        embeddings = await embeddings_with_fallback([document.content for document in documents])
    except Exception as exc:
        logger.warning("Embedding batch failed: %s", exc)
        return 0
    completed = 0
    for document, embedding in zip(documents, embeddings, strict=True):
        document.embedding = embedding
        deployment = model_router.require(ModelRole.EMBEDDING)[0]
        document.embedding_model = (
            f"{deployment.provider}:{deployment.model}:truncate-{settings.EMBEDDING_DIMENSIONS}"
        )
        session.add(document)
        completed += 1
    await session.flush()
    return completed


async def retrieve(
    session: AsyncSession,
    query: str,
    *,
    limit: int = 12,
    source_types: set[str] | None = None,
    user_id: uuid.UUID | None = None,
    area_id: uuid.UUID | None = None,
    require_owner_metadata: bool = False,
    occurred_from: datetime | None = None,
    occurred_until: datetime | None = None,
    logical_from: str | None = None,
    logical_until: str | None = None,
) -> list[RecallHit]:
    """Hybrid lexical/semantic retrieval with reciprocal-rank fusion."""
    candidate_multiplier = 12
    lexical = await _lexical_documents(
        session,
        query,
        limit * candidate_multiplier,
        source_types,
        occurred_from=occurred_from,
        occurred_until=occurred_until,
        logical_from=logical_from,
        logical_until=logical_until,
        user_id=user_id,
    )
    lexical = await _filter_scoped_documents(
        session,
        lexical,
        user_id=user_id,
        area_id=area_id,
        require_owner_metadata=require_owner_metadata,
    )
    semantic: list[tuple[SearchDocument, float]] = []
    if (
        model_router.deployments_for(ModelRole.EMBEDDING)
        and session.bind is not None
        and session.bind.dialect.name == "postgresql"
    ):
        try:
            query_embedding = await embedding_with_fallback(query)
            distance = SearchDocument.embedding.cosine_distance(query_embedding)
            statement = (
                select(SearchDocument, distance.label("distance"))
                .where(SearchDocument.is_superseded == False, SearchDocument.embedding.is_not(None))
                .order_by(distance)
                .limit(limit * candidate_multiplier)
            )
            if source_types:
                statement = statement.where(col(SearchDocument.source_type).in_(source_types))
            if user_id is not None:
                statement = statement.where(SearchDocument.owner_user_id == user_id)
            statement = _apply_temporal_filter(
                statement,
                occurred_from=occurred_from,
                occurred_until=occurred_until,
                logical_from=logical_from,
                logical_until=logical_until,
            )
            rows = (await session.execute(statement)).all()
            semantic = [(doc, max(0.0, 1.0 - float(distance_value))) for doc, distance_value in rows]
            semantic = await _filter_scoped_documents(
                session,
                semantic,
                user_id=user_id,
                area_id=area_id,
                require_owner_metadata=require_owner_metadata,
            )
        except Exception as exc:
            logger.info("Semantic retrieval unavailable: %s", exc)

    fused: dict[uuid.UUID, tuple[SearchDocument, float, list[str]]] = {}
    for reason, ranked in (("lexical", lexical), ("semantic", semantic)):
        for rank, (document, raw_score) in enumerate(ranked, start=1):
            prior = fused.get(document.id)
            score = (prior[1] if prior else 0.0) + 1.0 / (60 + rank) + raw_score * 0.05
            reasons = [*(prior[2] if prior else []), reason]
            fused[document.id] = (document, score, reasons)
    source_boost = {
        "daily_summary": 0.025,
        "timeline": 0.020,
        "capture": 0.018,
        "artifact_chunk": 0.012,
        "evidence_span": 0.025,
        "memory_claim": 0.022,
        "entity": 0.010,
        "event": 0.0,
    }
    candidates = sorted(
        fused.values(),
        key=lambda item: item[1] + source_boost.get(item[0].source_type, 0.005),
        reverse=True,
    )
    ordered = []
    per_type: dict[str, int] = {}
    event_cap = max(1, min(2, limit // 3))
    for candidate in candidates:
        source_type = candidate[0].source_type
        if source_type == "event" and per_type.get(source_type, 0) >= event_cap:
            continue
        ordered.append(candidate)
        per_type[source_type] = per_type.get(source_type, 0) + 1
        if len(ordered) >= limit:
            break
    return [
        RecallHit(
            source_type=doc.source_type,
            source_id=doc.source_id,
            title=doc.title,
            content=doc.content,
            occurred_at=doc.occurred_at,
            score=score,
            reasons=reasons,
            metadata=doc.metadata_,
        )
        for doc, score, reasons in ordered
    ]


async def semantic_recall_available(session: AsyncSession) -> bool:
    """Whether this request can execute the semantic half of hybrid recall."""
    if not (
        model_router.deployments_for(ModelRole.EMBEDDING)
        and session.bind is not None
        and session.bind.dialect.name == "postgresql"
    ):
        return False
    count = await session.scalar(
        select(func.count(SearchDocument.id)).where(
            SearchDocument.is_superseded == False,
            SearchDocument.embedding.is_not(None),
        )
    )
    return bool(count)


async def graph_context(
    session: AsyncSession,
    query: str,
    *,
    limit: int = 20,
    user_id: uuid.UUID | None = None,
    area_id: uuid.UUID | None = None,
    occurred_from: datetime | None = None,
    occurred_until: datetime | None = None,
) -> list[dict]:
    """Discover relevant entities, then return current facts around them."""
    terms = [term for term in re.findall(r"[\w.-]+", query.casefold()) if len(term) >= 3]
    if not terms:
        return []
    entity_statement = (
        select(Entity)
        .where(Entity.is_superseded == False)
        .where(func.lower(Entity.name).contains(max(terms, key=len)))
    )
    if user_id is not None:
        entity_statement = entity_statement.where(Entity.owner_user_id == user_id)
    entities = (await session.execute(entity_statement.limit(8))).scalars().all()
    if not entities:
        alias_statement = select(EntityAlias).join(
            Entity,
            Entity.id == EntityAlias.entity_id,
        ).where(
            Entity.is_superseded == False,
            func.lower(EntityAlias.alias).contains(max(terms, key=len)),
        )
        if user_id is not None:
            alias_statement = alias_statement.where(Entity.owner_user_id == user_id)
        aliases = (
            await session.execute(alias_statement.limit(8))
        ).scalars().all()
        entity_ids = [alias.entity_id for alias in aliases]
        if entity_ids:
            alias_statement = select(Entity).where(
                col(Entity.id).in_(entity_ids), Entity.is_superseded == False
            )
            if user_id is not None:
                alias_statement = alias_statement.where(Entity.owner_user_id == user_id)
            entities = (await session.execute(alias_statement)).scalars().all()
    if not entities:
        return []
    ids = [entity.id for entity in entities]
    from app.services.kernel import entity_family_ids

    family_ids: set[uuid.UUID] = set()
    for entity_id in ids:
        family_ids |= await entity_family_ids(session, entity_id)
    relation_statement = (
            select(Relation)
            .where(Relation.is_superseded == False, Relation.invalidated_at.is_(None))
            .where(
                (col(Relation.subject_id).in_(list(family_ids)))
                | (col(Relation.object_id).in_(list(family_ids)))
            )
            .order_by(col(Relation.occurred_from).desc())
            .limit(limit)
    )
    if user_id is not None:
        relation_statement = relation_statement.where(Relation.owner_user_id == user_id)
    if occurred_from is not None:
        relation_statement = relation_statement.where(
            or_(Relation.occurred_until.is_(None), Relation.occurred_until >= occurred_from)
        )
    if occurred_until is not None:
        relation_statement = relation_statement.where(Relation.occurred_from < occurred_until)
    relations = (await session.execute(relation_statement)).scalars().all()
    if area_id is not None and user_id is not None:
        scoped_relations = []
        for relation in relations:
            lineage = [
                ("event", relation.source_event_id),
                ("file_attachment", relation.source_file_id),
                ("artifact_chunk", relation.source_chunk_id),
            ]
            visible = False
            for source_type, source_id in lineage:
                if source_id is not None and await target_visible(
                    session,
                    user_id=user_id,
                    target_type=source_type,
                    target_id=source_id,
                    area_id=area_id,
                ):
                    visible = True
                    break
            if visible:
                scoped_relations.append(relation)
        relations = scoped_relations
    all_entity_ids = set(ids)
    for relation in relations:
        if relation.subject_type == "entity":
            all_entity_ids.add(relation.subject_id)
        if relation.object_type == "entity":
            all_entity_ids.add(relation.object_id)
    names = {
        entity.id: entity
        for entity in (
            await session.execute(select(Entity).where(col(Entity.id).in_(list(all_entity_ids))))
        ).scalars().all()
    }
    event_ids = {
        relation.subject_id
        for relation in relations
        if relation.subject_type == "event"
    } | {
        relation.object_id
        for relation in relations
        if relation.object_type == "event"
    }
    graph_events = {
        event.id: event
        for event in (
            await session.execute(select(Event).where(col(Event.id).in_(list(event_ids))))
        ).scalars().all()
    }

    async def display_name(entity_id: uuid.UUID) -> str:
        entity = names.get(entity_id)
        if entity is None:
            return str(entity_id)
        if not entity.is_superseded:
            return entity.name or str(entity_id)
        from app.services.kernel import resolve_current_entity

        current = await resolve_current_entity(session, entity_id)
        return (current.name or entity.name) if current is not None else (entity.name or str(entity_id))

    def event_display_name(event_id: uuid.UUID) -> str:
        event = graph_events.get(event_id)
        if event is None:
            return str(event_id)
        data = event.data or {}
        return str(
            data.get("title")
            or data.get("name")
            or data.get("app")
            or data.get("url")
            or event.event_type
        ).strip()

    return [
        {
            "subject": (
                await display_name(relation.subject_id)
                if relation.subject_type == "entity"
                else event_display_name(relation.subject_id)
            ),
            "predicate": relation.predicate,
            "object": (
                await display_name(relation.object_id)
                if relation.object_type == "entity"
                else event_display_name(relation.object_id)
            ),
            "occurred_from": relation.occurred_from,
            "occurred_until": relation.occurred_until,
            "confidence": relation.confidence,
            "source_event_id": relation.source_event_id,
            "source_file_id": relation.source_file_id,
            "source_chunk_id": relation.source_chunk_id,
        }
        for relation in relations
    ]


async def backfill_search_documents(session: AsyncSession, *, limit: int = 1000) -> dict[str, int]:
    """Rebuild recall documents from durable source tables; safe to rerun."""
    counts: dict[str, int] = {"event": 0, "timeline": 0, "daily_summary": 0, "entity": 0}
    events = (await session.execute(select(Event).where(Event.is_superseded == False).limit(limit))).scalars().all()
    for event in events:
        await upsert_search_document(
            session,
            source_type="event",
            source_id=event.id,
            title=event.event_type,
            content=f"{event.event_type}\n{event.data}",
            occurred_at=event.start_time,
            logical_date=event.logical_date,
            metadata={
                "event_type": event.event_type,
                "owner_user_id": str(event.owner_user_id) if event.owner_user_id else None,
            },
        )
        counts["event"] += 1
    entries = (await session.execute(select(TimelineEntry).limit(limit))).scalars().all()
    for entry in entries:
        await upsert_search_document(
            session,
            source_type="timeline",
            source_id=entry.id,
            title=entry.activity,
            content="\n".join(filter(None, [entry.activity, entry.category, entry.notes])),
            occurred_at=entry.start_time,
            logical_date=entry.logical_date,
            metadata={
                "owner_user_id": str(entry.owner_user_id) if entry.owner_user_id else None,
            },
        )
        counts["timeline"] += 1
    summaries = (await session.execute(select(DailySummary).limit(limit))).scalars().all()
    for summary in summaries:
        await upsert_search_document(
            session,
            source_type="daily_summary",
            source_id=summary.id,
            title=summary.logical_date,
            content=summary.summary_text,
            logical_date=summary.logical_date,
            metadata={
                "owner_user_id": (
                    str(summary.owner_user_id) if summary.owner_user_id else None
                ),
            },
        )
        counts["daily_summary"] += 1
    entities = (await session.execute(select(Entity).where(Entity.is_superseded == False).limit(limit))).scalars().all()
    for entity in entities:
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
        counts["entity"] += 1
    return counts


async def _lexical_documents(
    session: AsyncSession,
    query: str,
    limit: int,
    source_types: set[str] | None,
    *,
    occurred_from: datetime | None = None,
    occurred_until: datetime | None = None,
    logical_from: str | None = None,
    logical_until: str | None = None,
    user_id: uuid.UUID | None = None,
) -> list[tuple[SearchDocument, float]]:
    statement = select(SearchDocument).where(SearchDocument.is_superseded == False)
    if user_id is not None:
        statement = statement.where(SearchDocument.owner_user_id == user_id)
    if source_types:
        statement = statement.where(col(SearchDocument.source_type).in_(source_types))
    statement = _apply_temporal_filter(
        statement,
        occurred_from=occurred_from,
        occurred_until=occurred_until,
        logical_from=logical_from,
        logical_until=logical_until,
    )
    if session.bind is not None and session.bind.dialect.name == "postgresql":
        vector = func.to_tsvector("english", SearchDocument.content)
        parsed_query = func.websearch_to_tsquery("english", query)
        rank = func.ts_rank_cd(vector, parsed_query)
        ranked_statement = (
            statement.add_columns(rank.label("rank"))
            .where(vector.op("@@")(parsed_query))
            .order_by(rank.desc())
            .limit(limit)
        )
        rows = (await session.execute(ranked_statement)).all()
        return [(document, float(score)) for document, score in rows]
    terms = [term for term in re.findall(r"[\w'-]+", query.casefold()) if len(term) >= 3][:12]
    if not terms:
        return []
    documents = (
        await session.execute(
            statement.where(or_(*(SearchDocument.content.ilike(f"%{term}%") for term in terms)))
            .limit(limit)
        )
    ).scalars().all()
    scored = [
        (
            document,
            sum(document.content.casefold().count(term) for term in terms) / max(len(terms), 1),
        )
        for document in documents
    ]
    return sorted(scored, key=lambda item: item[1], reverse=True)


def _apply_temporal_filter(
    statement,
    *,
    occurred_from: datetime | None,
    occurred_until: datetime | None,
    logical_from: str | None,
    logical_until: str | None,
):
    """Include dated documents by either instant or LifeLog logical date."""
    instant_conditions = []
    logical_conditions = []
    if occurred_from is not None:
        instant_conditions.append(SearchDocument.occurred_at >= occurred_from)
    if occurred_until is not None:
        instant_conditions.append(SearchDocument.occurred_at < occurred_until)
    if logical_from is not None:
        logical_conditions.append(SearchDocument.logical_date >= logical_from)
    if logical_until is not None:
        logical_conditions.append(SearchDocument.logical_date < logical_until)
    alternatives = []
    if instant_conditions:
        alternatives.append(and_(*instant_conditions))
    if logical_conditions:
        alternatives.append(and_(*logical_conditions))
    return statement.where(or_(*alternatives)) if alternatives else statement


async def _filter_scoped_documents(
    session: AsyncSession,
    ranked: list[tuple[SearchDocument, float]],
    *,
    user_id: uuid.UUID | None,
    area_id: uuid.UUID | None,
    require_owner_metadata: bool = False,
) -> list[tuple[SearchDocument, float]]:
    if user_id is None:
        return ranked if area_id is None else []
    result = []
    for document, score in ranked:
        if document.owner_user_id != user_id:
            continue
        if area_id is None:
            result.append((document, score))
            continue
        if await target_visible(
            session,
            user_id=user_id,
            target_type=document.source_type,
            target_id=document.source_id,
            area_id=area_id,
        ):
            result.append((document, score))
    return result
