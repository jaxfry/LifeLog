import os
from datetime import datetime, timedelta, timezone

try:
    from zoneinfo import ZoneInfo
except ImportError:
    from backports.zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select, col
from litellm import acompletion

from app.core.db import get_session
from app.models.data import Timeline, DailySummary, RawLog, DailyChapter
from app.models.config import SystemConfig
from app.core.logger import get_logger
from app.core.vector_service import generate_embedding

logger = get_logger(__name__)
router = APIRouter()

AI_MODEL = "gemini/gemini-flash-latest"
NO_ACTIVITY_MESSAGE = "No recent activity data available."


class ChatRequest(BaseModel):
    message: str
    context_days: int = 7


class ChatResponse(BaseModel):
    response: str
    context_used: bool

async def get_gemini_api_key(db: AsyncSession) -> str:
    """
    Fetches the Gemini API key from the database or environment variables.
    """
    # 1. Try DB
    config = await db.get(SystemConfig, "GEMINI_API_KEY")
    if config and config.value:
        return config.value
    
    # 2. Fallback to Env
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        raise HTTPException(status_code=500, detail="AI service not configured. Please set GEMINI_API_KEY.")
    return api_key

async def get_user_context(session: AsyncSession, days: int = 7, user_timezone: str = "UTC") -> str:
    """
    Gather recent user activity context for the AI to reference.
    """
    try:
        tz = ZoneInfo(user_timezone)
    except Exception:
        try:
            # Try parsing as offset (e.g. "-0500")
            dummy = datetime.strptime(user_timezone, "%z")
            tz = dummy.tzinfo
        except ValueError:
            logger.warning(f"Invalid timezone {user_timezone}, falling back to UTC")
            tz = timezone.utc

    end_date = datetime.now(timezone.utc).replace(tzinfo=None)
    start_date = end_date - timedelta(days=days)
    
    # Get recent timeline entries
    timeline_query = select(Timeline).where(
        Timeline.start_time >= start_date
    ).order_by(col(Timeline.start_time).desc()).limit(20)
    
    timeline_result = await session.execute(timeline_query)
    timeline_entries = timeline_result.scalars().all()
    
    # Get recent daily summaries
    summary_query = select(DailySummary).where(
        DailySummary.date >= start_date
    ).order_by(col(DailySummary.date).desc()).limit(7)
    
    summary_result = await session.execute(summary_query)
    summaries = summary_result.scalars().all()
    
    # Build context string
    context_parts = []
    
    if summaries:
        context_parts.append("# Recent Daily Summaries")
        for summary in summaries:
            context_parts.append(f"\n## {summary.date.strftime('%Y-%m-%d')}")
            context_parts.append(summary.summary_text)
            if summary.key_activities:
                context_parts.append(f"Key Activities: {', '.join(summary.key_activities)}")
    
    if timeline_entries:
        context_parts.append("\n# Recent Activities")
        for entry in timeline_entries[:10]:  # Limit to 10 most recent
            # Convert UTC to user timezone
            utc_time = entry.start_time.replace(tzinfo=timezone.utc)
            local_time = utc_time.astimezone(tz)
            time_str = local_time.strftime('%Y-%m-%d %H:%M')
            
            context_parts.append(f"\n{time_str}: {entry.activity}")
            if entry.notes:
                context_parts.append(f"  {entry.notes}")
    
    return "\n".join(context_parts) if context_parts else "No recent activity data available."

@router.post("/chat", response_model=ChatResponse)
async def chat_with_ai(
    request: ChatRequest,
    session: AsyncSession = Depends(get_session)
):
    """
    Chat with LifeLog AI. The AI can access your recent activity data to provide insights.
    """
    try:
        # Get API key
        api_key = await get_gemini_api_key(session)
        os.environ["GEMINI_API_KEY"] = api_key
        
        # Get user timezone from most recent RawLog
        # This ensures we use the client's actual timezone from their device
        timezone_query = select(RawLog.client_timezone).where(
            RawLog.client_timezone.is_not(None)
        ).order_by(col(RawLog.received_at).desc()).limit(1)
        
        timezone_result = await session.execute(timezone_query)
        user_timezone = timezone_result.scalar_one_or_none() or "UTC"
        
        # Get user context (recent)
        recent_context = await get_user_context(session, request.context_days, user_timezone)
        
        # Get vector context (relevant)
        vector_context = ""
        embedding = await generate_embedding(request.message)
        if embedding:
            # Search Timeline
            stmt_timeline = select(Timeline).where(Timeline.embedding.is_not(None)).order_by(Timeline.embedding.l2_distance(embedding)).limit(10)
            result_timeline = await session.execute(stmt_timeline)
            timeline_entries = result_timeline.scalars().all()
            
            # Search Chapters
            stmt_chapters = select(DailyChapter).where(DailyChapter.embedding.is_not(None)).order_by(DailyChapter.embedding.l2_distance(embedding)).limit(5)
            result_chapters = await session.execute(stmt_chapters)
            chapters = result_chapters.scalars().all()
            
            parts = []
            if chapters:
                parts.append("## Relevant Historical Chapters")
                for c in chapters:
                    parts.append(f"- {c.date.date()} {c.title}: {c.summary}")
            
            if timeline_entries:
                parts.append("## Relevant Historical Activities")
                for t in timeline_entries:
                    parts.append(f"- {t.start_time} to {t.end_time}: {t.activity} ({t.notes})")
            
            vector_context = "\n".join(parts)

        # Build the system prompt
        system_prompt = f"""You are LifeLog AI, an intelligent assistant that helps users understand and analyze their personal activity data.

You have access to the user's recent activity timeline and daily summaries, as well as semantically relevant historical data. Use this information to provide insightful, personalized responses.

When the user asks questions about their activities, productivity, or patterns, reference specific data from their timeline.

Be concise, helpful, and insightful. If you don't have enough data to answer a question, say so clearly.

Here is the user's recent activity data:
{recent_context}

Here is some relevant historical data based on the user's query:
{vector_context}
"""
        
        # Call the AI
        response = await acompletion(
            model="gemini/gemini-flash-latest",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": request.message}
            ],
            api_key=api_key
        )
        
        ai_response = response.choices[0].message.content
        
        return ChatResponse(
            response=ai_response,
            context_used=bool(recent_context.strip() and recent_context != "No recent activity data available.")
        )
        
    except Exception as e:
        logger.error(f"Error in AI chat: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get AI response: {str(e)}")

@router.get("/chat/health")
async def check_ai_health(session: AsyncSession = Depends(get_session)):
    """
    Check if the AI service is properly configured.
    """
    try:
        api_key = await get_gemini_api_key(session)
        return {
            "configured": bool(api_key),
            "model": "gemini/gemini-flash-latest"
        }
    except Exception:
        return {
            "configured": False,
            "model": None
        }
