import uuid
from datetime import UTC, datetime
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import col, select

from app.core.database import get_session
from app.core.dependencies import get_current_user
from app.models.auth import User
from app.models.config import Extension
from app.models.context import ContextLink, LifeArea, MemoryPolicy
from app.models.retrieval import SearchDocument
from app.services.context import (
    get_owned_area,
    link_target,
    normalize_slug,
    set_policy,
    target_visible,
)

router = APIRouter()


class LifeAreaCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=120)
    slug: str | None = None
    description: str | None = Field(default=None, max_length=2000)
    icon: str | None = Field(default=None, max_length=80)
    color: str | None = Field(default=None, max_length=40)
    definition: dict = Field(default_factory=dict)


class LifeAreaUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str | None = Field(default=None, min_length=1, max_length=120)
    description: str | None = Field(default=None, max_length=2000)
    icon: str | None = Field(default=None, max_length=80)
    color: str | None = Field(default=None, max_length=40)
    definition: dict | None = None
    is_active: bool | None = None


class ContextLinkCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    target_type: str = Field(min_length=1, max_length=100)
    target_id: uuid.UUID
    role: str = Field(default="relevant", max_length=100)


class MemoryPolicyWrite(BaseModel):
    model_config = ConfigDict(extra="forbid")

    target_type: str = Field(min_length=1, max_length=100)
    target_id: uuid.UUID
    visibility: Literal["global", "selected_areas", "private"] = "global"
    allowed_area_ids: list[uuid.UUID] = Field(default_factory=list)
    sensitivity: str | None = Field(default=None, max_length=100)
    reason: str | None = Field(default=None, max_length=2000)


@router.post("/life-areas", response_model=LifeArea, status_code=status.HTTP_201_CREATED)
async def create_life_area(
    body: LifeAreaCreate,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
) -> LifeArea:
    slug = normalize_slug(body.slug or body.name)
    existing = (
        await session.execute(
            select(LifeArea).where(LifeArea.user_id == user.id, LifeArea.slug == slug)
        )
    ).scalars().first()
    if existing is not None:
        raise HTTPException(status_code=409, detail="Life Area slug already exists")
    area = LifeArea(user_id=user.id, slug=slug, **body.model_dump(exclude={"slug"}))
    session.add(area)
    await session.commit()
    await session.refresh(area)
    return area


@router.get("/life-areas", response_model=list[LifeArea])
async def list_life_areas(
    include_inactive: bool = False,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
) -> list[LifeArea]:
    statement = select(LifeArea).where(LifeArea.user_id == user.id)
    if not include_inactive:
        statement = statement.where(LifeArea.is_active == True)
    return list(
        (await session.execute(statement.order_by(col(LifeArea.created_at).asc()))).scalars().all()
    )


@router.get("/life-area-templates")
async def list_life_area_templates(
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
) -> list[dict]:
    del user  # Templates are public metadata from locally installed, active extensions.
    extensions = (
        await session.execute(select(Extension).where(Extension.is_active == True))
    ).scalars().all()
    return [
        {"extension_id": extension.id, **template}
        for extension in extensions
        for template in (extension.config.get("life_areas") or [])
    ]


@router.patch("/life-areas/{area_id}", response_model=LifeArea)
async def update_life_area(
    area_id: uuid.UUID,
    body: LifeAreaUpdate,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
) -> LifeArea:
    area = await get_owned_area(session, area_id, user.id)
    if area is None:
        raise HTTPException(status_code=404, detail="Life Area not found")
    for key, value in body.model_dump(exclude_unset=True).items():
        setattr(area, key, value)
    area.updated_at = datetime.now(UTC).replace(tzinfo=None)
    session.add(area)
    await session.commit()
    await session.refresh(area)
    return area


@router.post("/life-areas/{area_id}/links", response_model=ContextLink, status_code=201)
async def add_context_link(
    area_id: uuid.UUID,
    body: ContextLinkCreate,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
) -> ContextLink:
    if await get_owned_area(session, area_id, user.id) is None:
        raise HTTPException(status_code=404, detail="Life Area not found")
    link = await link_target(
        session,
        area_id,
        body.target_type,
        body.target_id,
        role=body.role,
        source="user",
    )
    await session.commit()
    await session.refresh(link)
    return link


@router.delete("/life-areas/{area_id}/links/{link_id}", status_code=204)
async def remove_context_link(
    area_id: uuid.UUID,
    link_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
) -> None:
    if await get_owned_area(session, area_id, user.id) is None:
        raise HTTPException(status_code=404, detail="Life Area not found")
    link = await session.get(ContextLink, link_id)
    if link is None or link.life_area_id != area_id:
        raise HTTPException(status_code=404, detail="Context link not found")
    await session.delete(link)
    await session.commit()


@router.get("/life-areas/{area_id}/memories", response_model=list[SearchDocument])
async def list_area_memories(
    area_id: uuid.UUID,
    limit: int = Query(default=50, ge=1, le=500),
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
) -> list[SearchDocument]:
    if await get_owned_area(session, area_id, user.id) is None:
        raise HTTPException(status_code=404, detail="Life Area not found")
    documents = list(
        (
            await session.execute(
                select(SearchDocument)
                .join(
                    ContextLink,
                    (ContextLink.target_type == SearchDocument.source_type)
                    & (ContextLink.target_id == SearchDocument.source_id),
                )
                .where(
                    ContextLink.life_area_id == area_id,
                    SearchDocument.owner_user_id == user.id,
                    SearchDocument.is_superseded == False,
                )
                .order_by(col(SearchDocument.occurred_at).desc())
                .limit(limit)
            )
        ).scalars().all()
    )
    return [
        document
        for document in documents
        if await target_visible(
            session,
            user_id=user.id,
            target_type=document.source_type,
            target_id=document.source_id,
            area_id=area_id,
        )
    ]


@router.put("/memory-policies", response_model=MemoryPolicy)
async def write_memory_policy(
    body: MemoryPolicyWrite,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
) -> MemoryPolicy:
    for area_id in body.allowed_area_ids:
        if await get_owned_area(session, area_id, user.id) is None:
            raise HTTPException(status_code=400, detail=f"Unknown Life Area: {area_id}")
    policy = await set_policy(
        session,
        user.id,
        body.target_type,
        body.target_id,
        visibility=body.visibility,
        allowed_area_ids=body.allowed_area_ids,
        sensitivity=body.sensitivity,
        reason=body.reason,
    )
    await session.commit()
    await session.refresh(policy)
    return policy
