import uuid
from datetime import datetime
from unittest.mock import AsyncMock, patch

import pytest
from sqlmodel import select

from app.models.captures import Capture, CaptureArtifact
from app.models.claims import ClaimEvidence, EntityMention, FactEvidence, MemoryClaim
from app.models.evidence import EvidenceDocument, EvidenceSpan
from app.models.files import FileAttachment
from app.services.artifacts import (
    ExtractedCommitment,
    ExtractedEntity,
    ExtractedMemory,
    ExtractedRelation,
    process_artifact,
)
from app.services.grounding import align_evidence_quote
from app.services.model_router import ModelConfigurationError, ModelRole, model_router


@pytest.mark.unit
def test_grounding_preserves_exact_offsets_and_normalized_whitespace():
    source = "Header\nProject Atlas   belongs to Biology."

    exact = align_evidence_quote(source, "Project Atlas")
    normalized = align_evidence_quote(
        source,
        "Project Atlas belongs to Biology.",
        allow_fuzzy=False,
    )

    assert exact is not None
    assert source[exact.char_start : exact.char_end] == "Project Atlas"
    assert normalized is not None
    assert normalized.method == "whitespace_normalized"
    assert source[normalized.char_start : normalized.char_end].endswith("Biology.")
    assert align_evidence_quote(source, "unrelated invented text", allow_fuzzy=False) is None


@pytest.mark.unit
def test_model_router_requires_an_explicit_vision_model(monkeypatch):
    monkeypatch.setattr("app.services.model_router.settings.OPENROUTER_API_KEY", "key")
    monkeypatch.setattr("app.services.model_router.settings.VISION_MODEL", None)
    monkeypatch.setattr("app.services.model_router.settings.GEMINI_API_KEY", None)
    monkeypatch.setattr("app.services.model_router.settings.HACK_CLUB_AI_API_KEY", None)

    with pytest.raises(ModelConfigurationError, match="vision"):
        model_router.require(ModelRole.VISION)

    monkeypatch.setattr(
        "app.services.model_router.settings.VISION_MODEL",
        "google/gemini-flash",
    )
    deployment = model_router.require(ModelRole.VISION)[0]
    assert deployment.provider == "openrouter"
    assert deployment.modalities == {"text", "image"}


@pytest.mark.asyncio
@pytest.mark.integration
async def test_owned_artifact_dual_writes_grounded_claims(
    session,
    mock_user,
    tmp_path,
    monkeypatch,
):
    from app.services import artifacts

    text = "Project Atlas belongs to Biology. Submit the lab report by 2026-09-10T17:00:00."
    path = tmp_path / "assignment.txt"
    path.write_text(text)
    monkeypatch.setattr(artifacts, "UPLOAD_DIR", tmp_path)
    capture = Capture(
        user_id=mock_user.id,
        kind="file",
        captured_at=datetime(2026, 9, 1, 16, 0),
        status="preserved",
    )
    attachment = FileAttachment(
        filename=path.name,
        stored_path=path.name,
        mime_type="text/plain",
        size_bytes=len(text),
        content_hash=uuid.uuid4().hex,
    )
    session.add(capture)
    session.add(attachment)
    await session.flush()
    session.add(CaptureArtifact(capture_id=capture.id, file_id=attachment.id))
    await session.commit()
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
                confidence=0.97,
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

    documents = (await session.execute(select(EvidenceDocument))).scalars().all()
    spans = (await session.execute(select(EvidenceSpan))).scalars().all()
    mentions = (await session.execute(select(EntityMention))).scalars().all()
    claims = (await session.execute(select(MemoryClaim))).scalars().all()
    claim_evidence = (await session.execute(select(ClaimEvidence))).scalars().all()
    fact_evidence = (await session.execute(select(FactEvidence))).scalars().all()

    assert len(documents) == 1
    assert documents[0].owner_user_id == mock_user.id
    assert len(spans) >= 5  # source chunk plus exact evidence spans
    assert {mention.surface_text for mention in mentions} == {"Project Atlas", "Biology"}
    assert all(mention.resolution_status == "resolved" for mention in mentions)
    assert {claim.kind for claim in claims} == {"relation", "commitment"}
    assert all(claim.reconciliation_status == "accepted" for claim in claims)
    assert len(claim_evidence) == 2
    assert len(fact_evidence) == 2


@pytest.mark.asyncio
@pytest.mark.integration
async def test_unknown_predicate_cannot_auto_promote_on_owned_path(
    session,
    mock_user,
    tmp_path,
    monkeypatch,
):
    from app.services import artifacts

    text = "Project Atlas secretly_quantum_links Biology."
    path = tmp_path / "unknown.txt"
    path.write_text(text)
    monkeypatch.setattr(artifacts, "UPLOAD_DIR", tmp_path)
    capture = Capture(
        user_id=mock_user.id,
        kind="file",
        captured_at=datetime(2026, 9, 1, 16, 0),
    )
    attachment = FileAttachment(
        filename=path.name,
        stored_path=path.name,
        mime_type="text/plain",
        size_bytes=len(text),
        content_hash=uuid.uuid4().hex,
    )
    session.add(capture)
    session.add(attachment)
    await session.flush()
    session.add(CaptureArtifact(capture_id=capture.id, file_id=attachment.id))
    await session.commit()
    memory = ExtractedMemory(
        entities=[
            ExtractedEntity(
                ref="project",
                entity_type="project",
                name="Project Atlas",
                confidence=0.99,
                evidence_quote="Project Atlas",
            ),
            ExtractedEntity(
                ref="course",
                entity_type="course",
                name="Biology",
                confidence=0.99,
                evidence_quote="Biology",
            ),
        ],
        relations=[
            ExtractedRelation(
                subject_ref="project",
                predicate="secretly_quantum_links",
                object_ref="course",
                confidence=0.99,
                evidence_quote=text.rstrip("."),
            )
        ],
    )

    with patch("app.services.artifacts.extract_memory", AsyncMock(return_value=memory)):
        await process_artifact(session, attachment.id)
        await session.commit()

    claim = (await session.execute(select(MemoryClaim))).scalars().one()
    assert claim.predicate == "relates_to"
    assert claim.reconciliation_status == "review"
    assert claim.canonical_target_id is None
