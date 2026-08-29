import hashlib
import json
import re
from collections import Counter, defaultdict
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select, update

from app.core.logger import get_logger
from app.core.utils.time import to_local_time
from app.models.ingest import Event, RawLog
from app.models.processing import Session, TimelineEntry
from app.models.retrieval import SearchDocument
from app.services.ai import call_llm
from app.services.cache import _cache_key
from app.services.model_router import ModelRole
from app.services.processing import get_sessions_ready_for_ai
from app.services.prompts import get_prompt, render_prompt
from app.services.retrieval import upsert_search_document

logger = get_logger(__name__)


async def generate_timeline_for_session(
    db_session: AsyncSession,
    session_obj: Session,
) -> TimelineEntry | None:
    claimed = (
        await db_session.execute(
            update(Session)
            .where(
                Session.id == session_obj.id,
                Session.status == "pending",
                Session.processing_status == "ready",
            )
            .values(status="processing", processing_status="processing")
            .returning(Session.id)
        )
    ).scalar_one_or_none()
    if claimed is None:
        await db_session.rollback()
        return None
    await db_session.commit()
    session_obj = await db_session.get(Session, session_obj.id)
    if session_obj is None:
        return None

    events_stmt = (
        select(Event, RawLog.client_timezone)
        .join(RawLog, RawLog.id == Event.source_log_id)
        .where(Event.session_id == session_obj.id)
        .where(Event.is_superseded == False)
        .order_by(Event.start_time.asc())
    )
    result = await db_session.execute(events_stmt)
    event_rows = result.all()
    events = [event for event, _timezone in event_rows]
    event_timezones = {
        event.id: timezone or "UTC" for event, timezone in event_rows
    }

    if not events:
        session_obj.status = "completed"
        session_obj.processing_status = "completed"
        db_session.add(session_obj)
        await db_session.commit()
        return None
    timeline_timezone = Counter(event_timezones.values()).most_common(1)[0][0]

    events_text, evidence_map = _build_evidence_bundle(events, event_timezones)
    template = await get_prompt(db_session, "timeline_generation")
    if not template:
        logger.error("No timeline_generation prompt found")
        return None

    user_prompt = render_prompt(template, events=events_text) + """

Return one JSON object with exactly these fields:
{
  "title": "specific activity title, at most 8 words",
  "summary": "1-3 factual sentences",
  "category": "work|school|communication|life_admin|creative|health|leisure|travel|mixed|other",
  "tags": ["short", "specific"],
  "evidence_refs": ["E1", "E2"],
  "confidence": 0.0,
  "inferences": ["at most 2 uncertain claims that materially aid understanding"],
  "concepts": [{"name": "Calculus 12", "type": "course", "evidence_refs": ["E1"]}]
}
Use only supplied evidence. Do not claim that work was completed or that progress
was significant unless the evidence explicitly establishes it. Keep observations
in summary and uncertain interpretations in inferences. Concept type must be one
of course, assignment, project, person, organization, topic, place, media, or
activity. Do not emit the same concept under multiple types. Evidence refs belong
only in evidence_refs, never in title or summary. Return JSON only.
"""

    cache_data = {
        "session_id": str(session_obj.id),
        "events_hash": hashlib.sha256(events_text.encode()).hexdigest(),
        "output_contract": 2,
    }
    cache_key = _cache_key("timeline", cache_data)

    try:
        content = await call_llm(
            db_session=db_session,
            system_prompt="You are a personal timeline generator. Be concise and factual.",
            user_prompt=user_prompt,
            cache_key=cache_key,
            session_context={
                "operation": "timeline_generation",
                "owner_user_id": session_obj.owner_user_id,
            },
            response_format={"type": "json_object"},
            max_tokens=4096,
            role=ModelRole.SUMMARIZATION,
        )
    except RuntimeError:
        logger.error("Failed to generate timeline for session %s", session_obj.id)
        session_obj.status = "failed"
        session_obj.processing_status = "failed"
        session_obj.retry_count += 1
        db_session.add(session_obj)
        await db_session.commit()
        return None

    structured = _parse_timeline_output(content)
    if structured["is_structured"] and (
        not structured["summary"] or not structured["evidence_refs"]
    ):
        logger.error("Timeline output for session %s lacked summary or evidence", session_obj.id)
        session_obj.status = "failed"
        session_obj.processing_status = "failed"
        session_obj.retry_count += 1
        db_session.add(session_obj)
        await db_session.commit()
        return None
    evidence_refs = [
        ref for ref in structured["evidence_refs"] if ref in evidence_map
    ]
    evidence_ids = [str(evidence_map[ref]) for ref in evidence_refs]
    evidence_uuid_ids = [evidence_map[ref] for ref in evidence_refs]
    owner_rows = (
        await db_session.execute(
            select(SearchDocument.metadata_).where(
                SearchDocument.source_type == "event",
                SearchDocument.source_id.in_(evidence_uuid_ids),
            )
        )
    ).scalars().all()
    owners = {
        row.get("owner_user_id")
        for row in owner_rows
        if row.get("owner_user_id") is not None
    }
    owner_user_id = owners.pop() if len(owners) == 1 else None
    entry = TimelineEntry(
        owner_user_id=session_obj.owner_user_id,
        session_id=session_obj.id,
        start_time=session_obj.start_time,
        end_time=session_obj.end_time,
        activity=structured["title"],
        notes=structured["summary"],
        category=structured["category"],
        tags=structured["tags"],
        evidence_event_ids=evidence_ids,
        confidence=structured["confidence"],
        inferences=structured["inferences"],
        logical_date=session_obj.logical_date,
        timezone=timeline_timezone,
    )
    db_session.add(entry)
    await db_session.flush()
    await upsert_search_document(
        db_session,
        source_type="timeline",
        source_id=entry.id,
        title=entry.activity,
        content="\n".join(part for part in [entry.activity, entry.notes] if part),
        occurred_at=entry.start_time,
        logical_date=entry.logical_date,
        metadata={
            "category": entry.category,
            "tags": entry.tags or [],
            "evidence_event_ids": evidence_ids,
            "confidence": entry.confidence,
            "owner_user_id": (
                str(session_obj.owner_user_id)
                if session_obj.owner_user_id is not None
                else owner_user_id
            ),
        },
    )

    await _persist_concepts(
        db_session,
        structured["concepts"],
        evidence_map,
        events,
    )

    session_obj.status = "completed"
    session_obj.processing_status = "completed"
    db_session.add(session_obj)
    await db_session.commit()

    logger.info(
        "Generated timeline entry %s for session %s",
        entry.id,
        session_obj.id,
    )
    return entry


