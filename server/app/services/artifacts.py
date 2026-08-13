import base64
import json
import re
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field, ValidationError, model_validator
from sqlalchemy import func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import col, select, update

from app.core.ai_files import _process_image
from app.core.config import settings
from app.core.files import UPLOAD_DIR
from app.core.logger import get_logger
from app.models.files import Commitment, ContentChunk, FileAttachment, MemoryProposal, Notification
from app.models.kernel import Entity, Relation
from app.services.ai import call_llm, transcribe_audio
from app.services.commitments import reminder_time
from app.services.kernel import create_entity, create_relation, get_current_entity_by_name
from app.services.retrieval import upsert_search_document

logger = get_logger(__name__)

ARTIFACT_PROCESSING_VERSION = 1
MEMORY_EXTRACTION_VERSION = 1


class ExtractedEntity(BaseModel):
    ref: str = Field(min_length=1, max_length=80)
    entity_type: str = Field(min_length=1, max_length=100)
    name: str = Field(min_length=1, max_length=500)
    confidence: float = Field(ge=0, le=1)
    evidence_quote: str = Field(min_length=1)


class ExtractedRelation(BaseModel):
    subject_ref: str
    predicate: str = Field(min_length=1, max_length=100)
    object_ref: str
    confidence: float = Field(ge=0, le=1)
    evidence_quote: str = Field(min_length=1)


class ExtractedCommitment(BaseModel):
    title: str = Field(min_length=1, max_length=500)
    description: str | None = None
    due_at: str | None = None
    not_before: str | None = None
    confidence: float = Field(ge=0, le=1)
    evidence_quote: str = Field(min_length=1)


class ExtractedMemory(BaseModel):
    entities: list[ExtractedEntity] = Field(default_factory=list)
    relations: list[ExtractedRelation] = Field(default_factory=list)
    commitments: list[ExtractedCommitment] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_references(self) -> "ExtractedMemory":
        refs = [entity.ref for entity in self.entities]
        if len(refs) != len(set(refs)):
            raise ValueError("entity refs must be unique")
        known = set(refs)
        for relation in self.relations:
            if relation.subject_ref not in known or relation.object_ref not in known:
                raise ValueError("relation refs must identify extracted entities")
        return self


async def process_artifact(
    session: AsyncSession,
    file_id: uuid.UUID,
    *,
    force: bool = False,
) -> FileAttachment:
    """Extract, chunk, and semantically enrich an attachment as one durable job."""
    attachment = (
        await session.execute(
            select(FileAttachment).where(FileAttachment.id == file_id).with_for_update()
        )
    ).scalars().first()
    if attachment is None:
        raise ValueError(f"file {file_id} does not exist")
    if attachment.processing_status == "ready" and not force:
        return attachment
    if attachment.processing_status == "processing" and not force:
        raise ValueError(f"file {file_id} is already processing")

    if force or attachment.processing_status == "failed":
        attachment.processing_version += 1
    version = attachment.processing_version
    attachment.processing_status = "processing"
    attachment.processing_error = None
    session.add(attachment)
    await session.flush()

    await session.execute(
        update(ContentChunk)
        .where(ContentChunk.file_id == attachment.id)
        .where(ContentChunk.is_superseded == False)
        .values(is_superseded=True)
    )
    await session.execute(
        update(Relation)
        .where(Relation.source_file_id == attachment.id)
        .where(Relation.is_superseded == False)
        .values(is_superseded=True, invalidated_at=_utcnow())
    )
    suggested_commitments = (
        await session.execute(
            select(Commitment)
            .where(Commitment.source_file_id == attachment.id)
            .where(Commitment.status == "suggested")
        )
    ).scalars().all()
    for commitment in suggested_commitments:
        commitment.status = "cancelled"
        commitment.updated_at = _utcnow()
        session.add(commitment)
        await session.execute(
            update(Notification)
            .where(Notification.commitment_id == commitment.id)
            .where(Notification.status == "pending")
            .values(status="cancelled")
        )

    file_path = UPLOAD_DIR / attachment.stored_path
    try:
        extracted = await extract_content(
            session,
            file_path,
            attachment.mime_type,
            attachment.filename,
            source_file_id=attachment.id,
        )
        chunks = await _persist_chunks(session, attachment, extracted, version)
        for chunk in chunks:
            await upsert_search_document(
                session,
                source_type="artifact_chunk",
                source_id=chunk.id,
                title=attachment.filename,
                content=chunk.content,
                occurred_at=attachment.created_at,
                version=version,
                metadata={
                    "file_id": str(attachment.id),
                    "locator": chunk.locator,
                    "content_type": chunk.content_type,
                },
            )
            try:
                memory = await extract_memory(session, chunk)
            except RuntimeError as exc:
                logger.warning("Memory extraction unavailable for chunk %s: %s", chunk.id, exc)
                attachment.processing_error = f"Content ready; semantic extraction unavailable: {exc}"
                break
            await _persist_and_promote_memory(session, attachment, chunk, memory)

        attachment.is_processed = True
        attachment.processing_status = "ready"
        attachment.processed_at = _utcnow()
        attachment.updated_at = _utcnow()
        session.add(attachment)
        await session.flush()
        return attachment
    except Exception as exc:
        attachment.is_processed = False
        attachment.processing_status = "failed"
        attachment.processing_error = str(exc)[:2000]
        attachment.updated_at = _utcnow()
        session.add(attachment)
        await session.flush()
        raise


