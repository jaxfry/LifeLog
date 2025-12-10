import os
from datetime import datetime, timedelta, timezone
from typing import Optional

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
from app.models.data import Timeline, DailySummary, RawLog, DailyChapter, Event
from app.models.files import FileAttachment
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

async def get_app_usage_stats(session: AsyncSession, days: int = 7, user_timezone: str = "UTC", start_date: Optional[datetime] = None, end_date: Optional[datetime] = None) -> dict:
    """
    Aggregate application usage statistics from raw events.
    Returns a dictionary with app names as keys and total duration in seconds as values.
    
    Args:
        session: Database session
        days: Number of days to look back (used if start_date/end_date not provided)
        user_timezone: User's timezone
        start_date: Optional start date for filtering (UTC)
        end_date: Optional end date for filtering (UTC)
    """
    if end_date is None:
        end_date = datetime.now(timezone.utc).replace(tzinfo=None)
    if start_date is None:
        start_date = end_date - timedelta(days=days)
    
    # Get all app_usage events in the time range
    event_query = select(Event).where(
        Event.type == "app_usage",
        Event.created_at >= start_date,
        Event.created_at <= end_date,
        Event.is_superseded == False
    )
    
    result = await session.execute(event_query)
    events = result.scalars().all()
    
    # Aggregate by app name
    app_durations = {}
    for event in events:
        app_name = event.data.get("app", "Unknown")
        duration = event.data.get("duration", 0)
        
        if app_name in app_durations:
            app_durations[app_name] += duration
        else:
            app_durations[app_name] = duration
    
    return app_durations

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
    
    # Get app usage statistics
    app_usage = await get_app_usage_stats(session, days, user_timezone)
    
    # Build context string
    context_parts = []
    
    if summaries:
        context_parts.append("# Recent Daily Summaries")
        for summary in summaries:
            context_parts.append(f"\n## {summary.date.strftime('%Y-%m-%d')}")
            context_parts.append(summary.summary_text)
            if summary.key_activities:
                context_parts.append(f"Key Activities: {', '.join(summary.key_activities)}")
    
    # Add app usage statistics
    if app_usage:
        context_parts.append(f"\n# Application Usage Statistics (Past {days} days)")
        # Sort by duration descending
        sorted_apps = sorted(app_usage.items(), key=lambda x: x[1], reverse=True)
        for app_name, total_seconds in sorted_apps[:20]:  # Top 20 apps
            hours = total_seconds / 3600
            minutes = (total_seconds % 3600) / 60
            if hours >= 1:
                context_parts.append(f"- {app_name}: {hours:.1f} hours")
            else:
                context_parts.append(f"- {app_name}: {minutes:.0f} minutes")
    
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
            
            # Search Files
            stmt_files = select(FileAttachment).where(FileAttachment.embedding.is_not(None)).order_by(FileAttachment.embedding.l2_distance(embedding)).limit(5)
            result_files = await session.execute(stmt_files)
            files = result_files.scalars().all()
            
            parts = []
            if chapters:
                parts.append("## Relevant Historical Chapters")
                for c in chapters:
                    parts.append(f"- {c.date.date()} {c.title}: {c.summary}")
            
            if files:
                parts.append("## Relevant Documents/Files")
                for f in files:
                    parts.append(f"- {f.filename} ({f.category}): {f.description or 'No description'}")
                    if f.ai_metadata and 'summary' in f.ai_metadata:
                        parts.append(f"  Summary: {f.ai_metadata['summary']}")
            
            if timeline_entries:
                parts.append("## Relevant Historical Activities")
                for t in timeline_entries:
                    # Convert UTC to user's local time for display
                    local_start = t.start_time.replace(tzinfo=timezone.utc).astimezone(tz)
                    local_end = t.end_time.replace(tzinfo=timezone.utc).astimezone(tz)
                    parts.append(f"- {local_start.strftime('%Y-%m-%d %H:%M')} to {local_end.strftime('%H:%M')}: {t.activity} ({t.notes})")
            
            vector_context = "\n".join(parts)

        # Build the system prompt
        system_prompt = f"""You are LifeLog AI, an intelligent assistant that helps users understand and analyze their personal activity data.

You have access to the user's recent activity timeline, daily summaries, application usage statistics, and semantically relevant historical data. Use this information to provide insightful, personalized responses.

When the user asks questions about their activities, productivity, or patterns, reference specific data from their timeline and application usage statistics.

**Important Guidelines for Application Usage:**
- Application names in the "Application Usage Statistics" section represent the ACTUAL time spent in each application
- When a user asks about time spent on activities (e.g., "How much anime have I watched?"), ALWAYS check the application usage statistics first
- Look for applications that might be related to the activity:
  * "Hayase" is a media player application used for watching anime/videos
  * Video players (VLC, mpv, MPlayer, etc.) might indicate video watching
  * Browsers combined with video-related URLs indicate streaming
  * Applications with anime-related titles or content
- The application usage statistics are more accurate than timeline summaries for calculating exact time spent
- Always cite the specific applications and their durations when answering time-based questions
- Sum up all relevant application usage to provide accurate totals
- If an application name seems related to the user's query, include it in your answer

**Example Analysis:**
If the user asks "How much anime have I watched?", you should:
1. Look for "Hayase" (known media player) in Application Usage Statistics
2. Look for other video players or anime-related applications
3. Check timeline entries for anime-related activities
4. Sum all relevant durations and provide a total

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
