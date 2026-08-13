
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from app.core.logger import get_logger
from app.models.config import Prompt

logger = get_logger(__name__)

DEFAULT_PROMPTS: dict[str, str] = {
    "timeline_generation": (
        "You are a personal timeline generator. Given a sequence of computer "
        "activity events, describe concisely what the user was doing.\n\n"
        "Events:\n{events}\n\n"
        "Generate a brief timeline entry (1-3 sentences) describing this "
        "activity session. Include what they worked on and any notable details."
    ),
    "daily_summary": (
        "You are a personal daily summary generator. Given the day's "
        "timeline entries, summarize what the user did today.\n\n"
        "Date: {logical_date}\nTimeline entries:\n{timeline_entries}\n\n"
        "Generate a 2-4 sentence summary covering overall activities, "
        "key focus areas, and productivity insights."
    ),
}


async def get_prompt(db_session: AsyncSession, name: str) -> str | None:
    statement = (
        select(Prompt)
        .where(Prompt.name == name)
        .where(Prompt.is_active == True)
        .order_by(Prompt.version.desc())
    )
    result = await db_session.execute(statement)
    prompt = result.scalars().first()
    if prompt:
        return prompt.template
    return DEFAULT_PROMPTS.get(name)


def render_prompt(template: str, **kwargs) -> str:
    return template.format(**kwargs)


async def seed_default_prompts(db_session: AsyncSession) -> int:
    seeded = 0
    for name, template in DEFAULT_PROMPTS.items():
        statement = select(Prompt).where(Prompt.name == name).where(Prompt.is_active == True)
        result = await db_session.execute(statement)
        existing = result.scalars().first()
        if existing:
            continue
        prompt = Prompt(name=name, template=template, version=1, is_active=True)
        db_session.add(prompt)
        seeded += 1
    if seeded:
        await db_session.commit()
        logger.info("Seeded %d default prompts", seeded)
    return seeded
