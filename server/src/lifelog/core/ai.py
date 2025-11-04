"""
AI Service Layer for LifeLog

This module provides a unified interface for all AI-related operations, including embeddings and chat. It supports both remote and local providers, following the modular architecture.
"""

from typing import List, Optional
import asyncio
import httpx
import logging
from .config import settings
from .local_embedding import LocalEmbeddingProvider

logger = logging.getLogger(__name__)


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
        # Run sync embedding in a threadpool to avoid blocking the event loop
        vectors = await asyncio.to_thread(self.embedding_provider.embed, texts)
        usage_log_id = None
        # Log usage if session and actor/model info provided AND a provider exists
        if session and actor_id:
            from .. import models
            # Resolve provider from DB
            provider = None
            if provider_slug:
                from sqlmodel import select
                stmt = select(models.AIProvider).where(models.AIProvider.provider_slug == provider_slug)
                result = await session.exec(stmt)
                provider = result.one_or_none()
            # Only log usage when a concrete provider record exists to satisfy FK
            if provider and provider.id is not None:
                usage = models.AIUsageLog(
                    actor_id=actor_id,
                    ai_provider_id=provider.id,
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

    async def generate_completion(
        self,
        session,
        provider_slug: str,
        model: str,
        prompt: str,
        actor_id: Optional[int] = None,
        event_id: Optional[int] = None,
        temperature: float = 0.7,
        max_tokens: Optional[int] = None
    ) -> tuple[str, Optional[int]]:
        """
        Generate a completion using the configured LLM provider.
        
        Args:
            session: Database session for logging
            provider_slug: AI provider slug
            model: Model identifier (e.g., 'gpt-3.5-turbo', 'llama-3')
            prompt: The prompt text
            actor_id: Actor making the request
            event_id: Associated event ID (if any)
            temperature: Sampling temperature (0-1)
            max_tokens: Maximum tokens in response
        
        Returns:
            Tuple of (completion_text, usage_log_id)
        """
        from .. import models
        from sqlmodel import select
        
        # Resolve provider from DB
        provider = None
        if provider_slug:
            stmt = select(models.AIProvider).where(models.AIProvider.provider_slug == provider_slug)
            result = await session.exec(stmt)
            provider = result.one_or_none()
        
        # Use litellm endpoint if configured
        litellm_url = getattr(settings, "LITELLM_BASE_URL", "http://litellm:4000")
        
        try:
            # Call litellm API (OpenAI-compatible)
            async with httpx.AsyncClient(timeout=120.0) as client:
                response = await client.post(
                    f"{litellm_url}/chat/completions",
                    json={
                        "model": model,
                        "messages": [
                            {"role": "user", "content": prompt}
                        ],
                        "temperature": temperature,
                        "max_tokens": max_tokens
                    }
                )
                response.raise_for_status()
                data = response.json()
            
            # Extract completion
            completion_text = data["choices"][0]["message"]["content"]
            
            # Extract usage info
            usage_info = data.get("usage", {})
            prompt_tokens = usage_info.get("prompt_tokens")
            completion_tokens = usage_info.get("completion_tokens")
            
            # Estimate cost (rough approximation)
            # GPT-3.5-turbo: $0.0015 per 1K prompt tokens, $0.002 per 1K completion tokens
            cost = 0.0
            if prompt_tokens and completion_tokens:
                cost = (prompt_tokens * 0.0015 / 1000) + (completion_tokens * 0.002 / 1000)
            
            # Log usage
            usage_log_id = None
            if provider and provider.id is not None and actor_id:
                usage = models.AIUsageLog(
                    actor_id=actor_id,
                    ai_provider_id=provider.id,
                    event_id=event_id,
                    call_type="completion",
                    model_used=model,
                    prompt_tokens=prompt_tokens,
                    completion_tokens=completion_tokens,
                    cost=cost,
                )
                session.add(usage)
                await session.commit()
                await session.refresh(usage)
                usage_log_id = usage.id
            
            return completion_text, usage_log_id
            
        except httpx.HTTPStatusError as e:
            logger.error(f"LLM API error: {e.response.status_code} - {e.response.text}")
            raise ValueError(f"LLM API returned error: {e.response.status_code}")
        except Exception as e:
            logger.error(f"Failed to generate completion: {e}")
            raise

# Singleton instance
ai_service = AIService()
