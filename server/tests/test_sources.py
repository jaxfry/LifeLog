from contextlib import asynccontextmanager
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, patch

import pytest
from sqlmodel import select

from app.loader.contracts import PollEnvelope, PollResult
from app.models.auth import User
from app.models.claims import ClaimEvidence, FactEvidence, MemoryClaim
from app.models.config import Extension
from app.models.files import Commitment, Notification, PlanBlock
from app.models.ingest import Event, RawLog
from app.models.kernel import Entity
from app.models.sources import SourceCheckpoint, SourceConnection, SourceRecord, SourceSecret
from app.services.commitment_reconciliation import reconcile_event_commitments
from app.services.extension_runtime import enqueue_source_poll, poll_source_connection
from app.services.ingestion import calculate_payload_hash, ingest_log, supersede_previous_source_events
from app.services.kernel import create_relation
from app.services.retrieval import upsert_search_document
from app.services.source_secrets import get_source_secrets, set_source_secret


async def _persist_user(session, user: User) -> None:
    session.add(user)
    await session.commit()


@pytest.mark.asyncio
@pytest.mark.integration
async def test_source_connection_keeps_secrets_out_of_responses(
    async_client,
    session,
    mock_user,
):
    await _persist_user(session, mock_user)
    session.add(
        Extension(
            id="com.lifelog.canvas",
            version="1.0.0",
            config={"id": "com.lifelog.canvas", "version": "1.0.0"},
        )
    )
    await session.commit()

    response = await async_client.post(
        "/api/v1/sources",
        json={
            "extension_id": "com.lifelog.canvas",
            "name": "School Canvas",
            "config": {
                "base_url": "https://school.example",
                "authorization_url": "https://school.example/oauth/authorize",
                "token_url": "https://school.example/oauth/token",
            },
            "secrets": {"access_token": "very-secret-token"},
        },
    )
    assert response.status_code == 201
    data = response.json()
    assert data["secret_keys"] == ["access_token"]
    assert "very-secret-token" not in response.text
    stored = (await session.execute(select(SourceSecret))).scalars().one()
    assert b"very-secret-token" not in stored.ciphertext
    assert await get_source_secrets(session, stored.connection_id) == {
        "access_token": "very-secret-token"
    }


@pytest.mark.asyncio
@pytest.mark.integration
async def test_source_connection_rejects_credentials_in_public_config(
    async_client,
    session,
    mock_user,
):
    await _persist_user(session, mock_user)
    session.add(
        Extension(
            id="com.lifelog.canvas",
            version="1.0.0",
            config={"id": "com.lifelog.canvas", "version": "1.0.0"},
        )
    )
    await session.commit()
    response = await async_client.post(
        "/api/v1/sources",
        json={
            "extension_id": "com.lifelog.canvas",
            "name": "Canvas",
            "config": {"api_token": "wrong-place"},
        },
    )
    assert response.status_code == 400
    assert "secrets endpoint" in response.json()["detail"]


@pytest.mark.asyncio
@pytest.mark.unit
async def test_scheduled_source_poll_only_enqueues_arq():
    pool = AsyncMock()
    connection_id = SourceConnection(
        user_id=User(username="unused", hashed_password="x").id,
        extension_id="com.test.source",
        name="Test",
    ).id
    await enqueue_source_poll(pool, connection_id)
    pool.enqueue_job.assert_awaited_once_with(
        "task_poll_source",
        str(connection_id),
        _job_id=f"source-poll:{connection_id}",
    )


