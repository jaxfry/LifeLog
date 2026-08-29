import json
import uuid
from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from app.models.claims import FactEvidence, MemoryClaim
from app.models.context import ReviewItem
from app.services.dirty_scopes import mark_dirty_scope


async def reconcile_claim(
    session: AsyncSession,
    *,
    owner_user_id: uuid.UUID,
    claim_id: uuid.UUID,
) -> MemoryClaim | None:
    """Conservatively reconcile one grounded claim against accepted memory."""
    claim = (
        await session.execute(
            select(MemoryClaim).where(
                MemoryClaim.id == claim_id,
                MemoryClaim.owner_user_id == owner_user_id,
            )
        )
    ).scalar_one_or_none()
    if claim is None:
        return None
    if claim.reconciliation_status not in ("pending", "review"):
        return claim
    if claim.quality_score is None or claim.quality_score < 0.8:
        claim.reconciliation_status = "review"
        session.add(claim)
        await _review_conflict(session, claim, [], "Evidence quality is below auto-accept policy.")
        await session.flush()
        return claim

    candidate_peers = (
        await session.execute(
            select(MemoryClaim).where(
                MemoryClaim.owner_user_id == owner_user_id,
                MemoryClaim.id != claim.id,
                MemoryClaim.predicate == claim.predicate,
                MemoryClaim.reconciliation_status.in_(("accepted", "corroborating")),
                MemoryClaim.invalidated_at.is_(None),
            )
        )
    ).scalars().all()
    peers = [peer for peer in candidate_peers if _same_claim_subject(peer, claim)]
    overlapping = [peer for peer in peers if _overlaps(peer, claim)]
    same = [peer for peer in overlapping if _same_object_or_value(peer, claim)]
    if same:
        canonical = next(
            (
                peer
                for peer in same
                if peer.canonical_target_type is not None and peer.canonical_target_id is not None
            ),
            None,
        )
        claim.reconciliation_status = "corroborating"
        if canonical is not None:
            claim.canonical_target_type = canonical.canonical_target_type
            claim.canonical_target_id = canonical.canonical_target_id
            await _attach_fact_evidence(session, claim)
        session.add(claim)
    elif overlapping:
        claim.reconciliation_status = "conflicting"
        session.add(claim)
        await _review_conflict(
            session,
            claim,
            overlapping,
            "Two grounded claims overlap in time but disagree.",
        )
    else:
        # Reconciliation accepts the claim layer, but canonical projection is a
        # separate deterministic action. No entity/relation is invented here.
        claim.reconciliation_status = "accepted"
        session.add(claim)

    await mark_dirty_scope(
        session,
        owner_user_id=owner_user_id,
        reason="claim_reconciled",
        occurred_from=claim.valid_from,
        occurred_until=claim.valid_until,
        entity_ids=[
            value
            for value in (claim.subject_entity_id, claim.object_entity_id)
            if value is not None
        ],
        source_refs=[{"type": "memory_claim", "id": str(claim.id)}],
        materiality=claim.quality_score or 0.0,
    )
    await session.flush()
    from app.services.claims import index_claim

    await index_claim(session, claim)
    return claim


def _overlaps(left: MemoryClaim, right: MemoryClaim) -> bool:
    lower = datetime.min.replace(tzinfo=None)
    upper = datetime.max.replace(tzinfo=None)
    left_start = left.valid_from or lower
    left_end = left.valid_until or upper
    right_start = right.valid_from or lower
    right_end = right.valid_until or upper
    return left_start <= right_end and right_start <= left_end


def _same_object_or_value(left: MemoryClaim, right: MemoryClaim) -> bool:
    if left.object_entity_id is not None or right.object_entity_id is not None:
        return left.object_entity_id == right.object_entity_id
    return json.dumps(left.value, sort_keys=True, default=str) == json.dumps(
        right.value,
        sort_keys=True,
        default=str,
    ) and left.polarity == right.polarity


def _same_claim_subject(left: MemoryClaim, right: MemoryClaim) -> bool:
    """Avoid treating unrelated subjectless claims as contradictions."""
    if left.kind != right.kind:
        return False
    if left.subject_entity_id is not None or right.subject_entity_id is not None:
        return left.subject_entity_id == right.subject_entity_id
    if left.subject_mention_id is not None or right.subject_mention_id is not None:
        return left.subject_mention_id == right.subject_mention_id
    if left.kind == "commitment":
        left_title = " ".join(str((left.value or {}).get("title") or "").casefold().split())
        right_title = " ".join(str((right.value or {}).get("title") or "").casefold().split())
        return bool(left_title and left_title == right_title)
    return False


