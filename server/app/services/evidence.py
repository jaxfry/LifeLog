import hashlib
import json
import uuid

from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import col, select, update

from app.models.evidence import EvidenceDocument, EvidenceSpan
from app.models.files import ContentChunk, FileAttachment
from app.services.context import copy_context, copy_policy

EVIDENCE_PARSER_VERSION = "1"


async def ensure_artifact_evidence(
    session: AsyncSession,
    *,
    owner_user_id: uuid.UUID,
    attachment: FileAttachment,
    capture_id: uuid.UUID | None,
    chunks: list[ContentChunk],
    parser: str = "legacy_artifact",
) -> tuple[EvidenceDocument, dict[uuid.UUID, EvidenceSpan]]:
    """Dual-write current chunks into stable, owner-scoped evidence spans."""
    ordered = sorted(chunks, key=lambda chunk: chunk.sequence)
    fingerprint_payload = {
        "source_hash": attachment.content_hash,
        "processing_version": attachment.processing_version,
        "parser": parser,
        "parser_version": EVIDENCE_PARSER_VERSION,
        "chunks": [
            {
                "id": str(chunk.id),
                "hash": _hash_text(chunk.content),
                "locator": chunk.locator,
            }
            for chunk in ordered
        ],
    }
    derivation_key = _hash_text(
        json.dumps(fingerprint_payload, sort_keys=True, separators=(",", ":"), default=str)
    )
    existing = (
        await session.execute(
            select(EvidenceDocument).where(
                EvidenceDocument.owner_user_id == owner_user_id,
                EvidenceDocument.derivation_key == derivation_key,
            )
        )
    ).scalars().first()
    if existing is not None:
        spans = (
            await session.execute(
                select(EvidenceSpan).where(EvidenceSpan.document_id == existing.id)
            )
        ).scalars().all()
        return existing, {
            span.source_chunk_id: span
            for span in spans
            if span.source_chunk_id is not None
        }

    full_text_parts: list[str] = []
    ranges: list[tuple[ContentChunk, int, int]] = []
    cursor = 0
    for chunk in ordered:
        if full_text_parts:
            full_text_parts.append("\n\n")
            cursor += 2
        start = cursor
        full_text_parts.append(chunk.content)
        cursor += len(chunk.content)
        ranges.append((chunk, start, cursor))
    full_text = "".join(full_text_parts)
    kind = _document_kind(attachment, ordered)
    document = EvidenceDocument(
        owner_user_id=owner_user_id,
        source_file_id=attachment.id,
        capture_id=capture_id,
        kind=kind,
        full_text=full_text,
        structure={
            "format": "lifelog.evidence.v1",
            "chunks": [
                {
                    "source_chunk_id": str(chunk.id),
                    "sequence": chunk.sequence,
                    "content_type": chunk.content_type,
                    "locator": chunk.locator,
                }
                for chunk in ordered
            ],
        },
        source_content_hash=attachment.content_hash,
        parser=parser,
        parser_version=EVIDENCE_PARSER_VERSION,
        derivation_key=derivation_key,
    )
    session.add(document)
    await session.flush()
    await copy_context(
        session,
        from_type="file_attachment",
        from_id=attachment.id,
        to_type="evidence_document",
        to_id=document.id,
    )
    await copy_policy(
        session,
        user_id=owner_user_id,
        from_type="file_attachment",
        from_id=attachment.id,
        to_type="evidence_document",
        to_id=document.id,
    )

    span_by_chunk: dict[uuid.UUID, EvidenceSpan] = {}
    for chunk, start, end in ranges:
        locator = dict(chunk.locator)
        span = EvidenceSpan(
            document_id=document.id,
            source_chunk_id=chunk.id,
            sequence=chunk.sequence,
            text=chunk.content,
            char_start=start,
            char_end=end,
            page_number=_integer(locator.get("page")),
            bounding_box=locator.get("bounding_box"),
            start_seconds=_number(locator.get("start_seconds")),
            end_seconds=_number(locator.get("end_seconds")),
            speaker_label=locator.get("speaker"),
            structural_path=locator.get("structural_path"),
            locator=locator,
            content_hash=_hash_text(chunk.content),
        )
        session.add(span)
        await session.flush()
        await copy_context(
            session,
            from_type="evidence_document",
            from_id=document.id,
            to_type="evidence_span",
            to_id=span.id,
        )
        await copy_policy(
            session,
            user_id=owner_user_id,
            from_type="evidence_document",
            from_id=document.id,
            to_type="evidence_span",
            to_id=span.id,
        )
        from app.services.retrieval import upsert_search_document

        await upsert_search_document(
            session,
            source_type="evidence_span",
            source_id=span.id,
            title=attachment.filename,
            content=span.text,
            occurred_at=attachment.created_at,
            version=attachment.processing_version,
            metadata={
                "owner_user_id": str(owner_user_id),
                "evidence_document_id": str(document.id),
                "source_file_id": str(attachment.id),
                "locator": span.locator,
                "page_number": span.page_number,
                "start_seconds": span.start_seconds,
                "end_seconds": span.end_seconds,
            },
        )
        span_by_chunk[chunk.id] = span
    await session.flush()

    previous = (
        await session.execute(
            select(EvidenceDocument).where(
                EvidenceDocument.owner_user_id == owner_user_id,
                EvidenceDocument.source_file_id == attachment.id,
                EvidenceDocument.id != document.id,
                EvidenceDocument.is_superseded == False,
            )
        )
    ).scalars().all()
    if previous:
        await session.execute(
            update(EvidenceDocument)
            .where(col(EvidenceDocument.id).in_([item.id for item in previous]))
            .values(is_superseded=True, superseded_by=document.id)
        )
    return document, span_by_chunk


def _document_kind(attachment: FileAttachment, chunks: list[ContentChunk]) -> str:
    if attachment.mime_type.startswith(("audio/", "video/")):
        return "transcript"
    if attachment.mime_type.startswith("image/"):
        return "image"
    if any(chunk.content_type == "transcript" for chunk in chunks):
        return "transcript"
    return "document"


def _hash_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _integer(value: object) -> int | None:
    try:
        return int(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def _number(value: object) -> float | None:
    try:
        return float(value) if value is not None else None
    except (TypeError, ValueError):
        return None