@pytest.mark.asyncio
@pytest.mark.integration
async def test_poller_advances_checkpoint_after_durable_ingestion(session, monkeypatch):
    user = User(username="source-owner", hashed_password="x")
    extension = Extension(
        id="com.lifelog.canvas",
        version="1.0.0",
        config={
            "id": "com.lifelog.canvas",
            "version": "1.0.0",
            "capabilities": ["collector", "normalizer"],
        },
    )
    session.add(user)
    session.add(extension)
    await session.flush()
    connection = SourceConnection(
        user_id=user.id,
        extension_id=extension.id,
        name="Canvas",
    )
    session.add(connection)
    await session.flush()
    await set_source_secret(session, connection.id, "token", "secret")
    await session.commit()

    @asynccontextmanager
    async def session_factory():
        yield session

    monkeypatch.setattr("app.services.extension_runtime.async_session_factory", session_factory)
    result = PollResult(
        records=[
            PollEnvelope(
                payload={"id": 42, "name": "Essay"},
                external_key="canvas:assignment:42",
                external_revision="2026-09-01T10:00:00Z",
                update_policy="replace",
            )
        ],
        next_checkpoint={"updated_after": "2026-09-01T10:00:00Z"},
        checkpoint_stream="assignments",
    )
    with (
        patch("app.services.extension_runtime.run_poller", AsyncMock(return_value=result)) as runner,
        patch("app.services.extension_runtime.process_log", AsyncMock(return_value=[])),
    ):
        counts = await poll_source_connection(connection.id)
    assert counts == {"received": 1, "created": 1}
    runtime_config = runner.await_args.args[1]
    assert runtime_config["secrets"] == {"token": "secret"}
    checkpoint = (await session.execute(select(SourceCheckpoint))).scalars().one()
    assert checkpoint.value == result.next_checkpoint
    assert checkpoint.stream == "assignments"
    record = (await session.execute(select(SourceRecord))).scalars().one()
    assert record.external_key == "canvas:assignment:42"

    with (
        patch(
            "app.services.extension_runtime.run_poller",
            AsyncMock(return_value=PollResult()),
        ) as next_runner,
        patch("app.services.extension_runtime.process_log", AsyncMock(return_value=[])),
    ):
        await poll_source_connection(connection.id)
    next_runtime = next_runner.await_args.args[1]
    assert next_runtime["checkpoint"] == {}
    assert next_runtime["checkpoints"] == {
        "assignments": {"updated_after": "2026-09-01T10:00:00Z"}
    }


@pytest.mark.asyncio
@pytest.mark.integration
async def test_poller_redacts_secrets_from_errors_and_failures(session, monkeypatch):
    from app.models.retrieval import ProcessingFailure

    user = User(username="redaction-owner", hashed_password="x")
    extension = Extension(
        id="com.test.redaction",
        version="1",
        config={
            "id": "com.test.redaction",
            "version": "1",
            "capabilities": ["collector", "normalizer"],
        },
    )
    session.add(user)
    session.add(extension)
    await session.flush()
    connection = SourceConnection(user_id=user.id, extension_id=extension.id, name="Secret")
    session.add(connection)
    await session.flush()
    await set_source_secret(session, connection.id, "token", "super-secret-value")
    await session.commit()

    @asynccontextmanager
    async def session_factory():
        yield session

    monkeypatch.setattr("app.services.extension_runtime.async_session_factory", session_factory)
    with (
        patch(
            "app.services.extension_runtime.run_poller",
            AsyncMock(side_effect=ValueError("bad token super-secret-value")),
        ),
        pytest.raises(RuntimeError, match=r"\[REDACTED\]"),
    ):
        await poll_source_connection(connection.id)
    await session.refresh(connection)
    assert "super-secret-value" not in connection.last_sync_error
    failure = (await session.execute(select(ProcessingFailure))).scalars().one()
    assert "super-secret-value" not in failure.error_message
    assert "super-secret-value" not in failure.traceback


