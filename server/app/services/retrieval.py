import re
import uuid
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import col, select

from app.core.config import settings
from app.core.logger import get_logger
from app.models.ingest import Event
from app.models.kernel import Entity, EntityAlias, Relation
from app.models.processing import DailySummary, TimelineEntry
from app.models.retrieval import SearchDocument
from app.services.ai import embedding_with_fallback

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
    document.title = title
    document.content = content
    document.occurred_at = occurred_at
    document.logical_date = logical_date
    document.metadata_ = {**(document.metadata_ or {}), **(metadata or {})}
    document.is_superseded = False
    if generate_embedding and document.embedding is None:
        try:
            document.embedding = await embedding_with_fallback(content)
            document.embedding_model = "qwen/qwen3-embedding-8b:truncate-768"
        except Exception as exc:
            # Semantic recall is optional infrastructure. Lexical indexing must survive.
            logger.info("Embedding unavailable for %s/%s: %s", source_type, source_id, exc)
    session.add(document)
    await session.flush()
    return document


async def embed_pending_documents(session: AsyncSession, *, limit: int = 100) -> int:
    """Bounded semantic enrichment, intentionally outside source transactions."""
    if not settings.HACK_CLUB_AI_API_KEY:
        return 0
    documents = (
        await session.execute(
            select(SearchDocument)
            .where(SearchDocument.is_superseded == False, SearchDocument.embedding.is_(None))
            .order_by(col(SearchDocument.created_at).asc())
            .limit(limit)
        )
    ).scalars().all()
    completed = 0
    for document in documents:
        try:
            document.embedding = await embedding_with_fallback(document.content)
            document.embedding_model = "qwen/qwen3-embedding-8b:truncate-768"
            session.add(document)
            completed += 1
        except Exception as exc:
            logger.warning("Embedding batch stopped after provider failure: %s", exc)
            break
    await session.flush()
    return completed


async def retrieve(
    session: AsyncSession,
    query: str,
    *,
    limit: int = 12,
    source_types: set[str] | None = None,
) -> list[RecallHit]:
    """Hybrid lexical/semantic retrieval with reciprocal-rank fusion."""
    lexical = await _lexical_documents(session, query, limit * 3, source_types)
    semantic: list[tuple[SearchDocument, float]] = []
    if (
        settings.HACK_CLUB_AI_API_KEY
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
                .limit(limit * 3)
            )
            if source_types:
                statement = statement.where(col(SearchDocument.source_type).in_(source_types))
            rows = (await session.execute(statement)).all()
            semantic = [(doc, max(0.0, 1.0 - float(distance_value))) for doc, distance_value in rows]
        except Exception as exc:
            logger.info("Semantic retrieval unavailable: %s", exc)

    fused: dict[uuid.UUID, tuple[SearchDocument, float, list[str]]] = {}
    for reason, ranked in (("lexical", lexical), ("semantic", semantic)):
        for rank, (document, raw_score) in enumerate(ranked, start=1):
            prior = fused.get(document.id)
            score = (prior[1] if prior else 0.0) + 1.0 / (60 + rank) + raw_score * 0.05
            reasons = [*(prior[2] if prior else []), reason]
            fused[document.id] = (document, score, reasons)
    ordered = sorted(fused.values(), key=lambda item: item[1], reverse=True)[:limit]
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


def semantic_recall_available(session: AsyncSession) -> bool:
    """Whether this request can execute the semantic half of hybrid recall."""
    return bool(
        settings.HACK_CLUB_AI_API_KEY
        and session.bind is not None
        and session.bind.dialect.name == "postgresql"
    )


async def graph_context(session: AsyncSession, query: str, *, limit: int = 20) -> list[dict]:
    """Discover relevant entities, then return current facts around them."""
    terms = [term for term in re.findall(r"[\w.-]+", query.casefold()) if len(term) >= 3]
    if not terms:
        return []
    entities = (
        await session.execute(
            select(Entity)
            .where(Entity.is_superseded == False)
            .where(func.lower(Entity.name).contains(max(terms, key=len)))
            .limit(8)
        )
    ).scalars().all()
    if not entities:
        aliases = (
            await session.execute(
                select(EntityAlias).where(func.lower(EntityAlias.alias).contains(max(terms, key=len))).limit(8)
            )
        ).scalars().all()
        entity_ids = [alias.entity_id for alias in aliases]
        if entity_ids:
            entities = (
                await session.execute(select(Entity).where(col(Entity.id).in_(entity_ids)))
            ).scalars().all()
    if not entities:
        return []
    ids = [entity.id for entity in entities]
    relations = (
        await session.execute(
            select(Relation)
            .where(Relation.is_superseded == False, Relation.invalidated_at.is_(None))
            .where((col(Relation.subject_id).in_(ids)) | (col(Relation.object_id).in_(ids)))
            .order_by(col(Relation.occurred_from).desc())
            .limit(limit)
        )
    ).scalars().all()
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
    return [
        {
            "subject": (
                names[relation.subject_id].name
                if relation.subject_id in names
                else str(relation.subject_id)
            ),
            "predicate": relation.predicate,
            "object": names.get(relation.object_id).name if relation.object_id in names else str(relation.object_id),
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
            metadata={"event_type": event.event_type},
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
        )
        counts["timeline"] += 1
    summaries = (await session.execute(select(DailySummary).limit(limit))).scalars().all()
    for summary in summaries:
        await upsert_search_document(
            session,
            source_type="daily_summary",
            source_id=uuid.uuid5(uuid.NAMESPACE_URL, f"lifelog:daily-summary:{summary.logical_date}"),
            title=summary.logical_date,
            content=summary.summary_text,
            logical_date=summary.logical_date,
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
            metadata={"entity_type": entity.entity_type},
        )
        counts["entity"] += 1
    return counts


async def _lexical_documents(
    session: AsyncSession,
    query: str,
    limit: int,
    source_types: set[str] | None,
) -> list[tuple[SearchDocument, float]]:
    statement = select(SearchDocument).where(SearchDocument.is_superseded == False)
    if source_types:
        statement = statement.where(col(SearchDocument.source_type).in_(source_types))
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
    documents = (
        await session.execute(statement.where(SearchDocument.content.ilike(f"%{query}%")).limit(limit))
    ).scalars().all()
    return [(document, 1.0) for document in documents]
