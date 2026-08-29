import uuid
from datetime import UTC, datetime
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import col, select

from app.core.database import get_session
from app.core.dependencies import get_current_user
from app.models.auth import User
from app.models.config import Extension
from app.models.sources import SourceCheckpoint, SourceConnection, SourceSecret
from app.services.context import get_owned_area, link_target
from app.services.extension_runtime import schedule_source_poller
from app.services.source_secrets import (
    list_source_secret_keys,
    reencrypt_source_secrets,
    set_source_secret,
)

router = APIRouter()
_SENSITIVE_CONFIG_KEYS = {
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


def _looks_sensitive(key: object) -> bool:
    normalized = str(key).strip().casefold().replace("-", "_")
    return normalized in _SENSITIVE_CONFIG_KEYS or normalized.endswith(
        ("_password", "_secret", "_token")
    )


def _validate_public_config(config: dict) -> None:
    def _walk(value: object, path: str = "config") -> None:
        if isinstance(value, dict):
            for key, nested in value.items():
                if _looks_sensitive(key):
                    raise HTTPException(
                        status_code=400,
                        detail=f"{path}.{key} looks sensitive; submit it through the secrets endpoint",
                    )
                _walk(nested, f"{path}.{key}")
        elif isinstance(value, list):
            for index, nested in enumerate(value):
                _walk(nested, f"{path}[{index}]")

    _walk(config)


class SourceConnectionCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    extension_id: str
    name: str = Field(min_length=1, max_length=200)
    config: dict = Field(default_factory=dict)
    schedule_cron: str | None = None
    secrets: dict[str, str] = Field(default_factory=dict)
    life_area_ids: list[uuid.UUID] = Field(default_factory=list)

    @field_validator("schedule_cron")
    @classmethod
    def validate_schedule(cls, value: str | None) -> str | None:
        if value:
            from apscheduler.triggers.cron import CronTrigger

            CronTrigger.from_crontab(value)
        return value


class SourceConnectionUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str | None = Field(default=None, min_length=1, max_length=200)
    config: dict | None = None
    schedule_cron: str | None = None
    is_active: bool | None = None

    @field_validator("schedule_cron")
    @classmethod
    def validate_schedule(cls, value: str | None) -> str | None:
        if value:
            from apscheduler.triggers.cron import CronTrigger

            CronTrigger.from_crontab(value)
        return value


class SourceConnectionResponse(BaseModel):
    id: uuid.UUID
    extension_id: str
    name: str
    config: dict
    schedule_cron: str | None
    status: str
    is_active: bool
    secret_keys: list[str]
    last_sync_started_at: datetime | None
    last_sync_completed_at: datetime | None
    last_sync_error: str | None
    created_at: datetime
    updated_at: datetime


class SecretValue(BaseModel):
    value: str = Field(min_length=1)


class SourceSyncResponse(BaseModel):
    connection_id: uuid.UUID
    status: Literal["queued"] = "queued"


async def _owned_connection(
    session: AsyncSession,
    connection_id: uuid.UUID,
    user: User,
) -> SourceConnection:
    connection = await session.get(SourceConnection, connection_id)
    if connection is None or connection.user_id != user.id:
        raise HTTPException(status_code=404, detail="Source connection not found")
    return connection


async def _response(session: AsyncSession, connection: SourceConnection) -> SourceConnectionResponse:
    return SourceConnectionResponse(
        **connection.model_dump(),
        secret_keys=await list_source_secret_keys(session, connection.id),
    )


def _apply_schedule(request: Request, connection: SourceConnection) -> None:
    scheduler = getattr(request.app.state, "scheduler", None)
    if scheduler is not None:
        schedule_source_poller(
            scheduler,
            connection,
            getattr(request.app.state, "arq_pool", None),
        )


@router.post("/sources", response_model=SourceConnectionResponse, status_code=status.HTTP_201_CREATED)
async def create_source_connection(
    body: SourceConnectionCreate,
    request: Request,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
) -> SourceConnectionResponse:
    extension = await session.get(Extension, body.extension_id)
    if extension is None or not extension.is_active:
        raise HTTPException(status_code=400, detail="Source adapter is not installed and active")
    _validate_public_config(body.config)
    connection = SourceConnection(
        user_id=user.id,
        extension_id=body.extension_id,
        name=body.name,
        config=body.config,
        schedule_cron=body.schedule_cron or extension.scheduler_cron,
    )
    session.add(connection)
    await session.flush()
    for area_id in body.life_area_ids:
        if await get_owned_area(session, area_id, user.id) is None:
            raise HTTPException(status_code=400, detail=f"Unknown Life Area: {area_id}")
        await link_target(session, area_id, "source_connection", connection.id, source="user")
    try:
        for key, value in body.secrets.items():
            await set_source_secret(session, connection.id, key, value)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    await session.commit()
    await session.refresh(connection)
    _apply_schedule(request, connection)
    return await _response(session, connection)


@router.get("/sources", response_model=list[SourceConnectionResponse])
async def list_source_connections(
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
) -> list[SourceConnectionResponse]:
    connections = (
        await session.execute(
            select(SourceConnection)
            .where(SourceConnection.user_id == user.id)
            .order_by(col(SourceConnection.created_at).desc())
        )
    ).scalars().all()
    return [await _response(session, connection) for connection in connections]


@router.get("/sources/{connection_id}", response_model=SourceConnectionResponse)
async def get_source_connection(
    connection_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
) -> SourceConnectionResponse:
    return await _response(session, await _owned_connection(session, connection_id, user))


@router.patch("/sources/{connection_id}", response_model=SourceConnectionResponse)
async def update_source_connection(
    connection_id: uuid.UUID,
    body: SourceConnectionUpdate,
    request: Request,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
) -> SourceConnectionResponse:
    connection = await _owned_connection(session, connection_id, user)
    if body.config is not None:
        _validate_public_config(body.config)
    for key, value in body.model_dump(exclude_unset=True).items():
        setattr(connection, key, value)
    connection.updated_at = datetime.now(UTC).replace(tzinfo=None)
    connection.status = "active" if connection.is_active else "paused"
    session.add(connection)
    await session.commit()
    await session.refresh(connection)
    _apply_schedule(request, connection)
    return await _response(session, connection)


@router.put("/sources/{connection_id}/secrets/{key}", status_code=status.HTTP_204_NO_CONTENT)
async def put_source_secret(
    connection_id: uuid.UUID,
    key: str,
    body: SecretValue,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
) -> None:
    await _owned_connection(session, connection_id, user)
    try:
        await set_source_secret(session, connection_id, key, body.value)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    await session.commit()


@router.delete("/sources/{connection_id}/secrets/{key}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_source_secret(
    connection_id: uuid.UUID,
    key: str,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
) -> None:
    await _owned_connection(session, connection_id, user)
    secret = (
        await session.execute(
            select(SourceSecret).where(
                SourceSecret.connection_id == connection_id,
                SourceSecret.key == key,
            )
        )
    ).scalars().first()
    if secret is not None:
        await session.delete(secret)
        await session.commit()


@router.post("/sources/{connection_id}/rotate-secrets", status_code=status.HTTP_204_NO_CONTENT)
async def rotate_source_secrets(
    connection_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
) -> None:
    """Re-encrypt all secrets under the current key material and bump key_version.

    Run before changing SOURCE_SECRET_KEY so old ciphertext can still be decrypted.
    """
    await _owned_connection(session, connection_id, user)
    await reencrypt_source_secrets(session, connection_id)
    await session.commit()


@router.delete("/sources/{connection_id}", status_code=status.HTTP_204_NO_CONTENT)
async def disconnect_source_connection(
    connection_id: uuid.UUID,
    request: Request,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
) -> None:
    connection = await _owned_connection(session, connection_id, user)
    connection.is_active = False
    connection.status = "disconnected"
    connection.updated_at = datetime.now(UTC).replace(tzinfo=None)
    session.add(connection)
    await session.commit()
    _apply_schedule(request, connection)


@router.post(
    "/sources/{connection_id}/sync",
    response_model=SourceSyncResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def sync_source_connection(
    connection_id: uuid.UUID,
    request: Request,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
) -> SourceSyncResponse:
    connection = await _owned_connection(session, connection_id, user)
    if not connection.is_active:
        raise HTTPException(status_code=409, detail="Source connection is paused")
    pool = getattr(request.app.state, "arq_pool", None)
    if pool is None:
        raise HTTPException(status_code=503, detail="Background worker queue is unavailable")
    await pool.enqueue_job(
        "task_poll_source",
        str(connection.id),
        _job_id=f"source-poll:{connection.id}",
    )
    return SourceSyncResponse(connection_id=connection.id)


@router.get("/sources/{connection_id}/checkpoints", response_model=list[SourceCheckpoint])
async def list_source_checkpoints(
    connection_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
) -> list[SourceCheckpoint]:
    await _owned_connection(session, connection_id, user)
    return list(
        (
            await session.execute(
                select(SourceCheckpoint).where(SourceCheckpoint.connection_id == connection_id)
            )
        ).scalars().all()
    )
