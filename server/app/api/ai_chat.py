import hashlib
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import col, select

from app.core.database import get_session
from app.core.dependencies import get_current_user
from app.core.logger import get_logger
from app.models.auth import User
from app.models.files import Commitment
from app.models.ingest import Event
from app.models.processing import DailySummary, TimelineEntry
from app.services.ai import call_llm
from app.services.artifacts import retrieve_artifact_context
from app.services.retrieval import graph_context, retrieve

logger = get_logger(__name__)
router = APIRouter()


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=20_000)
    context_days: int = Field(default=7, ge=1, le=3650)


class ChatResponse(BaseModel):
    response: str
    context_used: bool
    citations: list[dict] = Field(default_factory=list)


async def get_user_context(
    db_session: AsyncSession,
    days: int = 7,
) -> str:
    end_date = datetime.now(UTC).replace(tzinfo=None)
    start_date = end_date - timedelta(days=days)

    parts = []

    timeline_stmt = (
        select(TimelineEntry)
        .where(TimelineEntry.start_time >= start_date)
        .order_by(col(TimelineEntry.start_time).desc())
        .limit(20)
    )
    result = await db_session.execute(timeline_stmt)
    entries = result.scalars().all()

    if entries:
        parts.append("# Recent Activities")
        for e in entries:
            start = e.start_time.strftime("%Y-%m-%d %H:%M")
            end = e.end_time.strftime("%H:%M")
            cat = f" ({e.category})" if e.category else ""
            parts.append(f"\n{start}-{end}{cat}: {e.activity}")

    summaries_stmt = (
        select(DailySummary)
        .where(DailySummary.logical_date >= start_date.strftime("%Y-%m-%d"))
        .order_by(col(DailySummary.logical_date).desc())
        .limit(7)
    )
    result = await db_session.execute(summaries_stmt)
    summaries = result.scalars().all()

    if summaries:
        parts.append("\n# Daily Summaries")
        for s in summaries:
            parts.append(f"\n## {s.logical_date}")
            parts.append(s.summary_text)

    event_stmt = (
        select(Event)
        .where(Event.event_type == "app_usage")
        .where(Event.created_at >= start_date)
        .where(Event.is_superseded == False)
    )
    result = await db_session.execute(event_stmt)
    events = result.scalars().all()

    if events:
        app_durations = {}
        for evt in events:
            app_name = (evt.data or {}).get("app", "Unknown")
            duration = float(evt.data.get("duration", 0) or 0)
            app_durations[app_name] = app_durations.get(app_name, 0) + duration

        parts.append(f"\n# App Usage (past {days} days)")
        for app, secs in sorted(app_durations.items(), key=lambda x: x[1], reverse=True)[:20]:
            hours = secs / 3600
            parts.append(f"- {app}: {hours:.1f}h" if hours >= 1 else f"- {app}: {secs/60:.0f}m")

    commitments = (
        await db_session.execute(
            select(Commitment)
            .where(Commitment.status.in_(["suggested", "planned", "in_progress"]))
            .order_by(col(Commitment.due_at).asc())
            .limit(20)
        )
    ).scalars().all()
    if commitments:
        parts.append("\n# Open Commitments")
        for item in commitments:
            due = item.due_at.isoformat() if item.due_at else "no due date"
            parts.append(f"- {item.title} — {item.status}, {due}")

    text = "\n".join(parts)
    return text if text else "No recent activity data available."


@router.post("/chat", response_model=ChatResponse)
async def chat_with_ai(
    request: ChatRequest,
    db_session: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> ChatResponse:
    try:
        context = await get_user_context(db_session, request.context_days)
        recall_hits = await retrieve(db_session, request.message, limit=12)
        artifact_context, artifact_citations = await retrieve_artifact_context(
            db_session, request.message, limit=8
        )
        graph_facts = await graph_context(db_session, request.message, limit=20)
        citations = list(artifact_citations)
        recall_parts = []
        for index, hit in enumerate(recall_hits, start=len(artifact_citations) + 1):
            marker = f"S{index}"
            recall_parts.append(f"[{marker}] {hit.title or hit.source_type}: {hit.content[:4000]}")
            citations.append(
                {
                    "id": marker,
                    "source_type": hit.source_type,
                    "source_id": str(hit.source_id),
                    "title": hit.title,
                    "metadata": hit.metadata,
                    "reasons": hit.reasons,
                }
            )
        graph_parts = [
            f"- {fact['subject']} --{fact['predicate']}--> {fact['object']} "
            f"({fact['occurred_from'] or 'undated'}, confidence={fact['confidence']})"
            for fact in graph_facts
        ]
        recall_context = "\n".join(filter(None, [artifact_context, *recall_parts]))
        graph_text = "\n".join(graph_parts)
        context_used = bool((context.strip() and "No recent" not in context) or recall_context or graph_text)

        system_prompt = (
            "You are LifeLog AI, an intelligent assistant that helps users "
            "understand and analyze their personal activity data.\n\n"
            f"Here is the user's recent activity data:\n{context}\n\n"
            f"Here are query-relevant memories:\n{recall_context or 'No relevant indexed memories.'}\n\n"
            f"Here are query-relevant current graph facts:\n{graph_text or 'No relevant graph facts.'}\n\n"
            "Answer from the supplied evidence. Cite retrieved-memory claims using their [S#] marker. "
            "Graph facts without an [S#] are supporting structure, not independently citable evidence. "
            "Say when the evidence is missing or uncertain; never fabricate a citation."
        )

        content = await call_llm(
            db_session=db_session,
            system_prompt=system_prompt,
            user_prompt=request.message,
            session_context={"operation": "grounded_chat"},
            cache_key=f"chat:{hashlib.sha256((system_prompt + request.message).encode()).hexdigest()}",
        )

        await db_session.commit()
        return ChatResponse(response=content, context_used=context_used, citations=citations)

    except RuntimeError as e:
        raise HTTPException(status_code=500, detail=f"AI service unavailable: {e}")
    except Exception as e:
        logger.exception("Chat error")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/chat/health")
async def check_ai_health():
    from app.core.config import settings
    configured = bool(settings.HACK_CLUB_AI_API_KEY or settings.GEMINI_API_KEY)
    return {"configured": configured, "model": settings.LITELLM_MODEL}
