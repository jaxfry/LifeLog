import hashlib
import json
import re
import uuid
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from app.models.claims import ClaimEvidence, EntityMention, FactEvidence, MemoryClaim
from app.models.evidence import EvidenceSpan
from app.services.context import copy_context, copy_policy
from app.services.grounding import GroundingMatch, align_evidence_quote
from app.services.ontology import ontology_registry


@dataclass
class ArtifactClaimBundle:
    mentions_by_ref: dict[str, EntityMention] = field(default_factory=dict)
    relation_claims: dict[int, MemoryClaim] = field(default_factory=dict)
    commitment_claims: dict[int, MemoryClaim] = field(default_factory=dict)


async def persist_artifact_claims(
    session: AsyncSession,
    *,
    owner_user_id: uuid.UUID,
    source_span: EvidenceSpan,
    memory: Any,
    extractor: str,
    extraction_version: int,
) -> ArtifactClaimBundle:
    """Persist grounded mentions and claims before canonical promotion."""
    bundle = ArtifactClaimBundle()
    for entity in memory.entities:
        payload = entity.model_dump()
        try:
            evidence_span, match = await _grounded_span(
                session,
                source_span,
                payload["evidence_quote"],
                owner_user_id,
            )
        except ValueError:
            continue
        normalized_type, known_type = ontology_registry.normalize_entity_type(
            payload["entity_type"]
        )
        derivation_key = _fingerprint(
            "mention",
            str(evidence_span.id),
            normalized_type,
            _normalize_name(payload["name"]),
            extractor,
            extraction_version,
            ontology_registry.version,
        )
        mention = await _mention_by_key(session, owner_user_id, derivation_key)
        if mention is None:
            mention = EntityMention(
                owner_user_id=owner_user_id,
                span_id=evidence_span.id,
                surface_text=payload["name"],
                normalized_text=_normalize_name(payload["name"]),
                entity_type=normalized_type,
                attributes={
                    "proposed_entity_type": payload["entity_type"],
                    "ontology_type_known": known_type,
                    "grounding_method": match.method,
                    "grounding_score": match.score,
                },
                confidence=payload.get("confidence"),
                extractor=extractor,
                extraction_version=extraction_version,
                ontology_version=ontology_registry.version,
                resolution_status="unresolved" if known_type else "ambiguous",
                derivation_key=derivation_key,
            )
            session.add(mention)
            await session.flush()
            await _propagate_scope(session, owner_user_id, evidence_span.id, "entity_mention", mention.id)
        bundle.mentions_by_ref[payload["ref"]] = mention

    for relation_index, relation in enumerate(memory.relations):
        payload = relation.model_dump()
        try:
            evidence_span, match = await _grounded_span(
                session,
                source_span,
                payload["evidence_quote"],
                owner_user_id,
            )
        except ValueError:
            continue
        subject = bundle.mentions_by_ref.get(payload["subject_ref"])
        object_ = bundle.mentions_by_ref.get(payload["object_ref"])
        predicate, known_predicate = ontology_registry.normalize_predicate(
            payload["predicate"]
        )
        schema_valid = bool(
            subject
            and object_
            and known_predicate
            and ontology_registry.validate_relation(predicate)
        )
        derivation_key = _fingerprint(
            "relation",
            str(evidence_span.id),
            str(subject.id if subject else "missing"),
            predicate,
            str(object_.id if object_ else "missing"),
            extractor,
            extraction_version,
            ontology_registry.version,
        )
        claim = await _claim_by_key(session, owner_user_id, derivation_key)
        if claim is None:
            claim = MemoryClaim(
                owner_user_id=owner_user_id,
                kind="relation",
                subject_mention_id=subject.id if subject else None,
                predicate=predicate,
                object_mention_id=object_.id if object_ else None,
                extraction_confidence=payload.get("confidence"),
                quality_score=_quality_score(match, schema_valid, payload.get("confidence")),
                reconciliation_status="pending" if schema_valid else "review",
                extractor=extractor,
                extraction_version=extraction_version,
                ontology_version=ontology_registry.version,
                derivation_key=derivation_key,
                data={
                    "original_predicate": payload["predicate"],
                    "ontology_predicate_known": known_predicate,
                    "schema_valid": schema_valid,
                    "grounding_method": match.method,
                    "grounding_score": match.score,
                },
            )
            session.add(claim)
            await session.flush()
            await _propagate_scope(session, owner_user_id, evidence_span.id, "memory_claim", claim.id)
            session.add(ClaimEvidence(claim_id=claim.id, span_id=evidence_span.id))
            await session.flush()
            await index_claim(session, claim)
        bundle.relation_claims[relation_index] = claim

    for commitment_index, commitment in enumerate(memory.commitments):
        payload = commitment.model_dump()
        try:
            evidence_span, match = await _grounded_span(
                session,
                source_span,
                payload["evidence_quote"],
                owner_user_id,
            )
        except ValueError:
            continue
        value = {
            "title": payload["title"],
            "description": payload.get("description"),
            "due_at": payload.get("due_at"),
            "not_before": payload.get("not_before"),
        }
        derivation_key = _fingerprint(
            "commitment",
            str(evidence_span.id),
            json.dumps(value, sort_keys=True, separators=(",", ":"), default=str),
            extractor,
            extraction_version,
            ontology_registry.version,
        )
        claim = await _claim_by_key(session, owner_user_id, derivation_key)
        if claim is None:
            claim = MemoryClaim(
                owner_user_id=owner_user_id,
                kind="commitment",
                predicate="scheduled_for",
                value=value,
                modality="planned",
                extraction_confidence=payload.get("confidence"),
                quality_score=_quality_score(match, True, payload.get("confidence")),
                reconciliation_status="pending",
                extractor=extractor,
                extraction_version=extraction_version,
                ontology_version=ontology_registry.version,
                derivation_key=derivation_key,
                data={
                    "grounding_method": match.method,
                    "grounding_score": match.score,
                },
            )
            session.add(claim)
            await session.flush()
            await _propagate_scope(session, owner_user_id, evidence_span.id, "memory_claim", claim.id)
            session.add(ClaimEvidence(claim_id=claim.id, span_id=evidence_span.id))
            await session.flush()
            await index_claim(session, claim)
        bundle.commitment_claims[commitment_index] = claim
    return bundle


