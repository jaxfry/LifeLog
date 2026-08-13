import uuid
from datetime import datetime
from unittest.mock import AsyncMock, patch

import pytest
from sqlmodel import select

from app.models.files import Commitment, ContentChunk, FileAttachment, MemoryProposal, Notification
from app.models.kernel import Entity, Relation
from app.services.artifacts import (
    ExtractedCommitment,
    ExtractedEntity,
    ExtractedMemory,
    ExtractedRelation,
    extract_content,
    process_artifact,
    retrieve_artifact_context,
    review_memory_proposal,
)


async def _make_text_attachment(session, tmp_path, monkeypatch, text: str) -> FileAttachment:
    from app.services import artifacts

    monkeypatch.setattr(artifacts, "UPLOAD_DIR", tmp_path)
    path = tmp_path / "notes.txt"
    path.write_text(text)
    attachment = FileAttachment(
        filename="notes.txt",
        stored_path="notes.txt",
        mime_type="text/plain",
        size_bytes=len(text),
        content_hash=uuid.uuid4().hex,
    )
    session.add(attachment)
    await session.commit()
    return attachment


@pytest.mark.asyncio
@pytest.mark.integration
async def test_artifact_pipeline_promotes_grounded_memory(session, tmp_path, monkeypatch):
    text = "Project Atlas belongs to Biology. Submit the lab report by 2026-09-10T17:00:00."
    attachment = await _make_text_attachment(session, tmp_path, monkeypatch, text)
    memory = ExtractedMemory(
        entities=[
            ExtractedEntity(
                ref="project",
                entity_type="project",
                name="Project Atlas",
                confidence=0.98,
                evidence_quote="Project Atlas",
            ),
            ExtractedEntity(
                ref="course",
                entity_type="course",
                name="Biology",
                confidence=0.98,
                evidence_quote="Biology",
            ),
        ],
        relations=[
            ExtractedRelation(
                subject_ref="project",
                predicate="belongs_to",
                object_ref="course",
                confidence=0.96,
                evidence_quote="Project Atlas belongs to Biology",
            )
        ],
        commitments=[
            ExtractedCommitment(
                title="Submit the lab report",
                due_at="2026-09-10T17:00:00",
                confidence=0.97,
                evidence_quote="Submit the lab report by 2026-09-10T17:00:00",
            )
        ],
    )

    with patch("app.services.artifacts.extract_memory", AsyncMock(return_value=memory)):
        await process_artifact(session, attachment.id)
        await session.commit()

    await session.refresh(attachment)
    assert attachment.processing_status == "ready"
    assert attachment.is_processed is True

    chunks = (await session.execute(select(ContentChunk))).scalars().all()
    proposals = (await session.execute(select(MemoryProposal))).scalars().all()
    entities = (await session.execute(select(Entity))).scalars().all()
    relations = (await session.execute(select(Relation))).scalars().all()
    commitments = (await session.execute(select(Commitment))).scalars().all()
    notifications = (await session.execute(select(Notification))).scalars().all()

    assert len(chunks) == 1
    assert len(proposals) == 4
    assert all(proposal.status == "accepted" for proposal in proposals)
    assert {entity.name for entity in entities} == {"Project Atlas", "Biology"}
    assert relations[0].source_file_id == attachment.id
    assert relations[0].source_chunk_id == chunks[0].id
    assert commitments[0].due_at == datetime(2026, 9, 10, 17, 0)
    assert notifications[0].commitment_id == commitments[0].id


@pytest.mark.asyncio
@pytest.mark.integration
async def test_low_confidence_memory_requires_review(session, tmp_path, monkeypatch):
    attachment = await _make_text_attachment(session, tmp_path, monkeypatch, "The possible codename is Zephyr.")
    memory = ExtractedMemory(
        entities=[
            ExtractedEntity(
                ref="name",
                entity_type="project",
                name="Zephyr",
                confidence=0.6,
                evidence_quote="Zephyr",
            )
        ]
    )
    with patch("app.services.artifacts.extract_memory", AsyncMock(return_value=memory)):
        await process_artifact(session, attachment.id)

    proposal = (await session.execute(select(MemoryProposal))).scalars().one()
    assert proposal.status == "pending"
    assert (await session.execute(select(Entity))).scalars().all() == []

    await review_memory_proposal(session, proposal.id, "accept")
    await session.commit()
    assert (await session.execute(select(Entity))).scalars().one().name == "Zephyr"


@pytest.mark.asyncio
@pytest.mark.integration
async def test_content_remains_searchable_when_semantic_ai_is_unavailable(session, tmp_path, monkeypatch):
    attachment = await _make_text_attachment(session, tmp_path, monkeypatch, "Mitochondria produce cellular energy.")
    with patch("app.services.artifacts.extract_memory", AsyncMock(side_effect=RuntimeError("offline"))):
        await process_artifact(session, attachment.id)
        await session.commit()

    await session.refresh(attachment)
    assert attachment.processing_status == "ready"
    assert "semantic extraction unavailable" in attachment.processing_error
    context, citations = await retrieve_artifact_context(session, "cellular energy")
    assert "Mitochondria" in context
    assert citations[0]["filename"] == "notes.txt"


@pytest.mark.asyncio
@pytest.mark.integration
async def test_audio_uses_core_transcription_provider(session, tmp_path):
    audio_path = tmp_path / "lecture.mp3"
    audio_path.write_bytes(b"test audio")
    with patch("app.services.artifacts.transcribe_audio", AsyncMock(return_value="Lecture transcript")):
        blocks = await extract_content(session, audio_path, "audio/mpeg", "lecture.mp3")
    assert blocks == [("Lecture transcript", "transcript", {"start_seconds": 0})]


@pytest.mark.asyncio
@pytest.mark.integration
async def test_scanned_pdf_pages_use_core_ocr_provider(session, tmp_path):
    import pymupdf

    pdf_path = tmp_path / "scan.pdf"
    document = pymupdf.open()
    document.new_page()
    document.save(pdf_path)
    document.close()

    with patch("app.services.artifacts._ocr_image", AsyncMock(return_value="Scanned assignment")):
        blocks = await extract_content(session, pdf_path, "application/pdf", "scan.pdf")
    assert blocks == [("Scanned assignment", "ocr", {"page": 1})]
