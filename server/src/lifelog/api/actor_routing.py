from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.exc import IntegrityError
from sqlmodel.ext.asyncio.session import AsyncSession
from sqlmodel import select

from ..dependencies import get_session
from ..auth import require_auth
from .. import models

router = APIRouter(prefix="/actor-routing", tags=["Actor Routing"])


@router.get("/")
async def list_routes(
    session: AsyncSession = Depends(get_session),
    current_user: str = Depends(require_auth),
):
    result = await session.exec(select(models.ActorRouting))
    routes = result.all()
    # Expand slugs for convenience
    out = []
    for r in routes:
        src = await session.get(models.Actor, r.source_actor_id)
        proc = await session.get(models.Actor, r.processor_actor_id)
        out.append({
            "id": r.id,
            "source_actor_id": r.source_actor_id,
            "source_actor_slug": src.slug if src else None,
            "processor_actor_id": r.processor_actor_id,
            "processor_actor_slug": proc.slug if proc else None,
        })
    return out


@router.post("/", status_code=status.HTTP_201_CREATED)
async def create_route(
    source_actor_slug: str,
    processor_actor_slug: str,
    session: AsyncSession = Depends(get_session),
    current_user: str = Depends(require_auth),
):
    src = (await session.exec(select(models.Actor).where(models.Actor.slug == source_actor_slug))).one_or_none()
    proc = (await session.exec(select(models.Actor).where(models.Actor.slug == processor_actor_slug))).one_or_none()
    if not src or not proc:
        raise HTTPException(status_code=404, detail="Source or processor actor not found")

    route = models.ActorRouting(source_actor_id=src.id, processor_actor_id=proc.id)  # type: ignore[arg-type]
    session.add(route)
    try:
        await session.commit()
    except IntegrityError:
        await session.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Route already exists for source actor")
    await session.refresh(route)
    return {"id": route.id, "source_actor_slug": source_actor_slug, "processor_actor_slug": processor_actor_slug}


@router.delete("/{route_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_route(
    route_id: int,
    session: AsyncSession = Depends(get_session),
    current_user: str = Depends(require_auth),
):
    route = await session.get(models.ActorRouting, route_id)
    if not route:
        raise HTTPException(status_code=404, detail="Route not found")
    await session.delete(route)
    await session.commit()
    return None
