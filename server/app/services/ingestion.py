import hashlib
import json
import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from app.core.logger import get_logger
from app.models.auth import Device
from app.models.claims import ClaimEvidence, FactEvidence, MemoryClaim
from app.models.evidence import EvidenceDocument, EvidenceSpan
from app.models.ingest import Event, RawLog
from app.models.kernel import Measurement, Relation
from app.models.retrieval import SearchDocument
from app.models.sources import SourceConnection, SourceRecord

logger = get_logger(__name__)


def calculate_payload_hash(payload: dict[str, Any]) -> str:
    payload_str = json.dumps(payload, sort_keys=True, default=str)
    return hashlib.sha256(payload_str.encode("utf-8")).hexdigest()


def calculate_ingest_key(
    *,
    device_id: str,
    payload_hash: str,
    source_connection_id: Any | None,
    external_key: str | None,
    external_revision: str | None,
) -> str:
    """Build one stable idempotency identity for device and connected-source writes."""
    if source_connection_id is not None and external_key:
        revision = external_revision or payload_hash
        identity = f"source:{source_connection_id}:{external_key}:{revision}"
    else:
        identity = f"device:{device_id}:{payload_hash}"
    return hashlib.sha256(identity.encode("utf-8")).hexdigest()


def calculate_semantic_key(*, device_id: str, payload: dict[str, Any]) -> str | None:
    """Stable fingerprint for device writes that vary only in noise fields.

    Mirrors the iOS vault's dedup semantics: same (type, start, end, data)
    collapses even when the client regenerates the signal `id` (e.g. re-buffered
    queues or live/backfill overlap). Returns None when the payload carries
    none of the identifying fields, in which case no semantic dedup applies.
    """
    if not isinstance(payload, dict) or not payload.get("type"):
        return None
    canonical = json.dumps(
        {
            "type": payload.get("type"),
            "start": payload.get("start_time"),
            "end": payload.get("end_time"),
            "data": payload.get("data"),
        },
        sort_keys=True,
        default=str,
    )
    return hashlib.sha256(f"device-semantic:{device_id}:{canonical}".encode()).hexdigest()


def _normalize_dt(dt: datetime | None) -> datetime | None:
    if dt is None:
        return None
    if dt.tzinfo is not None:
        return dt.astimezone(UTC).replace(tzinfo=None)
    return dt