async def extract_content(
    session: AsyncSession,
    file_path: Path,
    mime_type: str,
    filename: str,
    source_file_id: uuid.UUID | None = None,
) -> list[tuple[str, str, dict[str, Any]]]:
    """Return `(content, type, locator)` blocks using core media providers."""
    if not file_path.exists():
        raise ValueError("stored artifact is missing")
    if mime_type == "application/pdf":
        from pypdf import PdfReader

        blocks = []
        empty_pages = []
        for page_number, page in enumerate(PdfReader(file_path).pages, start=1):
            text = (page.extract_text() or "").strip()
            if text:
                blocks.append((text, "document_text", {"page": page_number}))
            else:
                empty_pages.append(page_number)
        if empty_pages:
            try:
                import pymupdf
            except ImportError as exc:
                raise RuntimeError("PyMuPDF is required to OCR scanned PDF pages") from exc
            with pymupdf.open(file_path) as document:
                for page_number in empty_pages:
                    pixmap = document[page_number - 1].get_pixmap(
                        matrix=pymupdf.Matrix(2, 2),
                        alpha=False,
                    )
                    image_data = base64.b64encode(pixmap.tobytes("jpeg")).decode("ascii")
                    text = await _ocr_image(
                        session,
                        image_data,
                        "image/jpeg",
                        f"{filename} page {page_number}",
                        source_file_id,
                    )
                    if text:
                        blocks.append((text, "ocr", {"page": page_number}))
        return sorted(blocks, key=lambda block: int(block[2].get("page", 0)))
    if mime_type.startswith("image/"):
        image_data = _process_image(file_path)
        if image_data is None:
            raise ValueError("image could not be decoded")
        text = await _ocr_image(session, image_data, mime_type, filename, source_file_id)
        return [(text, "ocr", {"page": 1})]
    if mime_type.startswith("audio/") or mime_type.startswith("video/"):
        text = await transcribe_audio(str(file_path))
        return [(text.strip(), "transcript", {"start_seconds": 0})]
    try:
        text = file_path.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        raise ValueError(f"unsupported artifact type: {mime_type}") from exc
    return [(text.strip(), "document_text", {})]


async def _ocr_image(
    session: AsyncSession,
    image_data: str,
    mime_type: str,
    label: str,
    source_file_id: uuid.UUID | None = None,
) -> str:
    text = await call_llm(
        db_session=session,
        system_prompt=(
            "Transcribe every legible word in this image faithfully. Preserve headings, lists, tables, "
            "dates, and handwritten uncertainty. Return plain text only; never infer missing text."
        ),
        user_prompt=[
            {"type": "text", "text": f"OCR this artifact: {label}"},
            {"type": "image_url", "image_url": {"url": f"data:{mime_type};base64,{image_data}"}},
        ],
        session_context={"operation": "artifact_ocr", "source_file_id": source_file_id},
        max_tokens=4096,
    )
    return text.strip()