async def _propagate_scope(
    session: AsyncSession,
    owner_user_id: uuid.UUID,
    span_id: uuid.UUID,
    target_type: str,
    target_id: uuid.UUID,
) -> None:
    await copy_context(
        session,
        from_type="evidence_span",
        from_id=span_id,
        to_type=target_type,
        to_id=target_id,
    )
    await copy_policy(
        session,
        user_id=owner_user_id,
        from_type="evidence_span",
        from_id=span_id,
        to_type=target_type,
        to_id=target_id,
    )


async def mark_mention_resolved(
    session: AsyncSession,
    mention: EntityMention,
    entity_id: uuid.UUID,
) -> None:
    mention.resolution_status = "resolved"
    mention.resolved_entity_id = entity_id
    session.add(mention)
    claims = (
        await session.execute(
            select(MemoryClaim).where(
                (MemoryClaim.subject_mention_id == mention.id)
                | (MemoryClaim.object_mention_id == mention.id)
            )
        )
    ).scalars().all()
    for claim in claims:
        if claim.subject_mention_id == mention.id:
            claim.subject_entity_id = entity_id
        if claim.object_mention_id == mention.id:
            claim.object_entity_id = entity_id
        session.add(claim)
    await session.flush()


async def link_claim_projection(
    session: AsyncSession,
    claim: MemoryClaim,
    *,
    target_type: str,
    target_id: uuid.UUID,
    status: str = "accepted",
) -> None:
    claim.reconciliation_status = status
    claim.canonical_target_type = target_type
    claim.canonical_target_id = target_id
    session.add(claim)
    existing = (
        await session.execute(
            select(FactEvidence.id).where(
                FactEvidence.target_type == target_type,
                FactEvidence.target_id == target_id,
                FactEvidence.claim_id == claim.id,
            )
        )
    ).scalar_one_or_none()
    if existing is None:
        session.add(
            FactEvidence(
                target_type=target_type,
                target_id=target_id,
                claim_id=claim.id,
            )
        )
    await session.flush()
    await index_claim(session, claim)