async def _attach_fact_evidence(session: AsyncSession, claim: MemoryClaim) -> None:
    if claim.canonical_target_type is None or claim.canonical_target_id is None:
        return
    exists = (
        await session.execute(
            select(FactEvidence.id).where(
                FactEvidence.target_type == claim.canonical_target_type,
                FactEvidence.target_id == claim.canonical_target_id,
                FactEvidence.claim_id == claim.id,
            )
        )
    ).scalar_one_or_none()
    if exists is None:
        session.add(
            FactEvidence(
                target_type=claim.canonical_target_type,
                target_id=claim.canonical_target_id,
                claim_id=claim.id,
                role="corroboration",
            )
        )


async def _review_conflict(
    session: AsyncSession,
    claim: MemoryClaim,
    peers: list[MemoryClaim],
    summary: str,
) -> ReviewItem:
    choices = [
        {"id": "accept_new", "label": "Use the new information"},
        {"id": "keep_existing", "label": "Keep the existing information"},
        {"id": "keep_both", "label": "Both are true"},
    ]
    item = (
        await session.execute(
            select(ReviewItem).where(
                ReviewItem.user_id == claim.owner_user_id,
                ReviewItem.source_type == "memory_claim",
                ReviewItem.source_id == claim.id,
            )
        )
    ).scalar_one_or_none()
    if item is None:
        item = ReviewItem(
            user_id=claim.owner_user_id,
            kind="claim_conflict",
            source_type="memory_claim",
            source_id=claim.id,
            title=f"Review conflicting {claim.predicate} memory",
            summary=summary,
            payload={
                "claim_id": str(claim.id),
                "conflicting_claim_ids": [str(peer.id) for peer in peers],
            },
            choices=choices,
            consequential=claim.kind in ("commitment", "measurement"),
            confidence=claim.quality_score,
            priority="high" if claim.kind == "commitment" else "normal",
        )
        session.add(item)
        await session.flush()
    elif item.status == "pending":
        item.choices = choices
        item.payload = {
            **item.payload,
            "conflicting_claim_ids": [str(peer.id) for peer in peers],
        }
        session.add(item)
        await session.flush()
    return item


async def decide_claim_conflict(
    session: AsyncSession,
    *,
    owner_user_id: uuid.UUID,
    claim_id: uuid.UUID,
    decision: str,
    conflicting_claim_ids: list[uuid.UUID],
) -> MemoryClaim:
    """Apply a user conflict decision and project only explicitly accepted memory."""
    claim = (
        await session.execute(
            select(MemoryClaim).where(
                MemoryClaim.id == claim_id,
                MemoryClaim.owner_user_id == owner_user_id,
            )
        )
    ).scalar_one_or_none()
    if claim is None:
        raise ValueError("Memory claim no longer exists")
    peers = (
        await session.execute(
            select(MemoryClaim).where(
                MemoryClaim.owner_user_id == owner_user_id,
                MemoryClaim.id.in_(conflicting_claim_ids),
            )
        )
    ).scalars().all()
    if decision == "keep_existing":
        claim.reconciliation_status = "rejected"
        claim.invalidated_at = _now()
    elif decision in ("accept_new", "keep_both"):
        if decision == "accept_new":
            for peer in peers:
                peer.reconciliation_status = "superseded"
                peer.invalidated_at = _now()
                session.add(peer)
                await _invalidate_projection_if_unsupported(session, peer)
        claim.reconciliation_status = "accepted"
        claim.invalidated_at = None
        session.add(claim)
        await _project_accepted_claim(session, claim)
    else:
        raise ValueError("Claim conflicts require accept_new, keep_existing, or keep_both")
    session.add(claim)
    await session.flush()
    from app.services.claims import index_claim

    await index_claim(session, claim)
    return claim


def _now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