async def _persist_chunks(
    session: AsyncSession,
    attachment: FileAttachment,
    blocks: list[tuple[str, str, dict[str, Any]]],
    version: int,
) -> list[ContentChunk]:
    chunks: list[ContentChunk] = []
    sequence = 0
    for content, content_type, locator in blocks:
        for text, offset in _chunk_text(content):
            chunk = ContentChunk(
                file_id=attachment.id,
                sequence=sequence,
                content=text,
                content_type=content_type,
                locator={**locator, "character_offset": offset},
                processing_version=version,
            )
            session.add(chunk)
            chunks.append(chunk)
            sequence += 1
    if not chunks:
        raise ValueError("artifact produced no searchable content")
    await session.flush()
    return chunks


async def extract_memory(session: AsyncSession, chunk: ContentChunk) -> ExtractedMemory:
    schema = ExtractedMemory.model_json_schema()
    response = await call_llm(
        db_session=session,
        system_prompt=(
            "Extract only durable, useful memory explicitly supported by the supplied text. "
            "Entities are named things or concepts worth resolving across time. Relations connect two extracted "
            "entities. Commitments are actionable obligations with optional dates. Every item must contain a short "
            "verbatim evidence_quote copied from the text. Do not invent facts. Use lowercase snake_case types and "
            "predicates. Dates must be ISO 8601 when present. Return only JSON matching this schema:\n"
            f"{json.dumps(schema)}"
        ),
        user_prompt=chunk.content,
        session_context={"operation": "artifact_memory", "source_file_id": chunk.file_id},
        max_tokens=4096,
    )
    cleaned = response.strip().removeprefix("```json").removesuffix("```").strip()
    try:
        return ExtractedMemory.model_validate_json(cleaned)
    except ValidationError as exc:
        raise RuntimeError(f"AI returned invalid memory extraction: {exc}") from exc


async def _persist_and_promote_memory(
    session: AsyncSession,
    attachment: FileAttachment,
    chunk: ContentChunk,
    memory: ExtractedMemory,
) -> None:
    promoted_entities: dict[str, Entity] = {}
    threshold = settings.MEMORY_AUTO_ACCEPT_CONFIDENCE

    for item in memory.entities:
        proposal = _proposal(attachment, chunk, "entity", item.model_dump(), item.evidence_quote, item.confidence)
        session.add(proposal)
        if item.confidence >= threshold and _quote_is_grounded(item.evidence_quote, chunk.content):
            entity = await get_current_entity_by_name(session, item.entity_type, item.name)
            if entity is None:
                entity = await create_entity(session, item.entity_type, item.name, confidence=item.confidence)
            proposal.status = "accepted"
            proposal.promoted_id = entity.id
            proposal.decided_at = _utcnow()
            promoted_entities[item.ref] = entity

    await session.flush()
    for item in memory.relations:
        proposal = _proposal(attachment, chunk, "relation", item.model_dump(), item.evidence_quote, item.confidence)
        session.add(proposal)
        subject = promoted_entities.get(item.subject_ref)
        object_ = promoted_entities.get(item.object_ref)
        if (
            item.confidence >= threshold
            and subject is not None
            and object_ is not None
            and _quote_is_grounded(item.evidence_quote, chunk.content)
        ):
            relation = await create_relation(
                session,
                subject.id,
                "entity",
                item.predicate,
                object_.id,
                "entity",
                confidence=item.confidence,
                source_file_id=attachment.id,
                source_chunk_id=chunk.id,
                extractor="core.artifact_memory",
                extraction_version=MEMORY_EXTRACTION_VERSION,
                data={"evidence_quote": item.evidence_quote},
            )
            proposal.status = "accepted"
            proposal.promoted_id = relation.id
            proposal.decided_at = _utcnow()

    for item in memory.commitments:
        proposal = _proposal(attachment, chunk, "commitment", item.model_dump(), item.evidence_quote, item.confidence)
        session.add(proposal)
        if item.confidence >= threshold and _quote_is_grounded(item.evidence_quote, chunk.content):
            due_at = _parse_datetime(item.due_at)
            not_before = _parse_datetime(item.not_before)
            if due_at is not None and not_before is not None and due_at < not_before:
                continue
            commitment = Commitment(
                title=item.title,
                description=item.description,
                due_at=due_at,
                not_before=not_before,
                confidence=item.confidence,
                source_file_id=attachment.id,
                source_chunk_id=chunk.id,
                data={"evidence_quote": item.evidence_quote},
            )
            session.add(commitment)
            await session.flush()
            proposal.status = "accepted"
            proposal.promoted_id = commitment.id
            proposal.decided_at = _utcnow()
            if commitment.due_at is not None:
                scheduled_for = reminder_time(commitment)
                if scheduled_for is None:
                    continue
                session.add(
                    Notification(
                        commitment_id=commitment.id,
                        title=commitment.title,
                        body=commitment.description,
                        scheduled_for=scheduled_for,
                        payload={"source_file_id": str(attachment.id)},
                    )
                )
    await session.flush()


