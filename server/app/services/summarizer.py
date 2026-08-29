import hashlib
import json
import re
import uuid
from datetime import UTC, datetime
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from app.core.logger import get_logger
from app.core.utils.time import to_local_time
from app.models.captures import Capture
from app.models.processing import DailySummary, TimelineEntry
from app.services.ai import call_llm
from app.services.cache import _cache_key
from app.services.model_router import ModelRole
from app.services.prompts import get_prompt, render_prompt
from app.services.retrieval import upsert_search_document

logger = get_logger(__name__)


async def generate_daily_summary(
    db_session: AsyncSession,
    logical_date: str,
    owner_user_id: uuid.UUID | None = None,
    force: bool = False,
) -> DailySummary:
    existing = (
        await db_session.execute(
            select(DailySummary).where(
                DailySummary.owner_user_id == owner_user_id,
                DailySummary.logical_date == logical_date,
            )
        )
    ).scalar_one_or_none()
    if existing and existing.status == "completed" and not force:
        logger.info("Daily summary for %s already exists, skipping", logical_date)
        await _index_summary(db_session, existing)
        await db_session.commit()
        return existing

    stmt = (
        select(TimelineEntry)
        .where(TimelineEntry.owner_user_id == owner_user_id)
        .where(TimelineEntry.logical_date == logical_date)
        .order_by(TimelineEntry.start_time.asc())
    )
    result = await db_session.execute(stmt)
    entries = result.scalars().all()

    if not entries:
        logger.info("No timeline entries for %s to summarize", logical_date)
        if existing:
            return existing
        summary = DailySummary(
            owner_user_id=owner_user_id,
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
    captures = (
        await db_session.execute(
            select(Capture).where(
                Capture.user_id == owner_user_id,
                Capture.status.in_(("ready", "partially_ready", "awaiting_review")),
                Capture.text_content.is_not(None),
            )
        )
    ).scalars().all()
    day_captures = [
        capture for capture in captures if _capture_logical_date(capture) == logical_date
    ]
    captures_text = _format_captures(day_captures)
    template = await get_prompt(db_session, "daily_summary")
    if not template:
        logger.error("No daily_summary prompt found")
        template = "Summarize these activities for {logical_date}:\n{timeline_entries}"

    user_prompt = render_prompt(
        template,
        logical_date=logical_date,
        timeline_entries=entries_text,
    )
    user_prompt += f"""

Additional first-person captures and notes:
{captures_text or "(none)"}

Return one JSON object with exactly these fields:
{{
  "summary": "2-4 factual sentences describing the day's arc",
  "key_activities": ["3-6 concise, distinct activities"],
  "open_loops": ["unfinished work, follow-ups, tentative deadlines, or reminders"],
  "productivity_score": null,
  "mood": null,
  "inferences": ["interpretations not directly established by evidence"]
}}
Captures are direct user evidence and may correct an activity trace. Never say
something was completed merely because an app or document was open. Preserve
uncertainty words such as “probably” and “check”. Keep unsupported judgments out
of the summary and place them in inferences. Return JSON only.
"""

    cache_data = {
        "logical_date": logical_date,
        "owner_user_id": str(owner_user_id) if owner_user_id else None,
        "entries_hash": hashlib.sha256(entries_text.encode()).hexdigest(),
        "captures_hash": hashlib.sha256(captures_text.encode()).hexdigest(),
        "output_contract": 2,
    }
    cache_key = _cache_key("summary", cache_data)

    try:
        content = await call_llm(
            db_session=db_session,
            system_prompt="You are a personal daily summarizer. Be concise and insightful.",
            user_prompt=user_prompt,
            cache_key=cache_key,
            session_context={
                "operation": "daily_summary",
                "owner_user_id": owner_user_id,
            },
            # Reasoning models count hidden reasoning against this budget. A full-day
            # synthesis needs more headroom than a short timeline description.
            max_tokens=4096,
            response_format={"type": "json_object"},
            role=ModelRole.SUMMARIZATION,
        )
    except RuntimeError:
        logger.error("Failed to generate daily summary for %s", logical_date)
        if existing:
            existing.status = "failed"
            db_session.add(existing)
            await db_session.commit()
            return existing
        summary = DailySummary(
            owner_user_id=owner_user_id,
            logical_date=logical_date,
            summary_text="Summary generation failed.",
            status="failed",
        )
        db_session.add(summary)
        await db_session.commit()
        return summary

    structured = _parse_summary_output(
        content,
        entries,
        evidence_text=f"{entries_text}\n{captures_text}",
    )

    if existing:
        existing.summary_text = structured["summary"]
        existing.key_activities = structured["key_activities"]
        existing.open_loops = structured["open_loops"]
        existing.productivity_score = structured["productivity_score"]
        existing.mood = structured["mood"]
        existing.inferences = structured["inferences"]
        existing.status = "completed"
        existing.updated_at = datetime.now(UTC).replace(tzinfo=None)
        db_session.add(existing)
    else:
        summary = DailySummary(
            owner_user_id=owner_user_id,
            logical_date=logical_date,
            summary_text=structured["summary"],
            key_activities=structured["key_activities"],
            open_loops=structured["open_loops"],
            productivity_score=structured["productivity_score"],
            mood=structured["mood"],
            inferences=structured["inferences"],
            status="completed",
        )
        db_session.add(summary)

    current = existing or summary
    for entry in entries:
        entry.is_summarized = True
        db_session.add(entry)
    await db_session.flush()
    await _index_summary(db_session, current)
    await db_session.commit()
    logger.info("Generated daily summary for %s", logical_date)
    return current


async def _index_summary(db_session: AsyncSession, summary: DailySummary) -> None:
    await upsert_search_document(
        db_session,
        source_type="daily_summary",
        source_id=summary.id,
        title=summary.logical_date,
        content="\n".join(
            [
                summary.summary_text,
                *(summary.key_activities or []),
                *(f"Open loop: {item}" for item in (summary.open_loops or [])),
            ]
        ),
        logical_date=summary.logical_date,
        metadata={
            "owner_user_id": str(summary.owner_user_id) if summary.owner_user_id else None,
            "status": summary.status,
            "open_loops": summary.open_loops or [],
            "inferences": summary.inferences or [],
        },
    )


async def update_summaries_for_range(
    db_session: AsyncSession,
    start_date: str,
    end_date: str,
    owner_user_id: uuid.UUID,
    force: bool = False,
) -> int:
    stmt = (
        select(TimelineEntry.logical_date)
        .where(TimelineEntry.owner_user_id == owner_user_id)
        .where(TimelineEntry.logical_date >= start_date)
        .where(TimelineEntry.logical_date <= end_date)
        .where(TimelineEntry.is_summarized == True)
        .distinct()
    )
    result = await db_session.execute(stmt)
    dates = result.scalars().all()

    updated = 0
    for logical_date in dates:
        await generate_daily_summary(
            db_session,
            logical_date,
            owner_user_id=owner_user_id,
            force=force,
        )
        updated += 1
    return updated


def _format_entries(entries: list[TimelineEntry]) -> str:
    lines = []
    for e in entries:
        start = to_local_time(e.start_time, e.timezone).strftime("%H:%M")
        end = to_local_time(e.end_time, e.timezone).strftime("%H:%M")
        cat = f" ({e.category})" if e.category else ""
        evidence = f" Evidence: {len(e.evidence_event_ids or [])} records."
        inference = f" Inferences: {e.inferences}." if e.inferences else ""
        lines.append(
            f"  [{start}-{end}]{cat} {e.activity}: {e.notes or ''}{evidence}{inference}"
        )
    return "\n".join(lines)


def _capture_logical_date(capture: Capture) -> str:
    timezone_name = capture.timezone or "UTC"
    try:
        timezone = ZoneInfo(timezone_name)
    except ZoneInfoNotFoundError:
        timezone = ZoneInfo("UTC")
    captured_at = capture.captured_at.replace(tzinfo=UTC)
    return captured_at.astimezone(timezone).strftime("%Y-%m-%d")


def _format_captures(captures: list[Capture]) -> str:
    lines = []
    for index, capture in enumerate(sorted(captures, key=lambda item: item.captured_at), start=1):
        hints = f" context={capture.context_hints}" if capture.context_hints else ""
        lines.append(
            f"  [N{index}] intent={capture.intent or 'unspecified'}{hints}: "
            f"{capture.text_content}"
        )
    return "\n".join(lines)


def _parse_summary_output(
    content: str,
    entries: list[TimelineEntry],
    evidence_text: str = "",
) -> dict:
    fallback = {
        "summary": content.strip(),
        "key_activities": [entry.activity for entry in entries if entry.activity][:6],
        "open_loops": [],
        "productivity_score": None,
        "mood": None,
        "inferences": [],
    }
    try:
        cleaned = re.sub(r"^```(?:json)?\s*|\s*```$", "", content.strip())
        value = json.loads(cleaned)
        if not isinstance(value, dict):
            return fallback
    except (json.JSONDecodeError, TypeError):
        return fallback
    score = value.get("productivity_score")
    if not isinstance(score, int) or not 1 <= score <= 10:
        score = None
    return {
        "summary": _sanitize_summary_claims(
            str(value.get("summary") or fallback["summary"]).strip(),
            evidence_text,
        ),
        "key_activities": [
            _sanitize_completion_claim(str(item).strip()[:180], evidence_text)
            for item in value.get("key_activities", [])
            if str(item).strip()
        ][:6],
        "open_loops": [
            str(item).strip()[:240]
            for item in value.get("open_loops", [])
            if str(item).strip()
        ][:10],
        "productivity_score": score,
        "mood": str(value["mood"]).strip()[:60] if value.get("mood") else None,
        "inferences": [
            str(item).strip()[:240]
            for item in value.get("inferences", [])
            if str(item).strip()
        ][:3],
    }


def _sanitize_completion_claim(text: str, evidence_text: str) -> str:
    if re.search(r"\b(completed|finished)\b", evidence_text, flags=re.I):
        return text
    def replacement(match: re.Match) -> str:
        phrase = "worked on"
        return phrase.capitalize() if match.group(0)[0].isupper() else phrase

    text = re.sub(r"\bcompleted\b", replacement, text, flags=re.I)
    return re.sub(r"\bfinished\b", replacement, text, flags=re.I)


def _sanitize_summary_claims(text: str, evidence_text: str) -> str:
    text = _sanitize_completion_claim(text, evidence_text)
    if not re.search(r"\bproductive|productivity\b", evidence_text, flags=re.I):
        sentences = re.split(r"(?<=[.!?])\s+", text)
        text = " ".join(
            sentence
            for sentence in sentences
            if not re.search(r"\bproductive|productivity\b", sentence, flags=re.I)
        )
    return text.strip()
