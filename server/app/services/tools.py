"""Deterministic assistant tools owned by the LifeLog base.

Every tool executes base services against durable data; the LLM only selects
tools and arguments and explains the results. Calculations are never
approximated inside a prompt window.
"""

import json
import uuid
from datetime import UTC, datetime, timedelta

from pydantic import BaseModel, Field, ValidationError
from sqlalchemy import func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import col, select

from app.models.captures import Capture
from app.models.claims import ClaimEvidence, MemoryClaim
from app.models.evidence import EvidenceDocument, EvidenceSpan
from app.models.files import Commitment, CommitmentProgress, PlanBlock
from app.models.ingest import Event, RawLog
from app.models.kernel import Entity
from app.models.sources import SourceConnection, SourceRecord
from app.services.context import target_visible
from app.services.inbox import upsert_review_item
from app.services.kernel import aggregate_duration, get_current_entity_by_name, get_entity_graph
from app.services.measurements import aggregate_measurements
from app.services.planning import generate_plan
from app.services.query_planning import plan_query
from app.services.retrieval import retrieve

MAX_TOOLS_PER_CHAT = 3


def _now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def _iso(value: datetime | None) -> str | None:
    return value.isoformat() if value is not None else None


class SearchMemoriesArgs(BaseModel):
    query: str = Field(min_length=1, max_length=2000)
    limit: int = Field(default=10, ge=1, le=30)


class TraverseGraphArgs(BaseModel):
    entity_name: str = Field(min_length=1, max_length=500)
    entity_type: str | None = Field(default=None, max_length=100)
    depth: int = Field(default=2, ge=1, le=3)
    limit: int = Field(default=25, ge=1, le=200)


class CalculateDurationArgs(BaseModel):
    predicate: str | None = Field(default=None, max_length=100)
    entity_type: str | None = Field(default=None, max_length=100)
    entity_name: str | None = Field(default=None, max_length=500)
    occurred_from: datetime | None = None
    occurred_until: datetime | None = None


class AggregateMeasurementsArgs(BaseModel):
    entity_type: str | None = Field(default=None, max_length=100)
    entity_name: str | None = Field(default=None, max_length=500)
    metric: str | None = Field(default=None, max_length=100)
    occurred_from: datetime | None = None
    occurred_until: datetime | None = None


class ListDeadlinesArgs(BaseModel):
    due_from: datetime | None = None
    due_until: datetime | None = None
    limit: int = Field(default=20, ge=1, le=100)


class InspectCommitmentProgressArgs(BaseModel):
    commitment_title: str = Field(min_length=1, max_length=500)


class FindConflictsArgs(BaseModel):
    occurred_from: datetime
    occurred_until: datetime


class GeneratePlanArgs(BaseModel):
    horizon_days: int = Field(default=7, ge=1, le=90)
    daily_capacity_minutes: int = Field(default=120, ge=15, le=1440)
    block_minutes: int = Field(default=45, ge=5, le=1440)


class CompareTimePeriodsArgs(BaseModel):
    entity_type: str | None = Field(default=None, max_length=100)
    entity_name: str | None = Field(default=None, max_length=500)
    predicate: str | None = Field(default=None, max_length=100)
    from_1: datetime
    until_1: datetime
    from_2: datetime
    until_2: datetime


class ResolveSourceHistoryArgs(BaseModel):
    external_key: str = Field(min_length=1, max_length=500)


class ProposeActionArgs(BaseModel):
    summary: str = Field(min_length=1, max_length=1000)
    action: dict = Field(default_factory=dict)
    consequential: bool = False


class PlanQueryArgs(BaseModel):
    question: str = Field(min_length=1, max_length=4000)


class InspectEvidenceArgs(BaseModel):
    source_id: uuid.UUID
    limit: int = Field(default=12, ge=1, le=30)


class InspectClaimHistoryArgs(BaseModel):
    entity_name: str | None = Field(default=None, max_length=500)
    entity_type: str | None = Field(default=None, max_length=100)
    predicate: str | None = Field(default=None, max_length=100)
    known_at: datetime | None = None
    valid_at: datetime | None = None
    limit: int = Field(default=20, ge=1, le=100)