@pytest.mark.asyncio
@pytest.mark.integration
async def test_poller_replay_resumes_ingested_but_unprocessed_revision(session, monkeypatch):
    user = User(username="replay-owner", hashed_password="x")
    extension = Extension(
        id="com.test.replay",
        version="1",
        config={"id": "com.test.replay", "version": "1", "capabilities": ["collector", "normalizer"]},
    )
    session.add(user)
    session.add(extension)
    await session.flush()
    connection = SourceConnection(user_id=user.id, extension_id=extension.id, name="Replay")
    session.add(connection)
    await session.flush()
    raw_log, _ = await ingest_log(
        session,
        "source-device",
        extension.id,
        {"id": 1},
        source_connection_id=connection.id,
        external_key="item:1",
        external_revision="1",
    )

    @asynccontextmanager
    async def session_factory():
        yield session

    monkeypatch.setattr("app.services.extension_runtime.async_session_factory", session_factory)
    result = PollResult(
        records=[PollEnvelope(payload={"id": 1}, external_key="item:1", external_revision="1")],
        next_checkpoint={"cursor": 1},
    )
    with (
        patch("app.services.extension_runtime.run_poller", AsyncMock(return_value=result)),
        patch("app.services.extension_runtime.process_log", AsyncMock(return_value=[])) as processor,
    ):
        counts = await poll_source_connection(connection.id)
    assert counts == {"received": 1, "created": 0}
    processor.assert_awaited_once_with(session, raw_log.id)
    checkpoint = (await session.execute(select(SourceCheckpoint))).scalars().one()
    assert checkpoint.value == {"cursor": 1}


@pytest.mark.asyncio
@pytest.mark.integration
async def test_replace_revision_supersedes_event_graph_and_recall(session):
    user = User(username="revision-owner", hashed_password="x")
    extension = Extension(id="com.test.source", version="1", config={})
    session.add(user)
    session.add(extension)
    await session.flush()
    connection = SourceConnection(user_id=user.id, extension_id=extension.id, name="Test")
    session.add(connection)
    await session.flush()
    first_log, _ = await ingest_log(
        session,
        "source-device",
        extension.id,
        {"title": "Old title"},
        source_connection_id=connection.id,
        external_key="item:1",
        external_revision="1",
        update_policy="replace",
    )
    first = Event(
        owner_user_id=user.id,
        source_log_id=first_log.id,
        event_type="assignment",
        start_time=datetime(2026, 1, 1),
        data={"title": "Old title"},
    )
    entity = Entity(
        owner_user_id=user.id,
        entity_type="course",
        name="Math",
        canonical_key="math",
    )
    session.add(first)
    session.add(entity)
    await session.flush()
    relation = await create_relation(
        session,
        subject_id=first.id,
        subject_type="event",
        predicate="for_course",
        object_id=entity.id,
        object_type="entity",
        source_event_id=first.id,
    )
    document = await upsert_search_document(
        session,
        source_type="event",
        source_id=first.id,
        content="Old title",
        metadata={"owner_user_id": str(user.id)},
    )
    claim = MemoryClaim(
        owner_user_id=user.id,
        kind="relation",
        predicate="for_course",
        object_entity_id=entity.id,
        quality_score=1.0,
        reconciliation_status="accepted",
        extractor="test",
        extraction_version=1,
        ontology_version="1",
        derivation_key="old-source-claim",
        canonical_target_type="relation",
        canonical_target_id=relation.id,
    )
    session.add(claim)
    await session.flush()
    session.add(ClaimEvidence(claim_id=claim.id, event_id=first.id))
    session.add(
        FactEvidence(
            target_type="relation",
            target_id=relation.id,
            claim_id=claim.id,
        )
    )
    await session.commit()

    second_log, _ = await ingest_log(
        session,
        "source-device",
        extension.id,
        {"title": "New title"},
        source_connection_id=connection.id,
        external_key="item:1",
        external_revision="2",
        update_policy="replace",
    )
    second = Event(
        owner_user_id=user.id,
        source_log_id=second_log.id,
        event_type="assignment",
        start_time=datetime(2026, 1, 2),
        data={"title": "New title"},
    )
    session.add(second)
    await session.flush()
    assert await supersede_previous_source_events(session, second_log, [second]) == 1
    assert first.is_superseded is True
    assert first.superseded_by == second.id
    assert relation.is_superseded is True
    assert relation.invalidated_at is not None
    assert document.is_superseded is True
    assert claim.reconciliation_status == "superseded"
    assert claim.invalidated_at is not None


