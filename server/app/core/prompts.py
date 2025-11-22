"""
This file contains all the LLM prompts used in the LifeLog application's
Data Processing Service.
"""
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select
from app.models.config import Prompt
from app.core.logger import get_logger

# --- Timeline Enrichment Prompts ---

DEFAULT_TIMELINE_ENRICHMENT_SYSTEM_PROMPT = """
You are a timeline analysis AI. Your task is to convert a log of raw computer events from {day_iso} into a structured JSON timeline.

**Output Requirements:**
- A single, valid JSON array of objects.
- Adhere strictly to this schema for each object: {schema_description}
- Be as concise as possible to reduce token count.

**Instructions:**
1.  **Group Events:** Group related consecutive events into meaningful blocks (5-30 mins). Process events in order. A major context switch begins a new block.
2.  **Set Timestamps:** `start` is the start_time of the first event; `end` is the end_time of the last. No overlaps. Use ISO 8601 format (YYYY-MM-DDTHH:MM:SS±HH:MM).
3.  **Define Activity:** Use a short verb phrase (max 6 words) for the `activity` field (e.g., "Debugging payment API" not "Using VS Code").
4.  **Write Notes:** In 1-2 sentences, summarize the activity in the `notes` field. Pull specific details (filenames, PR numbers, URLs) from the event data. For idle time, use "Device idle or user away."
5.  **Handle Gaps:** Fill gaps >15 minutes with an "Idle / Away" activity.
6.  **Empty Input:** If the event table is empty, return an empty JSON array `[]`.

**Event Data for {day_iso}:**
{events_json}

**JSON Output (single array, no comments, no trailing commas):**
"""

# --- Daily Summary Prompt ---

DEFAULT_DAILY_SUMMARY_PROMPT = """
You are a personal biographer AI. Your task is to summarize a user's day based on their timeline of activities.

**Input:**
Date: {date_str}
Timeline Entries:
{timeline_json}

**Output Requirements:**
Return a valid JSON object with the following fields:
- `summary_text`: A single, well-written paragraph (3-5 sentences) narrating the day's flow. Focus on what was achieved, not just a list of tasks.
- `key_activities`: A list of 3-5 short bullet points highlighting the major accomplishments or clusters of activity.
- `productivity_score`: An integer from 1-10 estimating focus and output based on the activities (1=Lazy, 10=Hyper-productive).
- `mood`: A one-word adjective inferring the likely mood (e.g., "Focused", "Scattered", "Relaxed", "Intense").

**Instructions:**
- Ignore minor gaps or short idle periods.
- Group related activities (e.g., "Coding in VS Code" and "Reading Documentation" are part of the same "Development" block).
- Be objective but engaging.

**JSON Output:**
"""

logger = get_logger(__name__)

async def get_system_prompt(db: AsyncSession, name: str = "timeline_enrichment") -> str:
    """
    Retrieves the active system prompt from the database.
    If not found, creates it using the default.
    """
    statement = select(Prompt).where(Prompt.name == name, Prompt.is_active == True).order_by(Prompt.version.desc())
    result = await db.execute(statement)
    prompt = result.scalars().first()
    
    if prompt:
        return prompt.template
        
    # Create default if missing
    logger.info(f"Prompt '{name}' not found. Creating default.")
    new_prompt = Prompt(
        name=name,
        template=DEFAULT_TIMELINE_ENRICHMENT_SYSTEM_PROMPT,
        version=1,
        is_active=True
    )
    db.add(new_prompt)
    await db.commit()
    return new_prompt.template

async def get_daily_summary_prompt(db: AsyncSession) -> str:
    name = "daily_summary"
    statement = select(Prompt).where(Prompt.name == name, Prompt.is_active == True).order_by(Prompt.version.desc())
    result = await db.execute(statement)
    prompt = result.scalars().first()
    
    if prompt:
        return prompt.template
        
    logger.info(f"Prompt '{name}' not found. Creating default.")
    new_prompt = Prompt(
        name=name,
        template=DEFAULT_DAILY_SUMMARY_PROMPT,
        version=1,
        is_active=True
    )
    db.add(new_prompt)
    await db.commit()
    return new_prompt.template

