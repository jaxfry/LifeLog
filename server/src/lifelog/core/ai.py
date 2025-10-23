"""
AI Service Layer for LifeLog

This module provides a unified interface for all AI-related operations, including embeddings and chat. It supports both remote and local providers, following the modular architecture.
"""

from typing import List, Optional
from .config import settings
from .local_embedding import LocalEmbeddingProvider

class AIService:
    def __init__(self):
        self.embedding_provider = LocalEmbeddingProvider(model_name=settings.DEFAULT_EMBEDDING_MODEL)
        # Future: add chat provider, remote providers, etc.

    async def embed_texts(
        self,
        session,
        provider_slug: str,
        model: str,
        texts: List[str],
        actor_id: Optional[int] = None,
        event_id: Optional[int] = None,
    ) -> tuple[List[List[float]], Optional[int]]:
        """
        Embed texts using the configured provider and log usage.
        Returns (vectors, usage_log_id)
        """
        # Only support local embedding for now
        vectors = self.embedding_provider.embed(texts)
        usage_log_id = None
        # Log usage if session and actor/model info provided
        if session and actor_id:
            from .. import models
            # Resolve provider from DB
            provider = None
            if provider_slug:
                from sqlmodel import select
                stmt = select(models.AIProvider).where(models.AIProvider.provider_slug == provider_slug)
                result = await session.exec(stmt)
                provider = result.one_or_none()
            provider_id = provider.id if provider else 1  # fallback to 1 if not found
            usage = models.AIUsageLog(
                actor_id=actor_id,
                ai_provider_id=provider_id,
                event_id=event_id,
                call_type="embedding",
                model_used=model,
                prompt_tokens=None,
                completion_tokens=None,
                cost=0.0,
            )
            session.add(usage)
            await session.commit()
            await session.refresh(usage)
            usage_log_id = usage.id
        return vectors, usage_log_id

# Singleton instance
ai_service = AIService()
