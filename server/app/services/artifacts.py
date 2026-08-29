import base64
import json
import re
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field, ValidationError, model_validator
from sqlalchemy import and_, func, or_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import col, select, update

from app.core.ai_files import _process_image
from app.core.config import settings
from app.core.files import UPLOAD_DIR
from app.core.logger import get_logger
from app.models.captures import Capture, CaptureArtifact
from app.models.context import ReviewItem
from app.models.evidence import EvidenceSpan
from app.models.files import Commitment, ContentChunk, FileAttachment, MemoryProposal, Notification
from app.models.kernel import Entity, Relation
from app.services.ai import call_llm, transcribe_audio
from app.services.claims import (
    link_claim_projection,
    mark_mention_resolved,
    persist_artifact_claims,
)
from app.services.commitments import reminder_time
from app.services.context import copy_context, copy_policies, copy_policy, target_visible
from app.services.derivations import complete_derivation, start_derivation
from app.services.entity_resolution import resolve_mention
from app.services.evidence import ensure_artifact_evidence
from app.services.inbox import upsert_review_item
from app.services.jobs import complete_job, fail_job, refresh_capture_status, skip_job, start_job
from app.services.kernel import create_entity, create_relation, get_current_entity_by_name
from app.services.model_router import ModelRole
from app.services.reconciliation import reconcile_claim
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
    capture_link = (
        await session.execute(
            select(CaptureArtifact).where(CaptureArtifact.file_id == attachment.id).limit(1)
        )
    ).scalars().first()
    capture_id = capture_link.capture_id if capture_link else None
    extraction_job = await start_job(
        session,
        target_type="file_attachment",
        target_id=attachment.id,
        stage="content_extraction",
        processor="core.artifact",
        processor_version=str(ARTIFACT_PROCESSING_VERSION),
        input_version=version,
        capture_id=capture_id,
    )
    active_job = extraction_job
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
        capture = await session.get(Capture, capture_id) if capture_id else None
        evidence_spans: dict[uuid.UUID, EvidenceSpan] = {}
        evidence_owner_id = (
            capture.user_id
            if capture is not None and capture.user_id is not None
            else attachment.owner_user_id
        )
        if evidence_owner_id is not None:
            derivation_run, derivation_attempt, should_run = await start_derivation(
                session,
                owner_user_id=evidence_owner_id,
                purpose="artifact_evidence_normalization",
                target_type="file_attachment",
                target_id=attachment.id,
                inputs={
                    "content_hash": attachment.content_hash,
                    "processing_version": version,
                    "chunk_ids": [str(chunk.id) for chunk in chunks],
                },
                processor="core.artifact_evidence",
                processor_version=str(ARTIFACT_PROCESSING_VERSION),
                ontology_version="1",
                policy_snapshot={"source_type": "file_attachment", "source_id": str(attachment.id)},
            )
            document, evidence_spans = await ensure_artifact_evidence(
                session,
                owner_user_id=evidence_owner_id,
                attachment=attachment,
                capture_id=capture.id if capture is not None else None,
                chunks=chunks,
            )
            if should_run:
                await complete_derivation(
                    session,
                    derivation_run,
                    derivation_attempt,
                    output_refs={
                        "evidence_document_id": str(document.id),
                        "evidence_span_ids": [str(span.id) for span in evidence_spans.values()],
                    },
                )
        for chunk in chunks:
            await copy_context(
                session,
                from_type="file_attachment",
                from_id=attachment.id,
                to_type="artifact_chunk",
                to_id=chunk.id,
            )
            if capture is not None and capture.user_id is not None:
                await copy_policy(
                    session,
                    user_id=capture.user_id,
                    from_type="file_attachment",
                    from_id=attachment.id,
                    to_type="artifact_chunk",
                    to_id=chunk.id,
                )
        await complete_job(
            session,
            extraction_job,
            output_refs={"chunk_ids": [str(chunk.id) for chunk in chunks]},
        )
        classification_job = await start_job(
            session,
            target_type="file_attachment",
            target_id=attachment.id,
            stage="classification",
            processor="core.artifact_classifier",
            input_version=version,
            capture_id=capture_id,
        )
        active_job = classification_job
        classification = await classify_artifact(session, capture_id, attachment, chunks)
        await complete_job(session, classification_job, output_refs=classification)
        memory_job = await start_job(
            session,
            target_type="file_attachment",
            target_id=attachment.id,
            stage="memory_enrichment",
            processor="core.artifact_memory",
            processor_version=str(MEMORY_EXTRACTION_VERSION),
            input_version=version,
            capture_id=capture_id,
        )
        active_job = memory_job
        enrichment_skipped = False
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
                    "owner_user_id": (
                        str(capture.user_id)
                        if capture is not None and capture.user_id is not None
                        else None
                    ),
                },
            )
            try:
                memory = await extract_memory(
                    session,
                    chunk,
                    owner_user_id=evidence_owner_id,
                )
            except RuntimeError as exc:
                logger.warning("Memory extraction unavailable for chunk %s: %s", chunk.id, exc)
                attachment.processing_error = f"Content ready; semantic extraction unavailable: {exc}"
                await skip_job(session, memory_job, exc)
                enrichment_skipped = True
                break
            await _persist_and_promote_memory(
                session,
                attachment,
                chunk,
                memory,
                owner_user_id=evidence_owner_id,
                evidence_span=evidence_spans.get(chunk.id),
            )

        if not enrichment_skipped:
            await complete_job(session, memory_job)

        if capture is not None and capture.user_id is not None:
            pending_proposals = (
                await session.execute(
                    select(MemoryProposal).where(
                        MemoryProposal.file_id == attachment.id,
                        MemoryProposal.status == "pending",
                    )
                )
            ).scalars().all()
            for proposal in pending_proposals:
                await upsert_review_item(
                    session,
                    user_id=capture.user_id,
                    kind="memory_proposal",
                    source_type="memory_proposal",
                    source_id=proposal.id,
                    capture_id=capture.id,
                    title=f"Review suggested {proposal.kind}",
                    summary=proposal.evidence_quote,
                    payload={
                        "proposal_kind": proposal.kind,
                        "confidence": proposal.confidence,
                        "proposal": proposal.payload,
                    },
                    consequential=proposal.kind == "commitment",
                )

        attachment.is_processed = True
        attachment.processing_status = "ready"
        attachment.processed_at = _utcnow()
        attachment.updated_at = _utcnow()
        session.add(attachment)
        if capture_id is not None:
            await refresh_capture_status(session, capture_id)
        await session.flush()
        return attachment
    except Exception as exc:
        await fail_job(session, active_job, exc)
        attachment.is_processed = False
        attachment.processing_status = "failed"
        attachment.processing_error = str(exc)[:2000]
        attachment.updated_at = _utcnow()
        session.add(attachment)
        await session.flush()
        await session.commit()
        raise