async def ingest_log(
    session: AsyncSession,
    device_id: str,
    extension_id: str,
    payload: dict[str, Any],
    client_timestamp: datetime | None = None,
    client_timezone: str | None = None,
    source_connection_id: Any | None = None,
    external_key: str | None = None,
    external_revision: str | None = None,
    source_updated_at: datetime | None = None,
    update_policy: str = "append",
) -> tuple[RawLog, bool]:
    payload_hash = calculate_payload_hash(payload)
    ingest_key = calculate_ingest_key(
        device_id=device_id,
        payload_hash=payload_hash,
        source_connection_id=source_connection_id,
        external_key=external_key,
        external_revision=external_revision,
    )
    semantic_key = None
    if source_connection_id is None:
        semantic_key = calculate_semantic_key(device_id=device_id, payload=payload)
    client_timestamp = _normalize_dt(client_timestamp)
    source_updated_at = _normalize_dt(source_updated_at)
    owner_user_id = await _resolve_owner(
        session,
        device_id=device_id,
        source_connection_id=source_connection_id,
    )

    statement = select(RawLog).where(RawLog.ingest_key == ingest_key)
    result = await session.execute(statement)
    existing = result.scalars().first()

    # Migration 006 gives historical device rows a deterministic transitional
    # key. Preserve their original idempotency semantics and lazily adopt the
    # canonical key the first time they are seen again.
    if existing is None and source_connection_id is None:
        existing = (
            await session.execute(
                select(RawLog).where(
                    RawLog.device_id == device_id,
                    RawLog.payload_hash == payload_hash,
                    RawLog.source_connection_id.is_(None),
                )
            )
        ).scalars().first()
        if existing is not None:
            existing.ingest_key = ingest_key
            session.add(existing)
            await session.commit()

    # Semantic dedup: collapse device writes that differ only in noise fields
    # (regenerated signal ids, live/backfill overlap reporting the same event).
    if existing is None and semantic_key is not None:
        existing = (
            await session.execute(
                select(RawLog).where(
                    RawLog.device_id == device_id,
                    RawLog.semantic_key == semantic_key,
                )
            )
        ).scalars().first()
        if existing is not None:
            existing.ingest_key = ingest_key
            session.add(existing)
            await session.commit()

    if existing:
        return existing, False

    source_record = None
    if external_key and source_connection_id:
        source_record = (
            await session.execute(
                select(SourceRecord).where(
                    SourceRecord.connection_id == source_connection_id,
                    SourceRecord.external_key == external_key,
                )
            )
        ).scalars().first()
        if source_record is None:
            source_record = SourceRecord(
                connection_id=source_connection_id,
                external_key=external_key,
                update_policy=update_policy,
            )
            session.add(source_record)
            await session.flush()

    raw_log = RawLog(
        owner_user_id=owner_user_id,
        ingest_key=ingest_key,
        device_id=device_id,
        extension_id=extension_id,
        payload=payload,
        payload_hash=payload_hash,
        semantic_key=semantic_key,
        client_timestamp=client_timestamp,
        client_timezone=client_timezone,
        source_connection_id=source_connection_id,
        source_record_id=source_record.id if source_record else None,
        external_key=external_key,
        external_revision=external_revision,
        source_updated_at=source_updated_at,
        update_policy=update_policy,
    )
    session.add(raw_log)

    try:
        await session.commit()
        await session.refresh(raw_log)
        if source_record is not None:
            source_record.current_raw_log_id = raw_log.id
            source_record.current_revision = external_revision
            source_record.source_updated_at = source_updated_at
            source_record.update_policy = update_policy
            source_record.updated_at = datetime.now(UTC).replace(tzinfo=None)
            session.add(source_record)
            await session.commit()
        return raw_log, True
    except IntegrityError:
        await session.rollback()
        result = await session.execute(statement)
        existing = result.scalars().first()
        if existing:
            return existing, False
        raise


async def _resolve_owner(
    session: AsyncSession,
    *,
    device_id: str,
    source_connection_id: Any | None,
) -> uuid.UUID | None:
    if source_connection_id is not None:
        connection = await session.get(SourceConnection, source_connection_id)
        if connection is not None:
            return connection.user_id
    device = await session.get(Device, device_id)
    return device.user_id if device is not None else None


