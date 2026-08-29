import re
import uuid
from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from app.models.claims import EntityMention, EntityResolutionDecision, MemoryClaim
from app.models.context import ReviewItem
from app.models.kernel import Entity, EntityAlias


def _now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def _key(value: str) -> str:
    return " ".join(re.findall(r"[a-z0-9]+", value.casefold()))


async def resolve_mention(
    session: AsyncSession,
    *,
    owner_user_id: uuid.UUID,
    mention_id: uuid.UUID,
) -> Entity | None:
    """Resolve only high-precision owner/type-scoped exact identities.

    Fuzzy/vector similarity is deliberately candidate generation only in the
    future. It must never silently merge lifetime identities.
    """
    mention = (
        await session.execute(
            select(EntityMention).where(
                EntityMention.id == mention_id,
                EntityMention.owner_user_id == owner_user_id,
            )
        )
    ).scalar_one_or_none()
    if mention is None:
        return None
    if mention.resolution_status == "resolved" and mention.resolved_entity_id:
        return await session.get(Entity, mention.resolved_entity_id)
    if mention.resolution_status == "rejected":
        return None
    candidates = (
        await session.execute(
            select(Entity)
            .outerjoin(EntityAlias, EntityAlias.entity_id == Entity.id)
            .where(
                Entity.owner_user_id == owner_user_id,
                Entity.entity_type == mention.entity_type,
                Entity.is_superseded == False,
                (Entity.canonical_key == _key(mention.surface_text))
                | (EntityAlias.canonical_key == _key(mention.surface_text)),
            )
            .distinct()
        )
    ).scalars().all()
    rejected_ids = await _rejected_candidate_ids(session, mention)
    candidates = [candidate for candidate in candidates if candidate.id not in rejected_ids]
    if len(candidates) == 1:
        entity = candidates[0]
        await _record_decision(session, mention, entity, "exact_identifier", 1.0, "accepted")
        mention.resolution_status = "resolved"
        mention.resolved_entity_id = entity.id
        mention.resolved_at = _now()
        await _project_resolution(session, mention)
        session.add(mention)
        await session.flush()
        return entity
    if len(candidates) > 1:
        mention.resolution_status = "ambiguous"
        session.add(mention)
        for candidate in candidates:
            await _record_decision(session, mention, candidate, "exact_ambiguous", 1.0, "review")
        await _upsert_review(session, mention, candidates)
        await session.flush()
    return None


async def _rejected_candidate_ids(
    session: AsyncSession,
    mention: EntityMention,
) -> set[uuid.UUID]:
    """Apply the latest user constraint learned for the same normalized mention."""
    rows = (
        await session.execute(
            select(EntityResolutionDecision, EntityMention)
            .join(EntityMention, EntityMention.id == EntityResolutionDecision.mention_id)
            .where(
                EntityMention.owner_user_id == mention.owner_user_id,
                EntityMention.entity_type == mention.entity_type,
                EntityMention.normalized_text == mention.normalized_text,
                EntityResolutionDecision.method.in_(("user_constraint", "user_confirmation")),
            )
            .order_by(EntityResolutionDecision.created_at)
        )
    ).all()
    latest: dict[uuid.UUID, str] = {}
    for decision, _source_mention in rows:
        latest[decision.candidate_entity_id] = decision.outcome
    return {
        candidate_id
        for candidate_id, outcome in latest.items()
        if outcome == "rejected"
    }


async def reject_candidate(
    session: AsyncSession,
    *,
    owner_user_id: uuid.UUID,
    mention_id: uuid.UUID,
    candidate_entity_id: uuid.UUID,
) -> bool:
    mention = (
        await session.execute(
            select(EntityMention).where(
                EntityMention.id == mention_id,
                EntityMention.owner_user_id == owner_user_id,
            )
        )
    ).scalar_one_or_none()
    if mention is None:
        return None
    candidate = (
        await session.execute(
            select(Entity).where(
                Entity.id == candidate_entity_id,
                Entity.owner_user_id == owner_user_id,
            )
        )
    ).scalar_one_or_none()
    if mention is None or candidate is None:
        return False
    await _record_decision(session, mention, candidate, "user_constraint", 1.0, "rejected")
    mention.resolution_status = "rejected"
    session.add(mention)
    await session.flush()
    return True


