import uuid
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import col, or_, select

from app.core.database import get_session
from app.core.dependencies import Pagination, get_current_superuser, get_current_user
from app.models.auth import User
from app.models.ingest import Event
from app.models.kernel import Entity, EntityMerge, Relation
from app.services import kernel as kernel_service
from app.services.measurements import aggregate_measurements

router = APIRouter()


def _normalize_dt(dt: datetime | None) -> datetime | None:
    if dt is None:
        return None
    if dt.tzinfo is not None:
        return dt.astimezone(UTC).replace(tzinfo=None)
    return dt


class EntityCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    entity_type: str = Field(min_length=1, max_length=100)
    name: str | None = None
    data: dict[str, Any] | None = None
    confidence: float | None = Field(default=None, ge=0, le=1)


class RelationCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    subject_id: uuid.UUID
    subject_type: str
    predicate: str = Field(min_length=1, max_length=100)
    object_id: uuid.UUID
    object_type: str
    occurred_from: datetime | None = None
    occurred_until: datetime | None = None
    confidence: float | None = Field(default=None, ge=0, le=1)
    data: dict[str, Any] | None = None


class EventRelationCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    predicate: str = Field(min_length=1, max_length=100)
    object_id: uuid.UUID
    object_type: str
    occurred_from: datetime | None = None
    occurred_until: datetime | None = None
    confidence: float | None = Field(default=None, ge=0, le=1)
    data: dict[str, Any] | None = None


class SupersedeRequest(BaseModel):
    replacement_id: uuid.UUID | None = None


class MergeRequest(BaseModel):
    survivor_id: uuid.UUID
    merged_id: uuid.UUID


class GraphResponse(BaseModel):
    entities: list[Entity]
    events: list[Event]
    relations: list[Relation]
    truncated: bool