async def retrieve_artifact_context(
    session: AsyncSession,
    query: str,
    limit: int = 8,
) -> tuple[str, list[dict[str, Any]]]:
    """Retrieve grounded chunks with stable citation identifiers."""
    terms = [term for term in re.findall(r"[\w'-]+", query.casefold()) if len(term) >= 3][:12]
    statement = select(ContentChunk).where(ContentChunk.is_superseded == False)
    if terms:
        if session.bind is not None and session.bind.dialect.name == "postgresql":
            document = func.to_tsvector("english", ContentChunk.content)
            search_query = func.websearch_to_tsquery("english", query)
            statement = statement.where(document.op("@@")(search_query)).order_by(
                func.ts_rank(document, search_query).desc()
            )
        else:
            from sqlalchemy import or_

            statement = statement.where(or_(*(col(ContentChunk.content).ilike(f"%{term}%") for term in terms)))
    else:
        statement = statement.order_by(col(ContentChunk.created_at).desc())
    candidates = (await session.execute(statement.limit(100))).scalars().all()
    if terms:
        from sqlalchemy import or_

        matched_entities = (
            await session.execute(
                select(Entity.id)
                .where(Entity.is_superseded == False)
                .where(or_(*(col(Entity.name).ilike(f"%{term}%") for term in terms)))
                .limit(25)
            )
        ).scalars().all()
        if matched_entities:
            graph_chunk_ids = (
                await session.execute(
                    select(Relation.source_chunk_id)
                    .where(Relation.is_superseded == False)
                    .where(Relation.source_chunk_id.is_not(None))
                    .where(
                        (Relation.subject_id.in_(matched_entities))
                        | (Relation.object_id.in_(matched_entities))
                    )
                    .limit(50)
                )
            ).scalars().all()
            if graph_chunk_ids:
                candidates.extend(
                    (
                        await session.execute(
                            select(ContentChunk)
                            .where(ContentChunk.id.in_(graph_chunk_ids))
                            .where(ContentChunk.is_superseded == False)
                        )
                    ).scalars().all()
                )
    unique_candidates = {chunk.id: chunk for chunk in candidates}
    ranked = sorted(
        unique_candidates.values(),
        key=lambda chunk: _lexical_score(chunk.content, terms),
        reverse=True,
    )[:limit]
    citations: list[dict[str, Any]] = []
    sections = []
    for index, chunk in enumerate(ranked, start=1):
        attachment = await session.get(FileAttachment, chunk.file_id)
        citation = f"S{index}"
        citations.append(
            {
                "id": citation,
                "file_id": str(chunk.file_id),
                "chunk_id": str(chunk.id),
                "filename": attachment.filename if attachment else "unknown",
                "locator": chunk.locator,
            }
        )
        sections.append(f"[{citation}] {citations[-1]['filename']} {chunk.locator}\n{chunk.content}")
    return "\n\n".join(sections), citations