async def classify_artifact(
    session: AsyncSession,
    capture_id: uuid.UUID | None,
    attachment: FileAttachment,
    chunks: list[ContentChunk],
) -> dict[str, Any]:
    """Apply deterministic broad classification before domain memory enrichment."""
    capture = await session.get(Capture, capture_id) if capture_id else None
    text = "\n".join(chunk.content for chunk in chunks).casefold()
    if capture is not None and capture.intent:
        label = capture.intent
        confidence = 1.0
        source = "user_intent"
    elif any(term in text for term in ("assignment", "homework", "due date", "due ")):
        label = "assignment"
        confidence = 0.85
        source = "deterministic_content"
    elif attachment.mime_type.startswith(("audio/", "video/")):
        label = "recording"
        confidence = 0.7
        source = "media_type"
    elif attachment.mime_type.startswith("image/"):
        label = "document_scan"
        confidence = 0.65
        source = "media_type"
    else:
        label = "document"
        confidence = 0.6
        source = "media_type"
    result = {
        "label": label,
        "confidence": confidence,
        "source": source,
        "needs_review": confidence < 0.7,
    }
    if capture is not None:
        capture.classification = result
        capture.updated_at = _utcnow()
        session.add(capture)
        if result["needs_review"] and capture.user_id is not None:
            await upsert_review_item(
                session,
                user_id=capture.user_id,
                kind="classification",
                source_type="capture_classification",
                source_id=capture.id,
                capture_id=capture.id,
                title="Where should this capture belong?",
                summary=f"LifeLog classified this as {label!r} with {confidence:.0%} confidence.",
                payload=result,
            )
    await session.flush()
    return result


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
        role=ModelRole.VISION,
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


