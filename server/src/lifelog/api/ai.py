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
from ..services import AIConfigService

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
