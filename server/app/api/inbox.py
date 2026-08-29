import uuid
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import col, select

from app.core.database import get_session
from app.core.dependencies import get_current_user
from app.models.auth import User
from app.models.context import ReviewItem
from app.services.inbox import decide_review_item, suggest_entity_merges

router = APIRouter()


class ReviewDecision(BaseModel):
    model_config = ConfigDict(extra="forbid")

    decision: str = Field(min_length=1, max_length=50)
    value: dict = Field(default_factory=dict)


@router.get("/inbox", response_model=list[ReviewItem])
async def list_inbox(
    status: Literal["pending", "accepted", "rejected", "dismissed"] | None = "pending",
    limit: int = Query(default=100, ge=1, le=500),
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
) -> list[ReviewItem]:
    statement = select(ReviewItem).where(ReviewItem.user_id == user.id)
    if status is not None:
        statement = statement.where(ReviewItem.status == status)
    return list(
        (
            await session.execute(
                statement.order_by(
                    col(ReviewItem.consequential).desc(),
                    col(ReviewItem.created_at).asc(),
                ).limit(limit)
            )
        ).scalars().all()
    )


@router.post("/inbox/{item_id}/decision", response_model=ReviewItem)
async def decide_inbox_item(
    item_id: uuid.UUID,
    body: ReviewDecision,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
) -> ReviewItem:
    item = await session.get(ReviewItem, item_id)
    if item is None or item.user_id != user.id:
        raise HTTPException(status_code=404, detail="Review item not found")
    try:
        await decide_review_item(session, item, body.decision, body.value)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    await session.commit()
    await session.refresh(item)
    return item


@router.post("/inbox/suggestions/entity-merges", status_code=200)
async def suggest_entity_merge_reviews(
    limit: int = Query(default=25, ge=1, le=100),
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
) -> dict:
    suggested = await suggest_entity_merges(session, user.id, limit=limit)
    await session.commit()
    return {"suggested": suggested}
