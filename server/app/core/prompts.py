"""
This file contains all the LLM prompts used in the LifeLog application's
Data Processing Service.
"""
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select, col
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
1.  **Group Events by Intent:** Group events into high-level activities based on the user's *intent* (e.g., "Coding LifeLog", "Researching AI"). Blocks should be as long as possible (up to several hours) if the general activity is consistent.
2.  **Maximize Signal-to-Noise:** Focus on the *signal* (major accomplishments, long periods of work) and filter out the *noise* (brief window switches, short distractions, checking email for < 5 mins).
3.  **Ignore Interruptions:** Ignore brief interruptions (e.g., changing music, quick Google searches, 1-2 minute gaps) if the user returns to the main task. Do not create separate blocks for these.
4.  **Context Switching:** Only start a new block if there is a *significant* shift in the user's primary goal (e.g., switching from "Work" to "Gaming", or "Writing" to "Meeting"). Do not split based on application switching alone.
5.  **Set Timestamps:** `start` is the start_time of the first event in the block; `end` is the end_time of the last. No overlaps. Use ISO 8601 format (YYYY-MM-DDTHH:MM:SS±HH:MM).
6.  **Define Activity:** Use a descriptive verb phrase (max 8 words) for the `activity` field (e.g., "Refactoring authentication module in VS Code").
7.  **Write Notes:** In 1-2 sentences, summarize the activity in the `notes` field. Mention key tools and topics.
    - **Drop Micro-Details:** Do not mention sub-minute actions (e.g., "brief 18-second switch") unless critical.
    - **Infer Intent:** Try to explain *why* the user was doing this (e.g., "...in an attempt to fix timeline quality issues").
8.  **Handle Gaps:** Fill gaps >15 minutes with an "Idle / Away" activity.
9.  **Empty Input:** If the event table is empty, return an empty JSON array `[]`.

**Event Data for {day_iso}:**
{events_json}

**JSON Output (single array, no comments, no trailing commas):**
"""

# --- Daily Summary Prompt ---

DEFAULT_DAILY_SUMMARY_PROMPT = """
You are a personal biographer AI. Your task is to summarize a user's day based on their timeline of activities.

**Input:**
Date: {date_str}
Timezone: {user_timezone}
Current Time: {current_time} (local time)
Timeline Entries (times in local timezone):
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
- **CRITICAL:** If the "Current Time" is before the end of the day (e.g., it is 5 PM), summarize ONLY what has happened so far. DO NOT hallucinate or predict the end of the day. Use phrases like "So far today..." or "The day began with...". Do not say "The day ended with..." if the day hasn't ended.

**JSON Output:**
"""

# --- Chapter Summary Prompt ---

DEFAULT_CHAPTER_SUMMARY_PROMPT = """
You are a high-level summarizer. Your task is to group granular timeline entries into 3-4 logical "Chapters" with high-level titles.

**Input:**
Date: {date_str}
Timezone: {user_timezone}
Timeline Entries (times in local timezone):
{timeline_json}

**Output Requirements:**
Return a valid JSON array of objects, where each object represents a Chapter:
- `title`: A high-level title for the chapter (e.g., "Morning Deep Work", "Afternoon Research").
- `summary`: A 1-2 sentence summary of what happened in this chapter.
- `start_time`: The ISO 8601 start time of the chapter in the same timezone as input (use the earliest entry's start time in this chapter).
- `end_time`: The ISO 8601 end time of the chapter in the same timezone as input (use the latest entry's end time in this chapter).
- `category`: A high-level category (e.g., "Work", "Personal", "Health").
- `tags`: A list of 3-5 relevant tags.

**Instructions:**
- Group the provided granular entries into 3-4 logical chapters.
- The chapters should cover the entire time range of the input entries.
- Strip away details and focus on macro chunks.
- Use the EXACT timestamps from the input entries for start_time and end_time - DO NOT modify or fabricate times.

**JSON Output:**
"""

logger = get_logger(__name__)

async def get_system_prompt(db: AsyncSession, name: str = "timeline_enrichment") -> str:
    """
    Retrieves the active system prompt from the database.
    If not found, creates it using the default.
    """
    statement = select(Prompt).where(Prompt.name == name, Prompt.is_active == True).order_by(col(Prompt.version).desc())
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
    statement = select(Prompt).where(Prompt.name == name, Prompt.is_active == True).order_by(col(Prompt.version).desc())
    result = await db.execute(statement)
    prompt = result.scalars().first()
    
    if prompt:
        # Check if prompt needs update (missing user_timezone for local time support)
        if "{user_timezone}" not in prompt.template:
             logger.info(f"Upgrading prompt '{name}' to include user_timezone for local time support.")
             new_prompt = Prompt(
                name=name,
                template=DEFAULT_DAILY_SUMMARY_PROMPT,
                version=prompt.version + 1,
                is_active=True
             )
             db.add(new_prompt)
             await db.commit()
             return new_prompt.template
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

async def get_chapter_summary_prompt(db: AsyncSession) -> str:
    name = "chapter_summary"
    statement = select(Prompt).where(Prompt.name == name, Prompt.is_active == True).order_by(col(Prompt.version).desc())
    result = await db.execute(statement)
    prompt = result.scalars().first()
    
    if prompt:
        # Check if prompt needs update (missing user_timezone for local time support)
        if "{user_timezone}" not in prompt.template:
             logger.info(f"Upgrading prompt '{name}' to include user_timezone for local time support.")
             new_prompt = Prompt(
                name=name,
                template=DEFAULT_CHAPTER_SUMMARY_PROMPT,
                version=prompt.version + 1,
                is_active=True
             )
             db.add(new_prompt)
             await db.commit()
             return new_prompt.template
        return prompt.template
        
    logger.info(f"Prompt '{name}' not found. Creating default.")
    new_prompt = Prompt(
        name=name,
        template=DEFAULT_CHAPTER_SUMMARY_PROMPT,
        version=1,
        is_active=True
    )
    db.add(new_prompt)
    await db.commit()
    return new_prompt.template