class InspectCoverageArgs(BaseModel):
    occurred_from: datetime
    occurred_until: datetime


TOOL_ARGS: dict[str, type[BaseModel]] = {
    "search_memories": SearchMemoriesArgs,
    "traverse_graph": TraverseGraphArgs,
    "calculate_duration": CalculateDurationArgs,
    "aggregate_measurements": AggregateMeasurementsArgs,
    "list_deadlines": ListDeadlinesArgs,
    "inspect_commitment_progress": InspectCommitmentProgressArgs,
    "find_scheduling_conflicts": FindConflictsArgs,
    "generate_plan": GeneratePlanArgs,
    "compare_time_periods": CompareTimePeriodsArgs,
    "resolve_source_history": ResolveSourceHistoryArgs,
    "propose_action": ProposeActionArgs,
    "plan_query": PlanQueryArgs,
    "inspect_evidence": InspectEvidenceArgs,
    "inspect_claim_history": InspectClaimHistoryArgs,
    "inspect_coverage": InspectCoverageArgs,
}

TOOL_DESCRIPTIONS: dict[str, str] = {
    "search_memories": (
        "Search indexed memories (events, timeline entries, summaries, entities) "
        "relevant to a query."
    ),
    "traverse_graph": (
        "Return current facts around a named entity (its relations, neighbors, "
        "and events), up to depth 3."
    ),
    "calculate_duration": (
        "Total valid-time duration for relations (e.g. predicate 'studied_for'), "
        "optionally per entity, in a time window."
    ),
    "aggregate_measurements": (
        "Summary statistics (count, sum, average, min, max, latest) for numeric "
        "measurements per entity and metric."
    ),
    "list_deadlines": "Open commitments with due dates in an optional window.",
    "inspect_commitment_progress": "One commitment and its recorded progress entries.",
    "find_scheduling_conflicts": "Overlapping plan blocks within a time window.",
    "generate_plan": (
        "Generate deterministic suggested plan blocks from open commitments "
        "for a horizon."
    ),
    "compare_time_periods": (
        "Compare durations between two time periods (delta seconds and percent)."
    ),
    "resolve_source_history": (
        "The revision history of one external source record (external_key)."
    ),
    "propose_action": (
        "Propose a state change for the user's confirmation; nothing executes "
        "until accepted."
    ),
    "plan_query": "Classify a question into bounded recall and computation intents.",
    "inspect_evidence": "Inspect exact spans and locators for one owner-scoped source.",
    "inspect_claim_history": "Inspect grounded accepted, conflicting, and historical claims.",
    "inspect_coverage": "Measure which owner-scoped sources have data in a period.",
}


def tool_catalog() -> str:
    """Compact JSON catalog of tool names, descriptions, and argument schemas."""
    catalog = {}
    for name, args_model in TOOL_ARGS.items():
        schema = args_model.model_json_schema()
        catalog[name] = {
            "description": TOOL_DESCRIPTIONS[name],
            "parameters": {"properties": schema.get("properties", {}), "required": schema.get("required", [])},
        }
    return json.dumps(catalog)


async def _resolve_entity(
    session: AsyncSession,
    name: str | None,
    entity_type: str | None,
    user_id: uuid.UUID,
) -> Entity | None:
    if not name:
        return None
    if entity_type:
        return await get_current_entity_by_name(
            session, entity_type, name, owner_user_id=user_id
        )
    result = await session.execute(
        select(Entity)
        .where(
            Entity.is_superseded == False,
            Entity.owner_user_id == user_id,
            Entity.name == name,
        )
        .limit(1)
    )
    return result.scalars().first()