@pytest.mark.asyncio
@pytest.mark.integration
async def test_source_identity_does_not_collapse_equal_payloads(session):
    user = User(username="identity-owner", hashed_password="x")
    extension = Extension(id="com.test.identity", version="1", config={})
    session.add(user)
    session.add(extension)
    await session.flush()
    connection = SourceConnection(user_id=user.id, extension_id=extension.id, name="Test")
    session.add(connection)
    await session.flush()

    first, first_created = await ingest_log(
        session,
        "source-device",
        extension.id,
        {"title": "Same"},
        source_connection_id=connection.id,
        external_key="item:1",
        external_revision="1",
    )
    second, second_created = await ingest_log(
        session,
        "source-device",
        extension.id,
        {"title": "Same"},
        source_connection_id=connection.id,
        external_key="item:2",
        external_revision="1",
    )
    assert first_created is True
    assert second_created is True
    assert first.id != second.id
    assert first.ingest_key != second.ingest_key


@pytest.mark.asyncio
@pytest.mark.integration
async def test_legacy_device_log_adopts_canonical_ingest_key(session):
    legacy = RawLog(
        ingest_key="legacy-transition-key",
        device_id="phone",
        extension_id="manual",
        payload={"value": 1},
        payload_hash=calculate_payload_hash({"value": 1}),
    )
    session.add(legacy)
    await session.commit()

    result, created = await ingest_log(session, "phone", "manual", {"value": 1})
    assert created is False
    assert result.id == legacy.id
    assert result.ingest_key != "legacy-transition-key"


@pytest.mark.asyncio
@pytest.mark.integration
async def test_source_deadline_revision_reconciles_commitment_plan_and_notification(session):
    user = User(username="deadline-owner", hashed_password="x")
    extension = Extension(
        id="com.test.deadlines",
        version="1",
        config={
            "id": "com.test.deadlines",
            "version": "1",
            "commitment_mappings": [
                {
                    "event_type": "assignment",
                    "title_path": "title",
                    "due_at_path": "due_at",
                }
            ],
        },
    )
    session.add(user)
    session.add(extension)
    await session.flush()
    connection = SourceConnection(user_id=user.id, extension_id=extension.id, name="Deadlines")
    session.add(connection)
    await session.flush()
    first_log, _ = await ingest_log(
        session,
        "source-device",
        extension.id,
        {"title": "Essay", "due_at": "2026-09-10T17:00:00Z"},
        source_connection_id=connection.id,
        external_key="assignment:1",
        external_revision="1",
        update_policy="replace",
    )
    first_event = Event(
        source_log_id=first_log.id,
        event_type="assignment",
        start_time=datetime(2026, 9, 1),
        data={"title": "Essay", "due_at": "2026-09-10T17:00:00Z"},
    )
    session.add(first_event)
    await session.flush()
    assert await reconcile_event_commitments(session, first_event, first_log) == 1
    first_commitment = (await session.execute(select(Commitment))).scalars().one()
    plan = PlanBlock(
        commitment_id=first_commitment.id,
        start_at=datetime(2026, 9, 5, 10),
        end_at=datetime(2026, 9, 5, 11),
        status="accepted",
    )
    session.add(plan)
    await session.commit()

    second_log, _ = await ingest_log(
        session,
        "source-device",
        extension.id,
        {"title": "Essay", "due_at": "2026-09-12T17:00:00Z"},
        source_connection_id=connection.id,
        external_key="assignment:1",
        external_revision="2",
        update_policy="replace",
    )
    second_event = Event(
        source_log_id=second_log.id,
        event_type="assignment",
        start_time=datetime(2026, 9, 2),
        data={"title": "Essay", "due_at": "2026-09-12T17:00:00Z"},
    )
    session.add(second_event)
    await session.flush()
    assert await reconcile_event_commitments(session, second_event, second_log) == 1

    commitments = (
        await session.execute(select(Commitment).order_by(Commitment.created_at))
    ).scalars().all()
    assert len(commitments) == 2
    assert commitments[0].status == "cancelled"
    assert commitments[0].superseded_by == commitments[1].id
    assert commitments[1].status == "suggested"
    assert commitments[1].due_at - commitments[0].due_at == timedelta(days=2)
    await session.refresh(plan)
    assert plan.status == "cancelled"
    revision = (
        await session.execute(
            select(Notification).where(Notification.commitment_id == commitments[1].id)
        )
    ).scalars().one()
    assert revision.payload["type"] == "commitment_revision"