async def supersede_previous_source_events(
    session: AsyncSession,
    raw_log: RawLog,
    new_events: list[Event],
) -> int:
    """Reconcile replace/snapshot revisions after their replacement exists."""
    if (
        raw_log.update_policy not in ("replace", "snapshot")
        or raw_log.source_record_id is None
        or not new_events
    ):
        return 0
    prior_logs = select(RawLog.id).where(
        RawLog.source_record_id == raw_log.source_record_id,
        RawLog.id != raw_log.id,
    )
    previous = (
        await session.execute(
            select(Event)
            .where(Event.source_log_id.in_(prior_logs), Event.is_superseded == False)
            .order_by(Event.created_at.desc())
        )
    ).scalars().all()
    replacements = {event.event_type: event for event in new_events}
    count = 0
    now = datetime.now(UTC).replace(tzinfo=None)
    for old_event in previous:
        replacement = replacements.get(old_event.event_type, new_events[0])
        old_event.is_superseded = True
        old_event.superseded_by = replacement.id
        session.add(old_event)
        linked_claims = (
            await session.execute(
                select(MemoryClaim)
                .join(ClaimEvidence, ClaimEvidence.claim_id == MemoryClaim.id)
                .where(
                    ClaimEvidence.event_id == old_event.id,
                    MemoryClaim.invalidated_at.is_(None),
                )
                .distinct()
            )
        ).scalars().all()
        invalidated_claims = [
            claim
            for claim in linked_claims
            if not await _claim_has_other_active_evidence(
                session,
                claim_id=claim.id,
                excluding_event_id=old_event.id,
            )
        ]
        invalidated_claim_ids = {claim.id for claim in invalidated_claims}
        for claim in invalidated_claims:
            claim.reconciliation_status = "superseded"
            claim.invalidated_at = now
            session.add(claim)
        if invalidated_claim_ids:
            claim_documents = (
                await session.execute(
                    select(SearchDocument).where(
                        SearchDocument.source_type == "memory_claim",
                        SearchDocument.source_id.in_(invalidated_claim_ids),
                        SearchDocument.is_superseded == False,
                    )
                )
            ).scalars().all()
            for document in claim_documents:
                document.is_superseded = True
                session.add(document)
        relations = (
            await session.execute(
                select(Relation).where(
                    Relation.source_event_id == old_event.id,
                    Relation.is_superseded == False,
                )
            )
        ).scalars().all()
        for relation in relations:
            if not await _has_active_fact_support(
                session,
                target_type="relation",
                target_id=relation.id,
                excluding_claim_ids=invalidated_claim_ids,
            ):
                relation.is_superseded = True
                relation.invalidated_at = now
                session.add(relation)
        measurements = (
            await session.execute(
                select(Measurement).where(
                    Measurement.source_event_id == old_event.id,
                    Measurement.is_superseded == False,
                )
            )
        ).scalars().all()
        for measurement in measurements:
            if not await _has_active_fact_support(
                session,
                target_type="measurement",
                target_id=measurement.id,
                excluding_claim_ids=invalidated_claim_ids,
            ):
                measurement.is_superseded = True
                session.add(measurement)
        documents = (
            await session.execute(
                select(SearchDocument).where(
                    SearchDocument.source_type == "event",
                    SearchDocument.source_id == old_event.id,
                    SearchDocument.is_superseded == False,
                )
            )
        ).scalars().all()
        for document in documents:
            document.is_superseded = True
            session.add(document)
        count += 1
    await session.flush()
    return count


async def _has_active_fact_support(
    session: AsyncSession,
    *,
    target_type: str,
    target_id: uuid.UUID,
    excluding_claim_ids: set[uuid.UUID],
) -> bool:
    statement = (
        select(FactEvidence.id)
        .join(MemoryClaim, MemoryClaim.id == FactEvidence.claim_id)
        .where(
            FactEvidence.target_type == target_type,
            FactEvidence.target_id == target_id,
            MemoryClaim.reconciliation_status.in_(("accepted", "corroborating")),
            MemoryClaim.invalidated_at.is_(None),
        )
    )
    if excluding_claim_ids:
        statement = statement.where(MemoryClaim.id.notin_(excluding_claim_ids))
    return (await session.execute(statement.limit(1))).scalars().first() is not None


async def _claim_has_other_active_evidence(
    session: AsyncSession,
    *,
    claim_id: uuid.UUID,
    excluding_event_id: uuid.UUID,
) -> bool:
    evidence = (
        await session.execute(
            select(ClaimEvidence).where(
                ClaimEvidence.claim_id == claim_id,
                (ClaimEvidence.event_id.is_(None))
                | (ClaimEvidence.event_id != excluding_event_id),
            )
        )
    ).scalars().all()
    for item in evidence:
        if item.role == "user_confirmation" or item.source_record_id is not None:
            return True
        if item.event_id is not None:
            event = await session.get(Event, item.event_id)
            if event is not None and not event.is_superseded:
                return True
        if item.span_id is not None:
            span = await session.get(EvidenceSpan, item.span_id)
            document = (
                await session.get(EvidenceDocument, span.document_id)
                if span is not None
                else None
            )
            if document is not None and not document.is_superseded:
                return True
    return False
