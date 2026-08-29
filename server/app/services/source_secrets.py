import base64
import hashlib
import re
import uuid
from datetime import UTC, datetime

from cryptography.fernet import Fernet, InvalidToken
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from app.core.config import settings
from app.models.sources import SourceSecret

_SECRET_KEY_PATTERN = re.compile(r"^[A-Za-z][A-Za-z0-9_.-]{0,199}$")


def _cipher() -> Fernet:
    material = settings.SOURCE_SECRET_KEY or settings.SECRET_KEY
    key = base64.urlsafe_b64encode(hashlib.sha256(material.encode("utf-8")).digest())
    return Fernet(key)


async def set_source_secret(
    session: AsyncSession,
    connection_id: uuid.UUID,
    key: str,
    plaintext: str,
) -> SourceSecret:
    normalized_key = key.strip()
    if not _SECRET_KEY_PATTERN.fullmatch(normalized_key):
        raise ValueError("secret key must start with a letter and contain only letters, digits, ._-")
    secret = (
        await session.execute(
            select(SourceSecret).where(
                SourceSecret.connection_id == connection_id,
                SourceSecret.key == normalized_key,
            )
        )
    ).scalars().first()
    now = datetime.now(UTC).replace(tzinfo=None)
    if secret is None:
        secret = SourceSecret(connection_id=connection_id, key=normalized_key, ciphertext=b"")
    secret.ciphertext = _cipher().encrypt(plaintext.encode("utf-8"))
    secret.updated_at = now
    session.add(secret)
    await session.flush()
    return secret


async def get_source_secrets(
    session: AsyncSession,
    connection_id: uuid.UUID,
) -> dict[str, str]:
    records = (
        await session.execute(
            select(SourceSecret).where(SourceSecret.connection_id == connection_id)
        )
    ).scalars().all()
    result: dict[str, str] = {}
    for record in records:
        try:
            result[record.key] = _cipher().decrypt(record.ciphertext).decode("utf-8")
        except InvalidToken as exc:
            raise RuntimeError(f"Unable to decrypt source secret {record.key!r}") from exc
    return result


async def list_source_secret_keys(
    session: AsyncSession,
    connection_id: uuid.UUID,
) -> list[str]:
    return list(
        (
            await session.execute(
                select(SourceSecret.key)
                .where(SourceSecret.connection_id == connection_id)
                .order_by(SourceSecret.key)
            )
        ).scalars().all()
    )


_SENSITIVE_KEYS = {
    "api_key",
    "authorization",
    "client_secret",
    "credential",
    "credentials",
    "password",
    "refresh_token",
    "secret",
    "token",
    "access_token",
}


def _is_sensitive_key(key: object) -> bool:
    normalized = str(key).strip().casefold().replace("-", "_")
    return normalized in _SENSITIVE_KEYS or normalized.endswith(("_password", "_secret", "_token"))


def redact_config(config: dict) -> dict:
    """Mask sensitive-looking values in a config dict for API responses."""

    def _walk(value: object) -> object:
        if isinstance(value, dict):
            return {
                key: "[REDACTED]"
                if _is_sensitive_key(key)
                else _walk(nested)
                for key, nested in value.items()
            }
        if isinstance(value, list):
            return [_walk(item) for item in value]
        return value

    return _walk(config)  # type: ignore[return-value]


async def reencrypt_source_secrets(
    session: AsyncSession,
    connection_id: uuid.UUID,
) -> int:
    """Re-encrypt every secret under the current key material.

    Rotate the stored key_version so a later key change is auditable. Run this
    before changing SOURCE_SECRET_KEY so old ciphertext can still be decrypted.
    """
    records = (
        await session.execute(
            select(SourceSecret).where(SourceSecret.connection_id == connection_id)
        )
    ).scalars().all()
    for record in records:
        plaintext = _cipher().decrypt(record.ciphertext)
        record.ciphertext = _cipher().encrypt(plaintext)
        record.key_version += 1
        record.updated_at = datetime.now(UTC).replace(tzinfo=None)
        session.add(record)
    await session.flush()
    return len(records)