async def _search_memories(session, args: SearchMemoriesArgs, *, user_id, area_id) -> dict:
    hits = await retrieve(
        session,
        args.query,
        limit=args.limit,
        user_id=user_id,
        area_id=area_id,
        require_owner_metadata=True,
    )
    return {
        "hits": [
            {
                "source_type": hit.source_type,
                "source_id": str(hit.source_id),
                "title": hit.title,
                "content": (hit.content or "")[:1500],
                "occurred_at": _iso(hit.occurred_at),
                "score": round(hit.score, 4),
            }
            for hit in hits
        ]
    }


async def _traverse_graph(session, args: TraverseGraphArgs, *, user_id, **_) -> dict:
    entity = await _resolve_entity(session, args.entity_name, args.entity_type, user_id)
    if entity is None:
        return {"error": f"no current entity named {args.entity_name!r}"}
    entities, events, relations, truncated = await get_entity_graph(
        session, entity.id, depth=args.depth, relation_limit=args.limit
    )
    names = {item.id: item.name for item in [entity, *entities]}
    return {
        "entity": {"id": str(entity.id), "name": entity.name, "entity_type": entity.entity_type},
        "neighbors": [names[item.id] for item in entities if item.id in names],
        "events": [str(item.id) for item in events],
        "relations": [
            {
                "subject": names.get(relation.subject_id, str(relation.subject_id)),
                "predicate": relation.predicate,
                "object": names.get(relation.object_id, str(relation.object_id)),
                "occurred_from": _iso(relation.occurred_from),
                "occurred_until": _iso(relation.occurred_until),
                "confidence": relation.confidence,
            }
            for relation in relations
        ],
        "truncated": truncated,
    }


async def _calculate_duration(session, args: CalculateDurationArgs, *, user_id, area_id) -> dict:
    entity = await _resolve_entity(session, args.entity_name, args.entity_type, user_id)
    if args.entity_name and entity is None:
        return {"error": f"no current entity named {args.entity_name!r}"}
    rows = await aggregate_duration(
        session,
        entity_id=entity.id if entity else None,
        entity_type=args.entity_type,
        predicate=args.predicate,
        occurred_from=args.occurred_from,
        occurred_until=args.occurred_until,
        area_id=area_id,
        user_id=user_id,
    )
    return {"total_seconds": round(sum(row["seconds"] for row in rows), 3), "per_entity": rows}


async def _aggregate_measurements(session, args: AggregateMeasurementsArgs, *, user_id, area_id) -> dict:
    entity = await _resolve_entity(session, args.entity_name, args.entity_type, user_id)
    if args.entity_name and entity is None:
        return {"error": f"no current entity named {args.entity_name!r}"}
    rows = await aggregate_measurements(
        session,
        entity_id=entity.id if entity else None,
        entity_type=args.entity_type,
        metric=args.metric,
        occurred_from=args.occurred_from,
        occurred_until=args.occurred_until,
        area_id=area_id,
        user_id=user_id,
    )
    return {"measurements": rows}


async def _list_deadlines(session, args: ListDeadlinesArgs, *, user_id, area_id) -> dict:
    statement = select(Commitment).where(
        Commitment.owner_user_id == user_id,
        Commitment.status.in_(["suggested", "planned", "in_progress"])
    )
    if args.due_from:
        statement = statement.where(Commitment.due_at >= args.due_from)
    if args.due_until:
        statement = statement.where(Commitment.due_at <= args.due_until)
    if area_id is not None:
        from app.services.context import scoped_target_ids

        scoped = await scoped_target_ids(
            session, area_id=area_id, user_id=user_id, target_type="commitment"
        )
        if not scoped:
            return {"deadlines": []}
        statement = statement.where(Commitment.id.in_(list(scoped)))
    commitments = (
        await session.execute(
            statement.order_by(col(Commitment.due_at).asc().nulls_last()).limit(args.limit)
        )
    ).scalars().all()
    return {
        "deadlines": [
            {
                "id": str(item.id),
                "title": item.title,
                "status": item.status,
                "due_at": _iso(item.due_at),
                "description": item.description,
            }
            for item in commitments
        ]
    }


