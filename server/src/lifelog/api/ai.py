"""
Internal AI management API
- Manage AI defaults (embedding provider/model/dim)
- List and update providers
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlmodel.ext.asyncio.session import AsyncSession

from ..dependencies import get_session
from ..auth import require_auth
from .. import schemas
from .. import models
from ..services import AIConfigService, EmbeddingService
from sqlmodel import select
from typing import Optional

router = APIRouter(prefix="/ai", tags=["AI (Internal)"])


@router.get("/settings", response_model=schemas.AISettingsRead)
async def get_ai_settings(
    session: AsyncSession = Depends(get_session),
    current_user: str = Depends(require_auth),
):
    row = await AIConfigService.get_ai_settings(session)
    return schemas.AISettingsRead(
        default_embedding_provider_slug=row.default_embedding_provider_slug,
        default_embedding_model=row.default_embedding_model,
        default_embedding_dim=row.default_embedding_dim,
    )


@router.put("/settings", response_model=schemas.AISettingsRead)
async def update_ai_settings(
    update: schemas.AISettingsUpdate,
    session: AsyncSession = Depends(get_session),
    current_user: str = Depends(require_auth),
):
    row = await AIConfigService.update_ai_settings(
        session,
        default_embedding_provider_slug=update.default_embedding_provider_slug,
        default_embedding_model=update.default_embedding_model,
        default_embedding_dim=update.default_embedding_dim,
    )
    return schemas.AISettingsRead(
        default_embedding_provider_slug=row.default_embedding_provider_slug,
        default_embedding_model=row.default_embedding_model,
        default_embedding_dim=row.default_embedding_dim,
    )


@router.get("/providers", response_model=list[schemas.AIProviderRead])
async def list_providers(
    session: AsyncSession = Depends(get_session),
    current_user: str = Depends(require_auth),
):
    providers = await AIConfigService.list_providers(session)
    out: list[schemas.AIProviderRead] = []
    for p in providers:
        if p.id is None:
            continue
        out.append(
            schemas.AIProviderRead(
                id=p.id,
                name=p.name,
                provider_slug=p.provider_slug,
                model_type=p.model_type,
                provider_type=p.provider_type,
                model_path_or_uri=p.model_path_or_uri,
                is_active=p.is_active,
                config=p.config,
            )
        )
    return out


@router.patch("/providers/{provider_id}", response_model=schemas.AIProviderRead)
async def update_provider(
    provider_id: int,
    update: schemas.AIProviderUpdate,
    session: AsyncSession = Depends(get_session),
    current_user: str = Depends(require_auth),
):
    provider = await AIConfigService.update_provider(
        session,
        provider_id,
        name=update.name,
        model_path_or_uri=update.model_path_or_uri,
        is_active=update.is_active,
        config=update.config,
    )
    if not provider or provider.id is None:
        raise HTTPException(status_code=404, detail="Provider not found")
    return schemas.AIProviderRead(
        id=provider.id,
        name=provider.name,
        provider_slug=provider.provider_slug,
        model_type=provider.model_type,
        provider_type=provider.provider_type,
        model_path_or_uri=provider.model_path_or_uri,
        is_active=provider.is_active,
        config=provider.config,
    )


class TestEmbedRequest(schemas.BaseModel):  # type: ignore[attr-defined]
    texts: list[str]


@router.post("/test-embed")
async def test_embed(
    req: TestEmbedRequest,
    session: AsyncSession = Depends(get_session),
    current_user: str = Depends(require_auth),
):
    """Quickly test the embedding pipeline without touching the DB."""
    # Resolve defaults from DB settings or fall back to app settings
    db_settings = await AIConfigService.get_ai_settings(session)
    from ..core.config import settings as app_settings  # type: ignore
    provider_slug = (
        db_settings.default_embedding_provider_slug
        or getattr(app_settings, "DEFAULT_EMBEDDING_PROVIDER_SLUG", "local-bge")
    )
    model = (
        db_settings.default_embedding_model
        or getattr(app_settings, "DEFAULT_EMBEDDING_MODEL", "BAAI/bge-large-en-v1.5")
    )

    from ..core.ai import ai_service
    vectors, _usage = await ai_service.embed_texts(
        session,
        provider_slug=provider_slug,
        model=model,
        texts=req.texts,
    )
    # Return small preview for sanity plus dimension
    dim = len(vectors[0]) if vectors else 0
    preview = [v[:8] for v in vectors]
    return {"count": len(vectors), "dim": dim, "vectors_preview": preview}


class BackfillEmbeddingsRequest(schemas.BaseModel):  # type: ignore[attr-defined]
    limit: Optional[int] = 100
    since_minutes: Optional[int] = 1440  # default: last 24h


@router.post("/backfill-embeddings")
async def backfill_embeddings(
    req: BackfillEmbeddingsRequest,
    session: AsyncSession = Depends(get_session),
    current_user: str = Depends(require_auth),
):
    """Create embeddings for events that don't have one yet.

    - Scopes to recent events by default (last 24h)
    - Skips superseded events
    - Uses each event's processor_actor_id as the embedding actor_id
    """
    from datetime import datetime, timezone, timedelta
    from .. import models

    # Base query: recent, non-superseded events (embedding dedupe handled in service)
    stmt = select(models.Event).where(models.Event.superseded_by_event_id == None)  # noqa: E711
    if req.since_minutes and req.since_minutes > 0:
        cutoff = datetime.now(timezone.utc) - timedelta(minutes=req.since_minutes)
        stmt = stmt.where(models.Event.start_time > cutoff)

    # Note: We intentionally do not exclude already-embedded events here.
    # EmbeddingService.ensure_event_embedding is idempotent and will skip existing.
    if req.limit and req.limit > 0:
        stmt = stmt.limit(req.limit)

    result = await session.exec(stmt)
    events = list(result.all())

    created = 0
    for ev in events:
        if ev.id is None or ev.processor_actor_id is None:
            continue
        try:
            emb = await EmbeddingService.ensure_event_embedding(
                session,
                event_id=ev.id,
                actor_id=ev.processor_actor_id,
            )
            if emb:
                created += 1
        except Exception:
            # Continue on errors to process as many as possible
            continue

    return {"processed": len(events), "created": created}