async def process_pending_sessions(
    db_session: AsyncSession,
    limit: int = 10,
) -> int:
    sessions = await get_sessions_ready_for_ai(db_session, limit=limit)
    processed = 0
    for ses in sessions:
        try:
            result = await generate_timeline_for_session(db_session, ses)
            if result:
                processed += 1
        except Exception:
            logger.exception("Failed to process session %s", ses.id)
            ses.status = "failed"
            ses.processing_status = "failed"
            ses.retry_count += 1
            db_session.add(ses)
            await db_session.commit()
    return processed


def _format_events(
    events: list[Event],
    timezones: dict[object, str] | None = None,
) -> str:
    lines = []
    for e in events:
        timezone = (timezones or {}).get(e.id, "UTC")
        start = to_local_time(e.start_time, timezone).strftime("%H:%M")
        end = to_local_time(e.end_time, timezone).strftime("%H:%M") if e.end_time else "?"
        data_summary = _summarize_event_data(e.data)
        lines.append(f"  [{start}-{end}] {e.event_type}: {data_summary}")
    return "\n".join(lines)


def _build_evidence_bundle(
    events: list[Event],
    timezones: dict[object, str] | None = None,
) -> tuple[str, dict[str, object]]:
    """Aggregate noisy focus records into compact, traceable evidence."""
    grouped: dict[tuple[str, str], dict[str, Any]] = defaultdict(
        lambda: {"events": [], "seconds": 0.0}
    )
    for event in events:
        if event.event_type == "device_status":
            continue
        label = _summarize_event_data(event.data).strip()
        if not label:
            continue
        normalized = re.sub(r"\s+", " ", label)
        normalized = re.sub(r"\s*\(Not Responding\)$", "", normalized, flags=re.I)
        key = (event.event_type, normalized.casefold())
        grouped[key]["label"] = normalized
        grouped[key]["events"].append(event)
        grouped[key]["seconds"] += max(
            0.0,
            ((event.end_time or event.start_time) - event.start_time).total_seconds(),
        )

    ranked = sorted(
        grouped.values(),
        key=lambda group: (-group["seconds"], group["events"][0].start_time),
    )[:60]
    ranked.sort(key=lambda group: group["events"][0].start_time)
    lines: list[str] = []
    evidence_map: dict[str, object] = {}
    for index, group in enumerate(ranked, start=1):
        ref = f"E{index}"
        first = min(group["events"], key=lambda event: event.start_time)
        last = max(group["events"], key=lambda event: event.end_time or event.start_time)
        timezone = (timezones or {}).get(first.id, "UTC")
        start = to_local_time(first.start_time, timezone).strftime("%H:%M")
        end = to_local_time(last.end_time or last.start_time, timezone).strftime("%H:%M")
        minutes = max(1, round(group["seconds"] / 60))
        lines.append(
            f"[{ref}] [{start}-{end}] {group['label']} — {minutes} min across "
            f"{len(group['events'])} focus records"
        )
        evidence_map[ref] = first.id
    return "\n".join(lines), evidence_map