async def _project_accepted_claim(
    session: AsyncSession,
    claim: MemoryClaim,
) -> None:
    if claim.canonical_target_type is not None and claim.canonical_target_id is not None:
        return
    from app.models.files import Commitment, Notification
    from app.services.claims import link_claim_projection
    from app.services.commitments import reminder_time
    from app.services.kernel import create_relation
    from app.services.measurements import create_measurement

    if (
        claim.kind == "relation"
        and claim.subject_entity_id is not None
        and claim.object_entity_id is not None
    ):
        relation = await create_relation(
            session,
            subject_id=claim.subject_entity_id,
            subject_type="entity",
            predicate=claim.predicate,
            object_id=claim.object_entity_id,
            object_type="entity",
            occurred_from=claim.valid_from,
            occurred_until=claim.valid_until,
            confidence=claim.quality_score,
            extractor="claim_reconciliation:user",
            extraction_version=claim.extraction_version,
            data={"memory_claim_id": str(claim.id), "user_confirmed": True},
            owner_user_id=claim.owner_user_id,
        )
        await link_claim_projection(
            session,
            claim,
            target_type="relation",
            target_id=relation.id,
        )
    elif claim.kind == "commitment":
        value = claim.value or {}
        title = str(value.get("title") or "").strip()
        if not title:
            return
        commitment = Commitment(
            owner_user_id=claim.owner_user_id,
            title=title,
            description=value.get("description"),
            due_at=_parse_datetime(value.get("due_at")),
            not_before=_parse_datetime(value.get("not_before")),
            confidence=claim.quality_score,
            data={"memory_claim_id": str(claim.id), "user_confirmed": True},
        )
        session.add(commitment)
        await session.flush()
        await link_claim_projection(
            session,
            claim,
            target_type="commitment",
            target_id=commitment.id,
        )
        scheduled_for = reminder_time(commitment)
        if scheduled_for is not None:
            session.add(
                Notification(
                    owner_user_id=claim.owner_user_id,
                    commitment_id=commitment.id,
                    title=commitment.title,
                    body=commitment.description,
                    scheduled_for=scheduled_for,
                    payload={"memory_claim_id": str(claim.id), "user_confirmed": True},
                )
            )
    elif claim.kind == "measurement" and claim.subject_entity_id is not None:
        value = claim.value or {}
        measurement = await create_measurement(
            session,
            entity_id=claim.subject_entity_id,
            metric=claim.predicate,
            value=float(value["value"]) if value.get("value") is not None else None,
            value_text=value.get("value_text"),
            unit=value.get("unit"),
            occurred_at=claim.valid_from,
            confidence=claim.quality_score,
            extractor="claim_reconciliation:user",
            extraction_version=claim.extraction_version,
        )
        await link_claim_projection(
            session,
            claim,
            target_type="measurement",
            target_id=measurement.id,
        )


async def _invalidate_projection_if_unsupported(
    session: AsyncSession,
    claim: MemoryClaim,
) -> None:
    if claim.canonical_target_type is None or claim.canonical_target_id is None:
        return
    active_support = (
        await session.execute(
            select(FactEvidence.id)
            .join(MemoryClaim, MemoryClaim.id == FactEvidence.claim_id)
            .where(
                FactEvidence.target_type == claim.canonical_target_type,
                FactEvidence.target_id == claim.canonical_target_id,
                MemoryClaim.id != claim.id,
                MemoryClaim.reconciliation_status.in_(("accepted", "corroborating")),
                MemoryClaim.invalidated_at.is_(None),
            )
            .limit(1)
        )
    ).scalars().first()
    if active_support is not None:
        return
    if claim.canonical_target_type == "relation":
        from app.models.kernel import Relation

        target = await session.get(Relation, claim.canonical_target_id)
        if target is not None:
            target.is_superseded = True
            target.invalidated_at = _now()
            session.add(target)
    elif claim.canonical_target_type == "measurement":
        from app.models.kernel import Measurement

        target = await session.get(Measurement, claim.canonical_target_id)
        if target is not None:
            target.is_superseded = True
            session.add(target)
    elif claim.canonical_target_type == "commitment":
        from sqlmodel import update

        from app.models.files import Commitment, Notification, PlanBlock

        target = await session.get(Commitment, claim.canonical_target_id)
        if target is not None:
            target.status = "cancelled"
            target.updated_at = _now()
            session.add(target)
            await session.execute(
                update(Notification)
                .where(Notification.commitment_id == target.id, Notification.status == "pending")
                .values(status="cancelled")
            )
            await session.execute(
                update(PlanBlock)
                .where(
                    PlanBlock.commitment_id == target.id,
                    PlanBlock.status.in_(("suggested", "accepted")),
                )
                .values(status="cancelled", updated_at=_now())
            )


def _parse_datetime(value: object | None) -> datetime | None:
    if value in (None, ""):
        return None
    parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if parsed.tzinfo is not None:
        return parsed.astimezone(UTC).replace(tzinfo=None)
    return parsed