@pytest.mark.asyncio
@pytest.mark.integration
async def test_two_connections_same_extension_keep_secrets_isolated(session, mock_user):
    await _persist_user(session, mock_user)
    session.add(
        Extension(
            id="com.lifelog.canvas",
            version="1.0.0",
            config={"id": "com.lifelog.canvas", "version": "1.0.0"},
        )
    )
    await session.commit()
    first = SourceConnection(
        user_id=mock_user.id,
        extension_id="com.lifelog.canvas",
        name="School Canvas",
        config={},
    )
    second = SourceConnection(
        user_id=mock_user.id,
        extension_id="com.lifelog.canvas",
        name="Work Canvas",
        config={},
    )
    session.add(first)
    session.add(second)
    await session.flush()
    await set_source_secret(session, first.id, "access_token", "school-token")
    await set_source_secret(session, second.id, "access_token", "work-token")
    await session.commit()

    assert await get_source_secrets(session, first.id) == {"access_token": "school-token"}
    assert await get_source_secrets(session, second.id) == {"access_token": "work-token"}


@pytest.mark.asyncio
@pytest.mark.integration
async def test_rotate_secrets_reencrypts_and_bumps_version(async_client, session, mock_user):

    await _persist_user(session, mock_user)
    session.add(
        Extension(
            id="com.lifelog.canvas",
            version="1.0.0",
            config={"id": "com.lifelog.canvas", "version": "1.0.0"},
        )
    )
    await session.flush()
    connection = SourceConnection(
        user_id=mock_user.id,
        extension_id="com.lifelog.canvas",
        name="Canvas",
        config={},
    )
    session.add(connection)
    await session.flush()
    await set_source_secret(session, connection.id, "access_token", "very-secret-token")
    await session.commit()

    secret = (await session.execute(select(SourceSecret))).scalars().one()
    ciphertext_before = secret.ciphertext
    assert secret.key_version == 1

    response = await async_client.post(f"/api/v1/sources/{connection.id}/rotate-secrets")
    assert response.status_code == 204
    await session.refresh(secret)
    assert secret.key_version == 2
    assert secret.ciphertext != ciphertext_before
    assert await get_source_secrets(session, connection.id) == {
        "access_token": "very-secret-token"
    }


@pytest.mark.asyncio
@pytest.mark.unit
async def test_failure_redaction_masks_credentials(session):
    from app.services.failures import record_processing_failure, redact_sensitive

    assert "Bearer abc123" in redact_sensitive("called with Bearer abc123") or True
    redacted = redact_sensitive("GET https://x?api_key=super-secret failed: 401")
    assert "super-secret" not in redacted
    assert "[REDACTED]" in redacted
    redacted_bearer = redact_sensitive("Authorization: Bearer abc.def.ghi failed")
    assert "abc.def.ghi" not in redacted_bearer
    assert "[REDACTED]" in redacted_bearer

    failure = await record_processing_failure(
        session,
        source_type="test",
        source_id=None,
        stage="poller",
        error=RuntimeError("request failed with token=topsecret"),
    )
    assert "topsecret" not in failure.error_message
    assert "[REDACTED]" in failure.error_message
    assert "topsecret" not in failure.traceback


@pytest.mark.asyncio
@pytest.mark.integration
async def test_extensions_api_redacts_sensitive_config(async_client, session, mock_user):
    await _persist_user(session, mock_user)
    session.add(
        Extension(
            id="com.lifelog.legacy",
            version="1.0.0",
            config={"id": "com.lifelog.legacy", "version": "1.0.0", "api_key": "legacy-secret"},
        )
    )
    await session.commit()
    response = await async_client.get("/api/v1/extensions")
    assert response.status_code == 200
    body = response.json()
    legacy = next(item for item in body if item["id"] == "com.lifelog.legacy")
    assert legacy["config"]["api_key"] == "[REDACTED]"
    assert "legacy-secret" not in response.text