def _parse_timeline_output(content: str) -> dict[str, Any]:
    fallback = {
        "title": content.strip(),
        "summary": None,
        "category": "other",
        "tags": [],
        "evidence_refs": [],
        "confidence": 0.7,
        "inferences": [],
        "concepts": [],
        "is_structured": content.lstrip().startswith("{"),
    }
    try:
        cleaned = re.sub(r"^```(?:json)?\s*|\s*```$", "", content.strip())
        value = json.loads(cleaned)
        if not isinstance(value, dict):
            return fallback
    except (json.JSONDecodeError, TypeError):
        return fallback
    tags = [str(tag).strip()[:50] for tag in value.get("tags", []) if str(tag).strip()][:8]
    category = str(value.get("category") or "other").strip().casefold()
    title = str(value.get("title") or "Activity").strip()[:160]
    if title.casefold() in {"activity", "session", "user activity"} and tags:
        title = f"{category.replace('_', ' ').title()}: {', '.join(tags[:3])}"
    summary = re.sub(r"\s*\(?\bE\d+\b\)?", "", str(value.get("summary") or "")).strip() or None
    allowed_categories = {
        "work", "school", "communication", "life_admin", "creative",
        "health", "leisure", "travel", "mixed", "other",
    }
    school_markers = {"calculus", "physics", "essay", "assignment", "derivative", "study"}
    leisure_markers = {"gaming", "music", "reddit", "hades", "voice chat", "friends"}
    tag_text = " ".join(tags).casefold()
    if any(marker in tag_text for marker in school_markers) and any(
        marker in tag_text for marker in leisure_markers
    ):
        category = "mixed"
    return {
        "title": title,
        "summary": summary,
        "category": category if category in allowed_categories else "other",
        "tags": tags,
        "evidence_refs": [str(ref) for ref in value.get("evidence_refs", [])][:20],
        "confidence": min(1.0, max(0.0, float(value.get("confidence", 0.8)))),
        "inferences": [str(item).strip() for item in value.get("inferences", []) if str(item).strip()][:2],
        "concepts": [item for item in value.get("concepts", []) if isinstance(item, dict)][:12],
        "is_structured": True,
    }


async def _persist_concepts(
    session: AsyncSession,
    concepts: list[dict[str, Any]],
    evidence_map: dict[str, object],
    events: list[Event],
) -> None:
    from app.services.extraction import persist_inferred_concepts

    await persist_inferred_concepts(session, concepts, evidence_map, events)


def _summarize_event_data(data: dict) -> str:
    if not data:
        return ""
    title = data.get("title") or data.get("name") or data.get("app") or data.get("url") or ""
    if isinstance(title, str) and title:
        return title
    return str(data)[:120]
