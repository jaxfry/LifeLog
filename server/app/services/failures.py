import re
import traceback
import uuid
from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from app.models.retrieval import ProcessingFailure

_SENSITIVE_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"(?i)(bearer\s+)[a-z0-9._~+/=-]+"), r"\1[REDACTED]"),
    (re.compile(r"(?i)(api[_-]?key[=:]\s*)\S+"), r"\1[REDACTED]"),
    (re.compile(r"(?i)(access[_-]?token[=:]\s*)\S+"), r"\1[REDACTED]"),
    (re.compile(r"(?i)(refresh[_-]?token[=:]\s*)\S+"), r"\1[REDACTED]"),
    (re.compile(r"(?i)(token[=:]\s*)\S+"), r"\1[REDACTED]"),
    (re.compile(r"(?i)(password[=:]\s*)\S+"), r"\1[REDACTED]"),
    (re.compile(r"(?i)(secret[=:]\s*)\S+"), r"\1[REDACTED]"),
    (re.compile(r"(?i)(authorization[=:]\s*)\S+"), r"\1[REDACTED]"),
]


def redact_sensitive(text: str | None) -> str | None:
    """Mask credential-shaped strings; defense in depth against secret leakage."""
    if not text:
        return text
    for pattern, replacement in _SENSITIVE_PATTERNS:
        text = pattern.sub(replacement, text)
    return text


async def record_processing_failure(
    session: AsyncSession,
    *,
    source_type: str,
    source_id: uuid.UUID | None,
    stage: str,
    error: Exception,
    context: dict | None = None,
) -> ProcessingFailure:
    existing = (
        await session.execute(
            select(ProcessingFailure).where(
                ProcessingFailure.source_type == source_type,
                ProcessingFailure.source_id == source_id,
                ProcessingFailure.stage == stage,
                ProcessingFailure.status == "open",
            )
        )
    ).scalars().first()
    failure = existing or ProcessingFailure(
        source_type=source_type,
        source_id=source_id,
        stage=stage,
        error_type=type(error).__name__,
        error_message=str(error),
    )
    if existing:
        failure.attempts += 1
    failure.error_type = type(error).__name__
    failure.error_message = redact_sensitive(str(error)) or str(error)
    failure.traceback = redact_sensitive("".join(traceback.format_exception(error)))[-20_000:]
    failure.context = context or {}
    failure.last_failed_at = datetime.now(UTC).replace(tzinfo=None)
    session.add(failure)
    await session.flush()
    return failure