async def index_claim(session: AsyncSession, claim: MemoryClaim) -> None:
    from app.services.retrieval import upsert_search_document

    value = json.dumps(claim.value, sort_keys=True, default=str) if claim.value else ""
    await upsert_search_document(
        session,
        source_type="memory_claim",
        source_id=claim.id,
        title=f"{claim.kind}: {claim.predicate}",
        content=" ".join(
            part
            for part in (
                claim.predicate,
                value,
                claim.modality,
                claim.polarity,
            )
            if part
        ),
        occurred_at=claim.valid_from or claim.learned_at,
        metadata={
            "owner_user_id": str(claim.owner_user_id),
            "status": claim.reconciliation_status,
            "canonical_target_type": claim.canonical_target_type,
            "canonical_target_id": (
                str(claim.canonical_target_id) if claim.canonical_target_id else None
            ),
            "valid_from": claim.valid_from.isoformat() if claim.valid_from else None,
            "valid_until": claim.valid_until.isoformat() if claim.valid_until else None,
            "ontology_version": claim.ontology_version,
        },
    )


async def _grounded_span(
    session: AsyncSession,
    source_span: EvidenceSpan,
    quote: str,
    owner_user_id: uuid.UUID,
) -> tuple[EvidenceSpan, GroundingMatch]:
    match = align_evidence_quote(source_span.text, quote, allow_fuzzy=False)
    if match is None:
        raise ValueError("extracted claim evidence is not exactly grounded")
    absolute_start = (source_span.char_start or 0) + match.char_start
    absolute_end = (source_span.char_start or 0) + match.char_end
    existing = (
        await session.execute(
            select(EvidenceSpan).where(
                EvidenceSpan.document_id == source_span.document_id,
                EvidenceSpan.char_start == absolute_start,
                EvidenceSpan.char_end == absolute_end,
                EvidenceSpan.content_hash == _hash_text(match.matched_text),
            )
        )
    ).scalars().first()
    if existing is not None:
        return existing, match
    maximum = (
        await session.execute(
            select(EvidenceSpan.sequence)
            .where(EvidenceSpan.document_id == source_span.document_id)
            .order_by(EvidenceSpan.sequence.desc())
            .limit(1)
        )
    ).scalar_one_or_none()
    span = EvidenceSpan(
        document_id=source_span.document_id,
        sequence=(maximum or 0) + 1,
        text=match.matched_text,
        char_start=absolute_start,
        char_end=absolute_end,
        page_number=source_span.page_number,
        bounding_box=source_span.bounding_box,
        start_seconds=source_span.start_seconds,
        end_seconds=source_span.end_seconds,
        speaker_label=source_span.speaker_label,
        structural_path=source_span.structural_path,
        locator={
            **source_span.locator,
            "parent_span_id": str(source_span.id),
            "grounding_method": match.method,
        },
        content_hash=_hash_text(match.matched_text),
    )
    session.add(span)
    await session.flush()
    await copy_context(
        session,
        from_type="evidence_span",
        from_id=source_span.id,
        to_type="evidence_span",
        to_id=span.id,
    )
    await copy_policy(
        session,
        user_id=owner_user_id,
        from_type="evidence_span",
        from_id=source_span.id,
        to_type="evidence_span",
        to_id=span.id,
    )
    return span, match


async def _mention_by_key(
    session: AsyncSession,
    owner_user_id: uuid.UUID,
    derivation_key: str,
) -> EntityMention | None:
    return (
        await session.execute(
            select(EntityMention).where(
                EntityMention.owner_user_id == owner_user_id,
                EntityMention.derivation_key == derivation_key,
            )
        )
    ).scalars().first()


async def _claim_by_key(
    session: AsyncSession,
    owner_user_id: uuid.UUID,
    derivation_key: str,
) -> MemoryClaim | None:
    return (
        await session.execute(
            select(MemoryClaim).where(
                MemoryClaim.owner_user_id == owner_user_id,
                MemoryClaim.derivation_key == derivation_key,
            )
        )
    ).scalars().first()


def _quality_score(
    match: GroundingMatch,
    schema_valid: bool,
    model_confidence: float | None,
) -> float:
    grounding = 0.5 if match.method in {"exact", "whitespace_normalized"} else 0.3 * match.score
    schema = 0.3 if schema_valid else 0.0
    confidence = max(0.0, min(1.0, float(model_confidence or 0.0))) * 0.2
    return min(1.0, grounding + schema + confidence)


def _normalize_name(value: str) -> str:
    return " ".join(re.findall(r"[a-z0-9]+", value.casefold()))


def _fingerprint(*parts: object) -> str:
    payload = "\x1f".join(str(part) for part in parts)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _hash_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()
