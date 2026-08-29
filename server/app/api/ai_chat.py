"""Interactive LifeLog assistant API."""

import uuid
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from pydantic_ai.exceptions import AgentRunError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_session
from app.core.dependencies import get_current_user
from app.core.logger import get_logger
from app.models.auth import User
from app.services.context import get_owned_area
from app.services.intelligence import run_interactive_assistant
from app.services.model_router import ModelRole, model_router
from app.services.retrieval import semantic_recall_available

logger = get_logger(__name__)
router = APIRouter()


class HistoryMessage(BaseModel):
    role: Literal["user", "assistant"]
    content: str = Field(min_length=1, max_length=20_000)


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=20_000)
    life_area_id: uuid.UUID | None = None
    history: list[HistoryMessage] = Field(default_factory=list, max_length=20)
    timezone: str = Field(default="UTC", min_length=1, max_length=100)
    # Compatibility only. The assistant deliberately has no fixed context window.
    context_days: int | None = Field(default=None, ge=1, le=3650, deprecated=True)


class ChatResponse(BaseModel):
    response: str
    context_used: bool
    citations: list[dict] = Field(default_factory=list)
    retrieval: dict = Field(default_factory=dict)


@router.post("/chat", response_model=ChatResponse)
async def chat_with_ai(
    request: ChatRequest,
    db_session: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> ChatResponse:
    try:
        area = None
        if request.life_area_id is not None:
            area = await get_owned_area(db_session, request.life_area_id, current_user.id)
            if area is None:
                raise HTTPException(status_code=404, detail="Life Area not found")

        result = await run_interactive_assistant(
            session=db_session,
            user_id=current_user.id,
            area_id=request.life_area_id,
            scope_name=area.name if area else "Whole life",
            timezone=request.timezone,
            history=[(item.role, item.content) for item in request.history],
            message=request.message,
        )
        semantic_enabled = await semantic_recall_available(db_session)
        await db_session.commit()
        return ChatResponse(
            response=result.response,
            context_used=bool(result.citations),
            citations=result.citations,
            retrieval={
                "scope": area.name if area else "Whole life",
                "time_scope": "chosen by assistant from the question",
                "mode": "agentic hybrid" if semantic_enabled else "agentic lexical",
                "evidence_count": len(result.citations),
                "tools_used": result.tools_used,
                "usage": result.usage,
            },
        )
    except HTTPException:
        raise
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=f"AI service unavailable: {exc}") from exc
    except AgentRunError as exc:
        logger.warning("Assistant provider rejected or could not complete the run: %s", exc)
        raise HTTPException(
            status_code=503,
            detail="The configured AI provider could not complete this request",
        ) from exc
    except Exception as exc:
        logger.exception("Chat error")
        raise HTTPException(
            status_code=500, detail="The assistant could not complete this request"
        ) from exc


@router.get("/chat/health")
async def check_ai_health() -> dict:
    roles = model_router.readiness()
    assistant = roles[ModelRole.ASSISTANT.value]
    return {
        "configured": assistant["configured"],
        "provider": assistant["providers"][0] if assistant["providers"] else None,
        "model": assistant["models"][0] if assistant["models"] else None,
        "providers": assistant["providers"],
        "models": assistant["models"],
        "mode": "interactive_agent",
        "roles": roles,
    }
