import uuid
from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from app.core.logger import get_logger
from app.models.processing import DailySummary, TimelineEntry
from app.services.ai import call_llm
from app.services.cache import _cache_key
from app.services.prompts import get_prompt, render_prompt
from app.services.retrieval import upsert_search_document

logger = get_logger(__name__)


async def generate_daily_summary(
    db_session: AsyncSession,
    logical_date: str,
    force: bool = False,
) -> DailySummary:
    existing = await db_session.get(DailySummary, logical_date)
    if existing and existing.status == "completed" and not force:
        logger.info("Daily summary for %s already exists, skipping", logical_date)
        await _index_summary(db_session, existing)
        await db_session.commit()
        return existing

    stmt = (
        select(TimelineEntry)
        .where(TimelineEntry.logical_date == logical_date)
        .where(TimelineEntry.is_summarized == True)
        .order_by(TimelineEntry.start_time.asc())
    )
    result = await db_session.execute(stmt)
    entries = result.scalars().all()

    if not entries:
        logger.info("No timeline entries for %s to summarize", logical_date)
        if existing:
            return existing
        summary = DailySummary(
            logical_date=logical_date,
            summary_text="No activities recorded.",
            status="completed",
        )
        db_session.add(summary)
        await db_session.flush()
        await _index_summary(db_session, summary)
        await db_session.commit()
        return summary

    entries_text = _format_entries(entries)
    template = await get_prompt(db_session, "daily_summary")
    if not template:
        logger.error("No daily_summary prompt found")
        template = "Summarize these activities for {logical_date}:\n{timeline_entries}"

    user_prompt = render_prompt(
        template,
        logical_date=logical_date,
        timeline_entries=entries_text,
    )

    cache_data = {
        "logical_date": logical_date,
        "entries_hash": hash(entries_text),
    }
    cache_key = _cache_key("summary", cache_data)

    try:
        content = await call_llm(
            db_session=db_session,
            system_prompt="You are a personal daily summarizer. Be concise and insightful.",
            user_prompt=user_prompt,
            cache_key=cache_key,
        )
    except RuntimeError:
        logger.error("Failed to generate daily summary for %s", logical_date)
        if existing:
            existing.status = "failed"
            db_session.add(existing)
            await db_session.commit()
            return existing
        summary = DailySummary(
            logical_date=logical_date,
            summary_text="Summary generation failed.",
            status="failed",
        )
        db_session.add(summary)
        await db_session.commit()
        return summary

    activities = [e.activity for e in entries if e.activity]

    if existing:
        existing.summary_text = content.strip()
        existing.key_activities = activities
        existing.status = "completed"
        existing.updated_at = datetime.now(UTC).replace(tzinfo=None)
        db_session.add(existing)
    else:
        summary = DailySummary(
            logical_date=logical_date,
            summary_text=content.strip(),
            key_activities=activities,
            status="completed",
        )
        db_session.add(summary)

    current = existing or summary
    await db_session.flush()
    await _index_summary(db_session, current)
    await db_session.commit()
    logger.info("Generated daily summary for %s", logical_date)
    return current


async def _index_summary(db_session: AsyncSession, summary: DailySummary) -> None:
    await upsert_search_document(
        db_session,
        source_type="daily_summary",
        source_id=uuid.uuid5(
            uuid.NAMESPACE_URL,
            f"lifelog:daily-summary:{summary.logical_date}",
        ),
        title=summary.logical_date,
        content=summary.summary_text,
        logical_date=summary.logical_date,
        metadata={"status": summary.status},
    )


async def update_summaries_for_range(
    db_session: AsyncSession,
    start_date: str,
    end_date: str,
    force: bool = False,
) -> int:
    stmt = (
        select(TimelineEntry.logical_date)
        .where(TimelineEntry.logical_date >= start_date)
        .where(TimelineEntry.logical_date <= end_date)
        .where(TimelineEntry.is_summarized == True)
        .distinct()
    )
    result = await db_session.execute(stmt)
    dates = result.scalars().all()

    updated = 0
    for logical_date in dates:
        await generate_daily_summary(db_session, logical_date, force=force)
        updated += 1
    return updated


def _format_entries(entries: list[TimelineEntry]) -> str:
    lines = []
    for e in entries:
        start = e.start_time.strftime("%H:%M")
        end = e.end_time.strftime("%H:%M")
        cat = f" ({e.category})" if e.category else ""
        lines.append(f"  [{start}-{end}]{cat} {e.activity}")
    return "\n".join(lines)