async def review_memory_proposal(
    session: AsyncSession,
    proposal_id: uuid.UUID,
    decision: str,
) -> MemoryProposal:
    """Apply a human decision to an AI proposal without discarding its evidence."""
    proposal = await session.get(MemoryProposal, proposal_id)
    if proposal is None:
        raise ValueError("Memory proposal not found")
    if proposal.status != "pending":
        raise ValueError("Memory proposal has already been decided")
    if decision == "reject":
        proposal.status = "rejected"
        proposal.decided_at = _utcnow()
        session.add(proposal)
        await session.flush()
        return proposal
    if decision != "accept":
        raise ValueError("decision must be accept or reject")

    chunk = await session.get(ContentChunk, proposal.chunk_id)
    if chunk is None or not _quote_is_grounded(proposal.evidence_quote, chunk.content):
        raise ValueError("proposal evidence is no longer grounded in its source chunk")
    payload = proposal.payload
    if proposal.kind == "entity":
        entity = await get_current_entity_by_name(session, payload["entity_type"], payload["name"])
        if entity is None:
            entity = await create_entity(
                session,
                payload["entity_type"],
                payload["name"],
                confidence=proposal.confidence,
            )
        promoted_id = entity.id
    elif proposal.kind == "commitment":
        due_at = _parse_datetime(payload.get("due_at"))
        not_before = _parse_datetime(payload.get("not_before"))
        if due_at is not None and not_before is not None and due_at < not_before:
            raise ValueError("proposal due_at is before not_before")
        commitment = Commitment(
            title=payload["title"],
            description=payload.get("description"),
            due_at=due_at,
            not_before=not_before,
            confidence=proposal.confidence,
            source_file_id=proposal.file_id,
            source_chunk_id=proposal.chunk_id,
            data={"evidence_quote": proposal.evidence_quote},
        )
        session.add(commitment)
        await session.flush()
        promoted_id = commitment.id
        scheduled_for = reminder_time(commitment)
        if scheduled_for is not None:
            session.add(
                Notification(
                    commitment_id=commitment.id,
                    title=commitment.title,
                    body=commitment.description,
                    scheduled_for=scheduled_for,
                    payload={"source_file_id": str(proposal.file_id)},
                )
            )
    else:
        entity_proposals = (
            await session.execute(
                select(MemoryProposal)
                .where(MemoryProposal.chunk_id == proposal.chunk_id)
                .where(MemoryProposal.kind == "entity")
                .where(MemoryProposal.status == "accepted")
            )
        ).scalars().all()
        by_ref = {item.payload.get("ref"): item.promoted_id for item in entity_proposals}
        subject_id = by_ref.get(payload.get("subject_ref"))
        object_id = by_ref.get(payload.get("object_ref"))
        if subject_id is None or object_id is None:
            raise ValueError("accept the relation's entity proposals first")
        relation = await create_relation(
            session,
            subject_id,
            "entity",
            payload["predicate"],
            object_id,
            "entity",
            confidence=proposal.confidence,
            source_file_id=proposal.file_id,
            source_chunk_id=proposal.chunk_id,
            extractor=proposal.extractor,
            extraction_version=proposal.extraction_version,
            data={"evidence_quote": proposal.evidence_quote},
        )
        promoted_id = relation.id

    proposal.status = "accepted"
    proposal.promoted_id = promoted_id
    proposal.decided_at = _utcnow()
    session.add(proposal)
    await session.flush()
    return proposal


def _proposal(
    attachment: FileAttachment,
    chunk: ContentChunk,
    kind: str,
    payload: dict[str, Any],
    evidence_quote: str,
    confidence: float,
) -> MemoryProposal:
    return MemoryProposal(
        file_id=attachment.id,
        chunk_id=chunk.id,
        kind=kind,
        payload=payload,
        evidence_quote=evidence_quote,
        confidence=confidence,
        extractor="core.artifact_memory",
        extraction_version=MEMORY_EXTRACTION_VERSION,
    )


def _chunk_text(text: str) -> list[tuple[str, int]]:
    size = max(settings.ARTIFACT_CHUNK_CHARS, 1000)
    overlap = min(max(settings.ARTIFACT_CHUNK_OVERLAP_CHARS, 0), size // 2)
    chunks = []
    start = 0
    while start < len(text):
        end = min(start + size, len(text))
        if end < len(text):
            boundary = text.rfind("\n", start + size // 2, end)
            if boundary > start:
                end = boundary
        chunk = text[start:end].strip()
        if chunk:
            chunks.append((chunk, start))
        if end >= len(text):
            break
        start = max(end - overlap, start + 1)
    return chunks


def _quote_is_grounded(quote: str, content: str) -> bool:
    normalized_quote = " ".join(quote.casefold().split())
    normalized_content = " ".join(content.casefold().split())
    return normalized_quote in normalized_content


def _parse_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is not None:
        return parsed.astimezone(UTC).replace(tzinfo=None)
    return parsed


def _lexical_score(content: str, terms: list[str]) -> int:
    lowered = content.casefold()
    return sum(lowered.count(term) for term in terms)


def _utcnow() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)