@router.get("/entities", response_model=list[Entity])
async def list_entities(
    entity_type: str | None = None,
    q: str | None = None,
    predicate: str | None = None,
    pagination: Pagination = Depends(),
    db_session: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    statement = (
        select(Entity)
        .where(Entity.is_superseded == False, Entity.owner_user_id == current_user.id)
        .order_by(col(Entity.created_at).desc())
        .offset(pagination.offset)
        .limit(pagination.limit)
    )
    if entity_type:
        statement = statement.where(Entity.entity_type == entity_type)
    if q:
        statement = statement.where(Entity.name.ilike(f"%{q}%"))
    if predicate:
        related_ids = select(Relation.object_id).where(
            Relation.owner_user_id == current_user.id,
            Relation.predicate == predicate,
            Relation.object_type == "entity",
            Relation.is_superseded == False,
        )
        subject_ids = select(Relation.subject_id).where(
            Relation.owner_user_id == current_user.id,
            Relation.predicate == predicate,
            Relation.subject_type == "entity",
            Relation.is_superseded == False,
        )
        statement = statement.where(or_(col(Entity.id).in_(related_ids), col(Entity.id).in_(subject_ids)))

    result = await db_session.execute(statement)
    return result.scalars().all()


@router.get("/entities/{entity_id}", response_model=Entity)
async def get_entity(
    entity_id: uuid.UUID,
    db_session: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    entity = await kernel_service.get_current_entity(db_session, entity_id)
    if entity is None or (
        entity.owner_user_id != current_user.id and not current_user.is_superuser
    ):
        raise HTTPException(status_code=404, detail="Entity not found")
    return entity


@router.get("/entities/{entity_id}/history", response_model=list[Entity])
async def get_entity_history(
    entity_id: uuid.UUID,
    db_session: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    entity = await db_session.get(Entity, entity_id)
    if entity is None or (
        entity.owner_user_id != current_user.id and not current_user.is_superuser
    ):
        raise HTTPException(status_code=404, detail="Entity not found")
    return await kernel_service.get_entity_history(db_session, entity_id)


@router.post("/entities", response_model=Entity, status_code=201)
async def create_entity(
    body: EntityCreate,
    db_session: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    try:
        entity = await kernel_service.create_entity(
            db_session,
            entity_type=body.entity_type,
            name=body.name,
            data=body.data,
            confidence=body.confidence,
            owner_user_id=current_user.id,
        )
        await db_session.commit()
        await db_session.refresh(entity)
        return entity
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except IntegrityError:
        await db_session.rollback()
        raise HTTPException(status_code=409, detail="A current entity with this type and name already exists")


@router.get("/entities/{entity_id}/graph", response_model=GraphResponse)
async def get_entity_graph(
    entity_id: uuid.UUID,
    depth: int = 1,
    relation_limit: int = 500,
    include_superseded: bool = False,
    db_session: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    if not 1 <= depth <= 3:
        raise HTTPException(status_code=400, detail="depth must be between 1 and 3")
    if not 1 <= relation_limit <= 1000:
        raise HTTPException(status_code=400, detail="relation_limit must be between 1 and 1000")
    root = await db_session.get(Entity, entity_id)
    if root is None or (
        root.owner_user_id != current_user.id and not current_user.is_superuser
    ):
        raise HTTPException(status_code=404, detail="Entity not found")
    entities, events, relations, truncated = await kernel_service.get_entity_graph(
        db_session,
        entity_id,
        depth=depth,
        include_superseded=include_superseded,
        relation_limit=relation_limit,
    )
    if not entities:
        raise HTTPException(status_code=404, detail="Entity not found")
    return {
        "entities": entities,
        "events": events,
        "relations": relations,
        "truncated": truncated,
    }


@router.post("/entities/{entity_id}/supersede", response_model=Entity)
async def supersede_entity(
    entity_id: uuid.UUID,
    body: SupersedeRequest,
    db_session: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_superuser),
):
    try:
        await kernel_service.supersede_entity(db_session, entity_id, body.replacement_id)
        await db_session.commit()
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    statement = select(Entity).where(Entity.id == entity_id)
    result = await db_session.execute(statement)
    entity = result.scalars().first()
    if entity is None:
        raise HTTPException(status_code=404, detail="Entity not found")
    return entity


@router.post("/entities/merge", status_code=200)
async def merge_entities(
    body: MergeRequest,
    db_session: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_superuser),
):
    try:
        await kernel_service.merge_entities(db_session, body.survivor_id, body.merged_id)
        await db_session.commit()
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    survivor = await kernel_service.get_current_entity(db_session, body.survivor_id)
    if survivor is None:
        raise HTTPException(status_code=404, detail="Survivor entity not found")
    return survivor


@router.post("/entities/merges/{merge_id}/reverse", response_model=EntityMerge)
async def reverse_entity_merge(
    merge_id: uuid.UUID,
    db_session: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_superuser),
) -> EntityMerge:
    try:
        merge = await kernel_service.reverse_entity_merge(db_session, merge_id)
        await db_session.commit()
        await db_session.refresh(merge)
        return merge
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.get("/relations", response_model=list[Relation])
async def list_relations(
    subject_id: uuid.UUID | None = None,
    object_id: uuid.UUID | None = None,
    include_superseded: bool = False,
    predicate: str | None = None,
    pagination: Pagination = Depends(),
    db_session: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    statement = (
        select(Relation)
        .where(Relation.owner_user_id == current_user.id)
        .order_by(col(Relation.created_at).desc())
        .offset(pagination.offset)
        .limit(pagination.limit)
    )
    if subject_id:
        statement = statement.where(Relation.subject_id == subject_id)
    if object_id:
        statement = statement.where(Relation.object_id == object_id)
    if predicate:
        statement = statement.where(Relation.predicate == predicate)
    if not include_superseded:
        statement = statement.where(Relation.is_superseded == False)

    result = await db_session.execute(statement)
    return result.scalars().all()

@router.get("/aggregates/measurement")
async def aggregate_measurement(
    entity_id: uuid.UUID | None = None,
    entity_type: str | None = None,
    metric: str | None = None,
    occurred_from: datetime | None = None,
    occurred_until: datetime | None = None,
    db_session: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> list[dict]:
    """Numeric rollups, e.g. average exam score per course."""
    return await aggregate_measurements(
        db_session,
        entity_id=entity_id,
        entity_type=entity_type,
        metric=metric,
        occurred_from=_normalize_dt(occurred_from) if occurred_from else None,
        occurred_until=_normalize_dt(occurred_until) if occurred_until else None,
        user_id=current_user.id,
    )


@router.get("/aggregates/duration")
async def aggregate_duration(
    entity_id: uuid.UUID | None = None,
    entity_type: str | None = None,
    predicate: str | None = None,
    occurred_from: datetime | None = None,
    occurred_until: datetime | None = None,
    db_session: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> list[dict]:
    """Generic valid-time rollup, e.g. hours per course/project/application."""
    return await kernel_service.aggregate_duration(
        db_session,
        entity_id=entity_id,
        entity_type=entity_type,
        predicate=predicate,
        occurred_from=_normalize_dt(occurred_from) if occurred_from else None,
        occurred_until=_normalize_dt(occurred_until) if occurred_until else None,
        user_id=current_user.id,
    )


@router.post("/relations", response_model=Relation, status_code=201)
async def create_relation(
    body: RelationCreate,
    db_session: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    try:
        relation = await kernel_service.create_relation(
            db_session,
            subject_id=body.subject_id,
            subject_type=body.subject_type,
            predicate=body.predicate,
            object_id=body.object_id,
            object_type=body.object_type,
            occurred_from=_normalize_dt(body.occurred_from),
            occurred_until=_normalize_dt(body.occurred_until),
            confidence=body.confidence,
            data=body.data,
            owner_user_id=current_user.id,
        )
        await db_session.commit()
        await db_session.refresh(relation)
        return relation
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.post("/relations/{relation_id}/supersede", response_model=Relation)
async def supersede_relation(
    relation_id: uuid.UUID,
    body: SupersedeRequest,
    db_session: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_superuser),
):
    try:
        await kernel_service.supersede_relation(db_session, relation_id, body.replacement_id)
        await db_session.commit()
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    statement = select(Relation).where(Relation.id == relation_id)
    result = await db_session.execute(statement)
    relation = result.scalars().first()
    if relation is None:
        raise HTTPException(status_code=404, detail="Relation not found")
    return relation


@router.post("/events/{event_id}/relations", response_model=Relation, status_code=201)
async def link_event_relation(
    event_id: uuid.UUID,
    body: EventRelationCreate,
    db_session: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    try:
        relation = await kernel_service.link_event(
            db_session,
            event_id=event_id,
            predicate=body.predicate,
            object_id=body.object_id,
            object_type=body.object_type,
            occurred_from=_normalize_dt(body.occurred_from),
            occurred_until=_normalize_dt(body.occurred_until),
            confidence=body.confidence,
            data=body.data,
            owner_user_id=current_user.id,
        )
        await db_session.commit()
        await db_session.refresh(relation)
        return relation
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.post("/events/{event_id}/supersede", status_code=200)
async def supersede_event(
    event_id: uuid.UUID,
    body: SupersedeRequest,
    db_session: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_superuser),
):
    try:
        await kernel_service.supersede_event(db_session, event_id, body.replacement_id)
        await db_session.commit()
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return {"message": f"Event {event_id} superseded and its derived facts retired"}