async def extract_memory(
    session: AsyncSession,
    chunk: ContentChunk,
    *,
    owner_user_id: uuid.UUID | None = None,
) -> ExtractedMemory:
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
        session_context={
            "operation": "artifact_memory",
            "source_file_id": chunk.file_id,
            "owner_user_id": owner_user_id,
        },
        max_tokens=4096,
        role=ModelRole.EXTRACTION,
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
    *,
    owner_user_id: uuid.UUID | None,
    evidence_span: EvidenceSpan | None = None,
) -> None:
    promoted_entities: dict[str, Entity] = {}
    threshold = settings.MEMORY_AUTO_ACCEPT_CONFIDENCE
    claim_bundle = None
    if owner_user_id is not None and evidence_span is not None:
        claim_bundle = await persist_artifact_claims(
            session,
            owner_user_id=owner_user_id,
            source_span=evidence_span,
            memory=memory,
            extractor="core.artifact_memory",
            extraction_version=MEMORY_EXTRACTION_VERSION,
        )
        for mention in claim_bundle.mentions_by_ref.values():
            if mention.resolution_status == "unresolved":
                await resolve_mention(
                    session,
                    owner_user_id=owner_user_id,
                    mention_id=mention.id,
                )

    for item in memory.entities:
        proposal = _proposal(attachment, chunk, "entity", item.model_dump(), item.evidence_quote, item.confidence)
        session.add(proposal)
        mention = claim_bundle.mentions_by_ref.get(item.ref) if claim_bundle else None
        if (
            item.confidence >= threshold
            and (
                claim_bundle is None
                or (
                    mention is not None
                    and mention.attributes.get("ontology_type_known") is True
                )
            )
            and _quote_is_grounded(item.evidence_quote, chunk.content)
        ):
            entity_type = mention.entity_type if mention is not None else item.entity_type
            entity = await get_current_entity_by_name(
                session, entity_type, item.name, owner_user_id=owner_user_id
            )
            if entity is None:
                entity = await create_entity(
                    session,
                    entity_type,
                    item.name,
                    confidence=item.confidence,
                    owner_user_id=owner_user_id,
                )
            await copy_context(
                session,
                from_type="artifact_chunk",
                from_id=chunk.id,
                to_type="entity",
                to_id=entity.id,
            )
            await copy_policies(
                session,
                from_type="artifact_chunk",
                from_id=chunk.id,
                to_type="entity",
                to_id=entity.id,
            )
            proposal.status = "accepted"
            proposal.promoted_id = entity.id
            proposal.decided_at = _utcnow()
            promoted_entities[item.ref] = entity
            if mention is not None:
                await mark_mention_resolved(session, mention, entity.id)

    await session.flush()
    if owner_user_id is not None and claim_bundle is not None:
        claims = [
            *claim_bundle.relation_claims.values(),
            *claim_bundle.commitment_claims.values(),
        ]
        for claim in claims:
            if claim.reconciliation_status in ("pending", "review"):
                await reconcile_claim(
                    session,
                    owner_user_id=owner_user_id,
                    claim_id=claim.id,
                )

    for item_index, item in enumerate(memory.relations):
        proposal = _proposal(attachment, chunk, "relation", item.model_dump(), item.evidence_quote, item.confidence)
        session.add(proposal)
        subject = promoted_entities.get(item.subject_ref)
        object_ = promoted_entities.get(item.object_ref)
        claim = claim_bundle.relation_claims.get(item_index) if claim_bundle else None
        if (
            item.confidence >= threshold
            and subject is not None
            and object_ is not None
            and (
                claim_bundle is None
                or (
                    claim is not None
                    and claim.reconciliation_status == "accepted"
                    and (claim.quality_score or 0.0) >= threshold
                )
            )
            and _quote_is_grounded(item.evidence_quote, chunk.content)
        ):
            relation = await create_relation(
                session,
                subject.id,
                "entity",
                claim.predicate if claim is not None else item.predicate,
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
            if claim is not None:
                await link_claim_projection(
                    session,
                    claim,
                    target_type="relation",
                    target_id=relation.id,
                )

    for item_index, item in enumerate(memory.commitments):
        proposal = _proposal(attachment, chunk, "commitment", item.model_dump(), item.evidence_quote, item.confidence)
        session.add(proposal)
        claim = claim_bundle.commitment_claims.get(item_index) if claim_bundle else None
        if (
            item.confidence >= threshold
            and (
                claim_bundle is None
                or (
                    claim is not None
                    and claim.reconciliation_status == "accepted"
                    and (claim.quality_score or 0.0) >= threshold
                )
            )
            and _quote_is_grounded(item.evidence_quote, chunk.content)
        ):
            due_at = _parse_datetime(item.due_at)
            not_before = _parse_datetime(item.not_before)
            if due_at is not None and not_before is not None and due_at < not_before:
                continue
            commitment = Commitment(
                owner_user_id=owner_user_id,
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
            await copy_context(
                session,
                from_type="artifact_chunk",
                from_id=chunk.id,
                to_type="commitment",
                to_id=commitment.id,
            )
            await copy_policies(
                session,
                from_type="artifact_chunk",
                from_id=chunk.id,
                to_type="commitment",
                to_id=commitment.id,
            )
            proposal.status = "accepted"
            proposal.promoted_id = commitment.id
            proposal.decided_at = _utcnow()
            if claim is not None:
                await link_claim_projection(
                    session,
                    claim,
                    target_type="commitment",
                    target_id=commitment.id,
                )
            if commitment.due_at is not None:
                scheduled_for = reminder_time(commitment)
                if scheduled_for is None:
                    continue
                session.add(
                    Notification(
                        owner_user_id=owner_user_id,
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
    user_id: uuid.UUID | None = None,
    area_id: uuid.UUID | None = None,
    occurred_from: datetime | None = None,
    occurred_until: datetime | None = None,
) -> tuple[str, list[dict[str, Any]]]:
    """Retrieve grounded chunks with stable citation identifiers."""
    terms = [term for term in re.findall(r"[\w'-]+", query.casefold()) if len(term) >= 3][:12]
    statement = (
        select(ContentChunk)
        .join(FileAttachment, FileAttachment.id == ContentChunk.file_id)
        .outerjoin(CaptureArtifact, CaptureArtifact.file_id == ContentChunk.file_id)
        .outerjoin(Capture, Capture.id == CaptureArtifact.capture_id)
        .where(ContentChunk.is_superseded == False)
    )
    if user_id is not None:
        statement = statement.where(FileAttachment.owner_user_id == user_id)
    temporal_conditions = []
    if occurred_from is not None:
        temporal_conditions.append(Capture.captured_at >= occurred_from)
    if occurred_until is not None:
        temporal_conditions.append(Capture.captured_at < occurred_until)
    if temporal_conditions:
        statement = statement.where(and_(*temporal_conditions))
    if terms and not temporal_conditions:
        if session.bind is not None and session.bind.dialect.name == "postgresql":
            document = func.to_tsvector("english", ContentChunk.content)
            search_query = func.websearch_to_tsquery("english", query)
            statement = statement.where(document.op("@@")(search_query)).order_by(
                func.ts_rank(document, search_query).desc()
            )
        else:
            statement = statement.where(or_(*(col(ContentChunk.content).ilike(f"%{term}%") for term in terms)))
    else:
        statement = statement.order_by(col(ContentChunk.created_at).desc())
    candidates = (await session.execute(statement.limit(100))).scalars().all()
    if terms:
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
    if area_id is not None:
        if user_id is None:
            unique_candidates = {}
        else:
            scoped_candidates = {}
            for chunk_id, chunk in unique_candidates.items():
                if await target_visible(
                    session,
                    user_id=user_id,
                    target_type="artifact_chunk",
                    target_id=chunk_id,
                    area_id=area_id,
                ):
                    scoped_candidates[chunk_id] = chunk
            unique_candidates = scoped_candidates
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
        review_item = (
            await session.execute(
                select(ReviewItem).where(
                    ReviewItem.source_type == "memory_proposal",
                    ReviewItem.source_id == proposal.id,
                    ReviewItem.status == "pending",
                )
            )
        ).scalars().first()
        if review_item is not None:
            review_item.status = "rejected"
            review_item.decided_at = _utcnow()
            review_item.updated_at = _utcnow()
            session.add(review_item)
        capture_link = (
            await session.execute(
                select(CaptureArtifact).where(CaptureArtifact.file_id == proposal.file_id).limit(1)
            )
        ).scalars().first()
        if capture_link is not None:
            await refresh_capture_status(session, capture_link.capture_id)
        await session.flush()
        return proposal
    if decision != "accept":
        raise ValueError("decision must be accept or reject")

    chunk = await session.get(ContentChunk, proposal.chunk_id)
    if chunk is None or not _quote_is_grounded(proposal.evidence_quote, chunk.content):
        raise ValueError("proposal evidence is no longer grounded in its source chunk")
    payload = proposal.payload
    capture_link = (
        await session.execute(
            select(CaptureArtifact).where(CaptureArtifact.file_id == proposal.file_id).limit(1)
        )
    ).scalars().first()
    capture = (
        await session.get(Capture, capture_link.capture_id)
        if capture_link is not None
        else None
    )
    attachment = await session.get(FileAttachment, proposal.file_id)
    owner_user_id = (
        capture.user_id
        if capture is not None
        else attachment.owner_user_id if attachment is not None else None
    )
    if proposal.kind == "entity":
        entity = await get_current_entity_by_name(
            session,
            payload["entity_type"],
            payload["name"],
            owner_user_id=owner_user_id,
        )
        if entity is None:
            entity = await create_entity(
                session,
                payload["entity_type"],
                payload["name"],
                confidence=proposal.confidence,
                owner_user_id=owner_user_id,
            )
        await copy_context(
            session,
            from_type="artifact_chunk",
            from_id=proposal.chunk_id,
            to_type="entity",
            to_id=entity.id,
        )
        await copy_policies(
            session,
            from_type="artifact_chunk",
            from_id=proposal.chunk_id,
            to_type="entity",
            to_id=entity.id,
        )
        promoted_id = entity.id
    elif proposal.kind == "commitment":
        due_at = _parse_datetime(payload.get("due_at"))
        not_before = _parse_datetime(payload.get("not_before"))
        if due_at is not None and not_before is not None and due_at < not_before:
            raise ValueError("proposal due_at is before not_before")
        commitment = Commitment(
            owner_user_id=owner_user_id,
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
        await copy_context(
            session,
            from_type="artifact_chunk",
            from_id=proposal.chunk_id,
            to_type="commitment",
            to_id=commitment.id,
        )
        await copy_policies(
            session,
            from_type="artifact_chunk",
            from_id=proposal.chunk_id,
            to_type="commitment",
            to_id=commitment.id,
        )
        promoted_id = commitment.id
        scheduled_for = reminder_time(commitment)
        if scheduled_for is not None:
            session.add(
                Notification(
                    owner_user_id=owner_user_id,
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
    review_item = (
        await session.execute(
            select(ReviewItem).where(
                ReviewItem.source_type == "memory_proposal",
                ReviewItem.source_id == proposal.id,
                ReviewItem.status == "pending",
            )
        )
    ).scalars().first()
    if review_item is not None:
        review_item.status = "accepted"
        review_item.decided_at = _utcnow()
        review_item.updated_at = _utcnow()
        session.add(review_item)
    capture_link = (
        await session.execute(
            select(CaptureArtifact).where(CaptureArtifact.file_id == proposal.file_id).limit(1)
        )
    ).scalars().first()
    if capture_link is not None:
        await refresh_capture_status(session, capture_link.capture_id)
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