async def accept_candidate(
    session: AsyncSession,
    *,
    owner_user_id: uuid.UUID,
    mention_id: uuid.UUID,
    candidate_entity_id: uuid.UUID,
) -> Entity | None:
    """Apply an explicit user identity decision and learn the mention as an alias."""
    mention = (
        await session.execute(
            select(EntityMention).where(
                EntityMention.id == mention_id,
                EntityMention.owner_user_id == owner_user_id,
            )
        )
    ).scalar_one_or_none()
    candidate = (
        await session.execute(
            select(Entity).where(
                Entity.id == candidate_entity_id,
                Entity.owner_user_id == owner_user_id,
                Entity.entity_type == mention.entity_type,
                Entity.is_superseded == False,
            )
        )
    ).scalar_one_or_none()
    if candidate is None:
        return None
    await _record_decision(
        session,
        mention,
        candidate,
        "user_confirmation",
        1.0,
        "accepted",
    )
    mention.resolution_status = "resolved"
    mention.resolved_entity_id = candidate.id
    mention.resolved_at = _now()
    await _project_resolution(session, mention)
    from app.services.kernel import add_entity_alias

    await add_entity_alias(session, candidate.id, mention.surface_text)
    session.add(mention)
    await session.flush()
    return candidate


async def reject_mention(
    session: AsyncSession,
    *,
    owner_user_id: uuid.UUID,
    mention_id: uuid.UUID,
) -> bool:
    """Record that none of the proposed identities should be used."""
    mention = (
        await session.execute(
            select(EntityMention).where(
                EntityMention.id == mention_id,
                EntityMention.owner_user_id == owner_user_id,
            )
        )
    ).scalar_one_or_none()
    if mention is None:
        return False
    candidates = (
        await session.execute(
            select(EntityResolutionDecision, Entity)
            .join(Entity, Entity.id == EntityResolutionDecision.candidate_entity_id)
            .where(
                EntityResolutionDecision.mention_id == mention.id,
                Entity.owner_user_id == owner_user_id,
            )
        )
    ).all()
    for _decision, candidate in candidates:
        await _record_decision(
            session,
            mention,
            candidate,
            "user_constraint",
            1.0,
            "rejected",
        )
    mention.resolution_status = "rejected"
    mention.resolved_entity_id = None
    mention.resolved_at = _now()
    session.add(mention)
    await session.flush()
    return True


async def _record_decision(
    session: AsyncSession,
    mention: EntityMention,
    candidate: Entity,
    method: str,
    score: float,
    outcome: str,
) -> EntityResolutionDecision:
    decision = (
        await session.execute(
            select(EntityResolutionDecision).where(
                EntityResolutionDecision.mention_id == mention.id,
                EntityResolutionDecision.candidate_entity_id == candidate.id,
                EntityResolutionDecision.method == method,
            )
        )
    ).scalar_one_or_none()
    if decision is None:
        decision = EntityResolutionDecision(
            mention_id=mention.id,
            candidate_entity_id=candidate.id,
            method=method,
            score=score,
            components={"exact_name_or_alias": score, "owner_match": 1.0, "type_match": 1.0},
            outcome=outcome,
            explanation="Exact normalized identity within the same owner and entity type.",
        )
        session.add(decision)
        await session.flush()
    return decision


async def _project_resolution(session: AsyncSession, mention: EntityMention) -> None:
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
            claim.subject_entity_id = mention.resolved_entity_id
        if claim.object_mention_id == mention.id:
            claim.object_entity_id = mention.resolved_entity_id
        session.add(claim)


async def _upsert_review(
    session: AsyncSession,
    mention: EntityMention,
    candidates: list[Entity],
) -> ReviewItem:
    choices = [
        {
            "id": str(candidate.id),
            "entity_id": str(candidate.id),
            "label": candidate.name or str(candidate.id),
        }
        for candidate in candidates
    ] + [{"id": "reject", "label": "None of these"}]
    item = (
        await session.execute(
            select(ReviewItem).where(
                ReviewItem.user_id == mention.owner_user_id,
                ReviewItem.source_type == "entity_mention",
                ReviewItem.source_id == mention.id,
            )
        )
    ).scalar_one_or_none()
    if item is None:
        item = ReviewItem(
            user_id=mention.owner_user_id,
            kind="entity_resolution",
            source_type="entity_mention",
            source_id=mention.id,
            title=f"Which {mention.entity_type} is “{mention.surface_text}”?",
            summary="LifeLog found more than one exact identity and will not guess.",
            choices=choices,
            consequential=mention.entity_type == "person",
            confidence=1.0,
            priority="high" if mention.entity_type == "person" else "normal",
        )
        session.add(item)
        await session.flush()
    elif item.status == "pending":
        item.choices = choices
        item.updated_at = _now()
        session.add(item)
        await session.flush()
    return item