async def _inspect_commitment_progress(
    session, args: InspectCommitmentProgressArgs, *, user_id, **_
) -> dict:
    commitment = (
        await session.execute(
            select(Commitment)
            .where(Commitment.owner_user_id == user_id)
            .where(Commitment.title.ilike(f"%{args.commitment_title}%"))
            .order_by(col(Commitment.created_at).desc())
            .limit(1)
        )
    ).scalars().first()
    if commitment is None:
        return {"error": f"no commitment matching {args.commitment_title!r}"}
    progress = (
        await session.execute(
            select(CommitmentProgress)
            .where(CommitmentProgress.commitment_id == commitment.id)
            .order_by(col(CommitmentProgress.observed_at).asc())
        )
    ).scalars().all()
    return {
        "commitment": {
            "id": str(commitment.id),
            "title": commitment.title,
            "status": commitment.status,
            "due_at": _iso(commitment.due_at),
        },
        "progress": [
            {
                "amount": entry.amount,
                "unit": entry.unit,
                "observed_at": _iso(entry.observed_at),
                "note": entry.note,
            }
            for entry in progress
        ],
    }


async def _find_conflicts(session, args: FindConflictsArgs, *, user_id, **_) -> dict:
    blocks = (
        await session.execute(
            select(PlanBlock)
            .where(PlanBlock.owner_user_id == user_id)
            .where(PlanBlock.status.in_(["suggested", "accepted", "completed"]))
            .where(PlanBlock.start_at < args.occurred_until)
            .where(PlanBlock.end_at > args.occurred_from)
            .order_by(col(PlanBlock.start_at).asc())
        )
    ).scalars().all()
    conflicts = []
    for index, first in enumerate(blocks):
        for second in blocks[index + 1 :]:
            overlap_start = max(first.start_at, second.start_at)
            overlap_end = min(first.end_at, second.end_at)
            if overlap_end > overlap_start:
                conflicts.append(
                    {
                        "block_a": {
                            "id": str(first.id),
                            "start_at": _iso(first.start_at),
                            "end_at": _iso(first.end_at),
                        },
                        "block_b": {
                            "id": str(second.id),
                            "start_at": _iso(second.start_at),
                            "end_at": _iso(second.end_at),
                        },
                        "overlap_minutes": int((overlap_end - overlap_start).total_seconds() // 60),
                    }
                )
    return {"conflicts": conflicts}


async def _generate_plan(session, args: GeneratePlanArgs, *, user_id, **_) -> dict:
    start_at = _now()
    end_at = start_at + timedelta(days=args.horizon_days)
    blocks = await generate_plan(
        session,
        start_at,
        end_at,
        owner_user_id=user_id,
        daily_capacity_minutes=args.daily_capacity_minutes,
        block_minutes=args.block_minutes,
    )
    commitment_ids = {block.commitment_id for block in blocks}
    titles = {
        item.id: item.title
        for item in (
            await session.execute(
                select(Commitment).where(
                    Commitment.owner_user_id == user_id,
                    Commitment.id.in_(list(commitment_ids)),
                )
            )
        ).scalars().all()
    }
    return {
        "blocks": [
            {
                "commitment": titles.get(block.commitment_id, str(block.commitment_id)),
                "start_at": _iso(block.start_at),
                "end_at": _iso(block.end_at),
                "rationale": block.rationale,
            }
            for block in blocks
        ],
        "note": "Blocks are suggested; acceptance happens through the plan interface.",
    }


async def _compare_periods(session, args: CompareTimePeriodsArgs, *, user_id, area_id) -> dict:
    entity = await _resolve_entity(session, args.entity_name, args.entity_type, user_id)
    if args.entity_name and entity is None:
        return {"error": f"no current entity named {args.entity_name!r}"}
    first = await aggregate_duration(
        session,
        entity_id=entity.id if entity else None,
        entity_type=args.entity_type,
        predicate=args.predicate,
        occurred_from=args.from_1,
        occurred_until=args.until_1,
        area_id=area_id,
        user_id=user_id,
    )
    second = await aggregate_duration(
        session,
        entity_id=entity.id if entity else None,
        entity_type=args.entity_type,
        predicate=args.predicate,
        occurred_from=args.from_2,
        occurred_until=args.until_2,
        area_id=area_id,
        user_id=user_id,
    )
    seconds_1 = sum(row["seconds"] for row in first)
    seconds_2 = sum(row["seconds"] for row in second)
    delta = seconds_2 - seconds_1
    return {
        "period_1_seconds": round(seconds_1, 3),
        "period_2_seconds": round(seconds_2, 3),
        "delta_seconds": round(delta, 3),
        "delta_percent": round(delta / seconds_1 * 100, 2) if seconds_1 else None,
    }


async def _resolve_source_history(
    session, args: ResolveSourceHistoryArgs, *, user_id, **_
) -> dict:
    record = (
        await session.execute(
            select(SourceRecord)
            .join(SourceConnection, SourceConnection.id == SourceRecord.connection_id)
            .where(
                SourceConnection.user_id == user_id,
                SourceRecord.external_key == args.external_key,
            )
            .limit(1)
        )
    ).scalars().first()
    if record is None:
        return {"error": f"no source record with external_key {args.external_key!r}"}
    logs = (
        await session.execute(
            select(RawLog)
            .where(RawLog.source_record_id == record.id)
            .order_by(col(RawLog.received_at).asc())
        )
    ).scalars().all()
    revisions = []
    for log in logs:
        events = (
            await session.execute(
                select(Event)
                .where(Event.source_log_id == log.id)
                .order_by(col(Event.created_at).asc())
            )
        ).scalars().all()
        revisions.append(
            {
                "raw_log_id": str(log.id),
                "received_at": _iso(log.received_at),
                "revision": log.external_revision,
                "source_updated_at": _iso(log.source_updated_at),
                "events": [
                    {
                        "event_id": str(event.id),
                        "event_type": event.event_type,
                        "is_superseded": event.is_superseded,
                        "superseded_by": str(event.superseded_by) if event.superseded_by else None,
                    }
                    for event in events
                ],
            }
        )
    return {
        "external_key": record.external_key,
        "connection_id": str(record.connection_id),
        "update_policy": record.update_policy,
        "current_revision": record.current_revision,
        "source_updated_at": _iso(record.source_updated_at),
        "revisions": revisions,
    }


async def _plan_query(_session, args: PlanQueryArgs, **_) -> dict:
    return plan_query(args.question).model_dump(mode="json")


async def _inspect_evidence(
    session, args: InspectEvidenceArgs, *, user_id, area_id, **_
) -> dict:
    documents = (
        await session.execute(
            select(EvidenceDocument)
            .outerjoin(EvidenceSpan, EvidenceSpan.document_id == EvidenceDocument.id)
            .where(
                EvidenceDocument.owner_user_id == user_id,
                EvidenceDocument.is_superseded == False,
                (EvidenceDocument.id == args.source_id)
                | (EvidenceDocument.source_file_id == args.source_id)
                | (EvidenceDocument.source_event_id == args.source_id)
                | (EvidenceSpan.id == args.source_id)
                | (EvidenceSpan.source_chunk_id == args.source_id),
            )
            .distinct()
        )
    ).scalars().all()
    if not documents:
        return {"error": "No owner-scoped evidence found for that source."}
    document_ids = [document.id for document in documents]
    spans = (
        await session.execute(
            select(EvidenceSpan)
            .where(EvidenceSpan.document_id.in_(document_ids))
            .order_by(EvidenceSpan.document_id, EvidenceSpan.sequence)
            .limit(args.limit)
        )
    ).scalars().all()
    if area_id is not None:
        spans = [
            span
            for span in spans
            if await target_visible(
                session,
                user_id=user_id,
                target_type="evidence_span",
                target_id=span.id,
                area_id=area_id,
            )
        ]
        visible_document_ids = {span.document_id for span in spans}
        documents = [document for document in documents if document.id in visible_document_ids]
        if not spans:
            return {"error": "No evidence is visible in the active Life Area."}
    return {
        "documents": [
            {
                "id": str(document.id),
                "kind": document.kind,
                "source_file_id": str(document.source_file_id) if document.source_file_id else None,
                "parser": document.parser,
                "parser_version": document.parser_version,
                "created_at": document.created_at.isoformat(),
            }
            for document in documents
        ],
        "spans": [
            {
                "id": str(span.id),
                "text": span.text[:3000],
                "page_number": span.page_number,
                "char_start": span.char_start,
                "char_end": span.char_end,
                "start_seconds": span.start_seconds,
                "end_seconds": span.end_seconds,
                "speaker": span.speaker_label,
                "locator": span.locator,
            }
            for span in spans
        ],
    }


async def _inspect_claim_history(
    session, args: InspectClaimHistoryArgs, *, user_id, area_id, **_
) -> dict:
    entity = await _resolve_entity(session, args.entity_name, args.entity_type, user_id)
    if args.entity_name and entity is None:
        return {"error": f"no current entity named {args.entity_name!r}"}
    statement = select(MemoryClaim).where(MemoryClaim.owner_user_id == user_id)
    if entity is not None:
        statement = statement.where(
            (MemoryClaim.subject_entity_id == entity.id)
            | (MemoryClaim.object_entity_id == entity.id)
        )
    if args.predicate:
        statement = statement.where(MemoryClaim.predicate == args.predicate)
    if args.known_at is not None:
        statement = statement.where(
            MemoryClaim.learned_at <= args.known_at,
            (MemoryClaim.invalidated_at.is_(None))
            | (MemoryClaim.invalidated_at > args.known_at),
        )
    if args.valid_at is not None:
        statement = statement.where(
            (MemoryClaim.valid_from.is_(None)) | (MemoryClaim.valid_from <= args.valid_at),
            (MemoryClaim.valid_until.is_(None)) | (MemoryClaim.valid_until > args.valid_at),
        )
    claims = (
        await session.execute(
            statement.order_by(col(MemoryClaim.learned_at).desc()).limit(args.limit)
        )
    ).scalars().all()
    if area_id is not None:
        claims = [
            claim
            for claim in claims
            if await target_visible(
                session,
                user_id=user_id,
                target_type="memory_claim",
                target_id=claim.id,
                area_id=area_id,
            )
        ]
    evidence_rows = (
        await session.execute(
            select(ClaimEvidence, EvidenceSpan)
            .outerjoin(EvidenceSpan, EvidenceSpan.id == ClaimEvidence.span_id)
            .where(ClaimEvidence.claim_id.in_([claim.id for claim in claims]))
        )
    ).all() if claims else []
    evidence_by_claim: dict[uuid.UUID, list[dict]] = {}
    for link, span in evidence_rows:
        evidence_by_claim.setdefault(link.claim_id, []).append(
            {
                "span_id": str(span.id) if span is not None else None,
                "quote": span.text[:1000] if span is not None else None,
                "role": link.role,
                "event_id": str(link.event_id) if link.event_id else None,
                "source_record_id": str(link.source_record_id) if link.source_record_id else None,
            }
        )
    return {
        "claims": [
            {
                "id": str(claim.id),
                "kind": claim.kind,
                "predicate": claim.predicate,
                "subject_entity_id": str(claim.subject_entity_id) if claim.subject_entity_id else None,
                "object_entity_id": str(claim.object_entity_id) if claim.object_entity_id else None,
                "value": claim.value,
                "polarity": claim.polarity,
                "modality": claim.modality,
                "valid_from": _iso(claim.valid_from),
                "valid_until": _iso(claim.valid_until),
                "learned_at": _iso(claim.learned_at),
                "status": claim.reconciliation_status,
                "canonical_target_type": claim.canonical_target_type,
                "canonical_target_id": (
                    str(claim.canonical_target_id) if claim.canonical_target_id else None
                ),
                "evidence": evidence_by_claim.get(claim.id, []),
            }
            for claim in claims
        ]
    }


async def _inspect_coverage(
    session, args: InspectCoverageArgs, *, user_id, **_
) -> dict:
    if args.occurred_until <= args.occurred_from:
        return {"error": "occurred_until must be after occurred_from"}
    capture_rows = (
        await session.execute(
            select(Capture.kind, func.count(Capture.id))
            .where(
                Capture.user_id == user_id,
                Capture.captured_at >= args.occurred_from,
                Capture.captured_at < args.occurred_until,
            )
            .group_by(Capture.kind)
        )
    ).all()
    event_rows = (
        await session.execute(
            select(Event.event_type, func.count(Event.id))
            .where(
                Event.owner_user_id == user_id,
                Event.start_time >= args.occurred_from,
                Event.start_time < args.occurred_until,
                Event.is_superseded == False,
            )
            .group_by(Event.event_type)
        )
    ).all()
    evidence_count = await session.scalar(
        select(func.count(EvidenceDocument.id)).where(
            EvidenceDocument.owner_user_id == user_id,
            EvidenceDocument.created_at >= args.occurred_from,
            EvidenceDocument.created_at < args.occurred_until,
            EvidenceDocument.is_superseded == False,
        )
    )
    return {
        "occurred_from": _iso(args.occurred_from),
        "occurred_until": _iso(args.occurred_until),
        "captures_by_kind": {kind: count for kind, count in capture_rows},
        "events_by_type": {event_type: count for event_type, count in event_rows},
        "evidence_documents_learned": int(evidence_count or 0),
        "has_any_data": bool(capture_rows or event_rows or evidence_count),
        "interpretation": (
            "No matching rows means LifeLog lacks coverage; it does not prove no activity occurred."
        ),
    }


async def _propose_action(session, args: ProposeActionArgs, *, user_id, **_kwargs) -> dict:
    item = await upsert_review_item(
        session,
        user_id=user_id,
        kind="proposed_action",
        source_type="proposed_action",
        source_id=uuid.uuid4(),
        title=args.summary,
        summary="A deterministic proposed action prepared by the assistant. Nothing changes until you accept it.",
        payload={"action": args.action},
        consequential=args.consequential,
        confidence=0.9,
        priority="high" if args.consequential else "normal",
        choices=[
            {"id": "accept", "label": "Execute this change"},
            {"id": "reject", "label": "Do not execute"},
            {"id": "dismiss", "label": "Ignore"},
        ],
    )
    return {
        "review_item_id": str(item.id),
        "status": item.status,
        "explanation": "Awaiting your confirmation in the Inbox.",
    }


_HANDLERS: dict[str, object] = {
    "search_memories": _search_memories,
    "traverse_graph": _traverse_graph,
    "calculate_duration": _calculate_duration,
    "aggregate_measurements": _aggregate_measurements,
    "list_deadlines": _list_deadlines,
    "inspect_commitment_progress": _inspect_commitment_progress,
    "find_scheduling_conflicts": _find_conflicts,
    "generate_plan": _generate_plan,
    "compare_time_periods": _compare_periods,
    "resolve_source_history": _resolve_source_history,
    "propose_action": _propose_action,
    "plan_query": _plan_query,
    "inspect_evidence": _inspect_evidence,
    "inspect_claim_history": _inspect_claim_history,
    "inspect_coverage": _inspect_coverage,
}


async def execute_tool(
    session: AsyncSession,
    *,
    user_id: uuid.UUID,
    area_id: uuid.UUID | None,
    name: str,
    arguments: dict,
) -> dict:
    """Validate arguments and run one deterministic tool; never raises for tool errors."""
    handler = _HANDLERS.get(name)
    if handler is None:
        return {"error": f"unknown tool {name!r}"}
    args_model = TOOL_ARGS[name]
    try:
        args = args_model.model_validate(arguments or {})
    except ValidationError as exc:
        return {"error": f"invalid arguments: {exc.errors()}"}
    try:
        return await handler(session, args, user_id=user_id, area_id=area_id)
    except Exception as exc:
        return {"error": f"{type(exc).__name__}: {exc}"}
