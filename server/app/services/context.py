import re
import uuid
from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from app.models.context import ContextLink, LifeArea, MemoryPolicy


def _now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def normalize_slug(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.casefold()).strip("-")
    if not slug or len(slug) > 80:
        raise ValueError("Life Area slug must contain letters or numbers and be at most 80 characters")
    return slug


async def get_owned_area(
    session: AsyncSession,
    area_id: uuid.UUID,
    user_id: uuid.UUID,
) -> LifeArea | None:
    area = await session.get(LifeArea, area_id)
    return area if area is not None and area.user_id == user_id else None


async def scoped_target_ids(
    session: AsyncSession,
    *,
    area_id: uuid.UUID | None,
    user_id: uuid.UUID,
    target_type: str,
) -> set[uuid.UUID]:
    """Current target ids linked to an owned area; empty set when unscoped."""
    if area_id is None:
        return set()
    area = await get_owned_area(session, area_id, user_id)
    if area is None or not area.is_active:
        return set()
    links = (
        await session.execute(
            select(ContextLink).where(
                ContextLink.life_area_id == area_id,
                ContextLink.target_type == target_type,
            )
        )
    ).scalars().all()
    return {
        link.target_id
        for link in links
        if await target_visible(
            session,
            user_id=user_id,
            target_type=target_type,
            target_id=link.target_id,
            area_id=area_id,
        )
    }


async def link_target(
    session: AsyncSession,
    area_id: uuid.UUID,
    target_type: str,
    target_id: uuid.UUID,
    *,
    role: str = "relevant",
    source: str = "user",
    confidence: float = 1.0,
    data: dict | None = None,
) -> ContextLink:
    existing = (
        await session.execute(
            select(ContextLink).where(
                ContextLink.life_area_id == area_id,
                ContextLink.target_type == target_type,
                ContextLink.target_id == target_id,
            )
        )
    ).scalars().first()
    link = existing or ContextLink(
        life_area_id=area_id,
        target_type=target_type,
        target_id=target_id,
    )
    link.role = role
    link.source = source
    link.confidence = confidence
    link.data = {**(link.data or {}), **(data or {})}
    session.add(link)
    await session.flush()
    return link


async def copy_context(
    session: AsyncSession,
    *,
    from_type: str,
    from_id: uuid.UUID,
    to_type: str,
    to_id: uuid.UUID,
    source: str = "propagated",
) -> int:
    links = (
        await session.execute(
            select(ContextLink).where(
                ContextLink.target_type == from_type,
                ContextLink.target_id == from_id,
            )
        )
    ).scalars().all()
    for link in links:
        await link_target(
            session,
            link.life_area_id,
            to_type,
            to_id,
            role=link.role,
            source=source,
            confidence=link.confidence,
            data={"propagated_from": f"{from_type}:{from_id}"},
        )
    return len(links)


async def set_policy(
    session: AsyncSession,
    user_id: uuid.UUID,
    target_type: str,
    target_id: uuid.UUID,
    *,
    visibility: str,
    allowed_area_ids: list[uuid.UUID] | list[str] | None = None,
    sensitivity: str | None = None,
    reason: str | None = None,
) -> MemoryPolicy:
    policy = (
        await session.execute(
            select(MemoryPolicy).where(
                MemoryPolicy.user_id == user_id,
                MemoryPolicy.target_type == target_type,
                MemoryPolicy.target_id == target_id,
            )
        )
    ).scalars().first()
    policy = policy or MemoryPolicy(user_id=user_id, target_type=target_type, target_id=target_id)
    policy.visibility = visibility
    policy.allowed_area_ids = [str(area_id) for area_id in (allowed_area_ids or [])]
    policy.sensitivity = sensitivity
    policy.reason = reason
    policy.updated_at = _now()
    session.add(policy)
    await session.flush()
    return policy


async def copy_policy(
    session: AsyncSession,
    *,
    user_id: uuid.UUID,
    from_type: str,
    from_id: uuid.UUID,
    to_type: str,
    to_id: uuid.UUID,
) -> MemoryPolicy | None:
    policy = (
        await session.execute(
            select(MemoryPolicy).where(
                MemoryPolicy.user_id == user_id,
                MemoryPolicy.target_type == from_type,
                MemoryPolicy.target_id == from_id,
            )
        )
    ).scalars().first()
    if policy is None:
        return None
    return await set_policy(
        session,
        user_id,
        to_type,
        to_id,
        visibility=policy.visibility,
        allowed_area_ids=policy.allowed_area_ids,
        sensitivity=policy.sensitivity,
        reason=policy.reason,
    )


async def copy_policies(
    session: AsyncSession,
    *,
    from_type: str,
    from_id: uuid.UUID,
    to_type: str,
    to_id: uuid.UUID,
) -> int:
    """Copy every owner's policy when a pipeline stage derives another memory."""
    policies = (
        await session.execute(
            select(MemoryPolicy).where(
                MemoryPolicy.target_type == from_type,
                MemoryPolicy.target_id == from_id,
            )
        )
    ).scalars().all()
    for policy in policies:
        await set_policy(
            session,
            policy.user_id,
            to_type,
            to_id,
            visibility=policy.visibility,
            allowed_area_ids=policy.allowed_area_ids,
            sensitivity=policy.sensitivity,
            reason=policy.reason,
        )
    return len(policies)


async def target_visible(
    session: AsyncSession,
    *,
    user_id: uuid.UUID,
    target_type: str,
    target_id: uuid.UUID,
    area_id: uuid.UUID | None,
) -> bool:
    """Global owner scope sees all; Life Area scope requires relevance and policy permission."""
    if area_id is None:
        return True
    area = await get_owned_area(session, area_id, user_id)
    if area is None or not area.is_active:
        return False
    linked = (
        await session.execute(
            select(ContextLink.id).where(
                ContextLink.life_area_id == area_id,
                ContextLink.target_type == target_type,
                ContextLink.target_id == target_id,
            )
        )
    ).scalars().first()
    if linked is None:
        return False
    policy = (
        await session.execute(
            select(MemoryPolicy).where(
                MemoryPolicy.user_id == user_id,
                MemoryPolicy.target_type == target_type,
                MemoryPolicy.target_id == target_id,
            )
        )
    ).scalars().first()
    if policy is None or policy.visibility == "global":
        return True
    if policy.visibility == "private":
        return False
    return str(area_id) in policy.allowed_area_ids


async def recognize_areas(
    session: AsyncSession,
    user_id: uuid.UUID,
    text: str,
) -> list[tuple[LifeArea, float]]:
    normalized = text.casefold()
    areas = (
        await session.execute(
            select(LifeArea).where(LifeArea.user_id == user_id, LifeArea.is_active == True)
        )
    ).scalars().all()
    matches = []
    for area in areas:
        hints = [area.name, area.slug, *(area.definition.get("recognition_hints") or [])]
        if any(str(hint).casefold() in normalized for hint in hints if str(hint).strip()):
            matches.append((area, 0.9))
    return matches
