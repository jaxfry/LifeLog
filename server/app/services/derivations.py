import hashlib
import json
import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import col, select

from app.models.intelligence import DerivationAttempt, DerivationRun


def _now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def fingerprint(value: Any) -> str:
    canonical = json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(canonical.encode()).hexdigest()


async def start_derivation(
    session: AsyncSession,
    *,
    owner_user_id: uuid.UUID,
    purpose: str,
    target_type: str,
    target_id: uuid.UUID,
    inputs: Any,
    processor: str,
    processor_version: str,
    prompt_version: str | None = None,
    ontology_version: str | None = None,
    model_role: str | None = None,
    provider: str | None = None,
    model: str | None = None,
    policy_snapshot: dict[str, Any] | None = None,
    budget_snapshot: dict[str, Any] | None = None,
) -> tuple[DerivationRun, DerivationAttempt, bool]:
    """Start or resume one idempotent derivation and append an attempt."""
    input_fingerprint = fingerprint(inputs)
    derivation_key = fingerprint(
        {
            "purpose": purpose,
            "target_type": target_type,
            "target_id": target_id,
            "input_fingerprint": input_fingerprint,
            "processor": processor,
            "processor_version": processor_version,
            "prompt_version": prompt_version,
            "ontology_version": ontology_version,
            "model_role": model_role,
            "provider": provider,
            "model": model,
        }
    )
    run = (
        await session.execute(
            select(DerivationRun).where(
                DerivationRun.owner_user_id == owner_user_id,
                DerivationRun.derivation_key == derivation_key,
            )
        )
    ).scalar_one_or_none()
    if run is not None and run.status == "completed":
        return run, DerivationAttempt(derivation_run_id=run.id, attempt=0, status="skipped"), False
    if run is None:
        run = DerivationRun(
            owner_user_id=owner_user_id,
            purpose=purpose,
            target_type=target_type,
            target_id=target_id,
            derivation_key=derivation_key,
            input_fingerprint=input_fingerprint,
            processor=processor,
            processor_version=processor_version,
            prompt_version=prompt_version,
            ontology_version=ontology_version,
            model_role=model_role,
            provider=provider,
            model=model,
            policy_snapshot=policy_snapshot or {},
            budget_snapshot=budget_snapshot or {},
        )
        session.add(run)
        await session.flush()
    maximum = (
        await session.execute(
            select(DerivationAttempt.attempt)
            .where(DerivationAttempt.derivation_run_id == run.id)
            .order_by(col(DerivationAttempt.attempt).desc())
            .limit(1)
        )
    ).scalar_one_or_none()
    attempt = DerivationAttempt(
        derivation_run_id=run.id,
        attempt=(maximum or 0) + 1,
        status="running",
    )
    run.status = "running"
    run.started_at = _now()
    run.completed_at = None
    session.add(run)
    session.add(attempt)
    await session.flush()
    return run, attempt, True


async def complete_derivation(
    session: AsyncSession,
    run: DerivationRun,
    attempt: DerivationAttempt,
    *,
    output_refs: dict[str, Any] | None = None,
) -> None:
    completed_at = _now()
    run.status = "completed"
    run.completed_at = completed_at
    run.output_refs = {**run.output_refs, **(output_refs or {})}
    attempt.status = "completed"
    attempt.completed_at = completed_at
    session.add(run)
    session.add(attempt)
    await session.flush()


async def fail_derivation(
    session: AsyncSession,
    run: DerivationRun,
    attempt: DerivationAttempt,
    error: Exception,
) -> None:
    completed_at = _now()
    run.status = "failed"
    run.completed_at = completed_at
    attempt.status = "failed"
    attempt.error_type = type(error).__name__
    attempt.error_message = _safe_error(error)
    attempt.completed_at = completed_at
    session.add(run)
    session.add(attempt)
    await session.flush()


def _safe_error(error: Exception) -> str:
    message = str(error)
    if len(message) > 1000:
        message = message[:1000] + "…"
    # Derivation errors are diagnostics, not a place to persist provider keys.
    for prefix in ("sk-", "Bearer "):
        if prefix in message:
            message = message.split(prefix, 1)[0] + "[REDACTED]"
    return message
