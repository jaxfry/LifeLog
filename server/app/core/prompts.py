"""
This file contains all the LLM prompts used in the LifeLog application's
Data Processing Service.
"""
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select
from app.models.config import Prompt

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
    print(f"Prompt '{name}' not found. Creating default.")
    new_prompt = Prompt(
        name=name,
        template=DEFAULT_TIMELINE_ENRICHMENT_SYSTEM_PROMPT,
        version=1,
        is_active=True
    )
    db.add(new_prompt)
    await db.commit()
    return new_prompt.template

