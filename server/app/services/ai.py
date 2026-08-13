import json
import time
from typing import Any, Union

import litellm
import tiktoken
from openai import AsyncOpenAI
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.logger import get_logger
from app.models.accounting import AIUsage

logger = get_logger(__name__)

_PROVIDERS: list[dict[str, Any]] = []

UserPrompt = Union[str, list[dict[str, Any]]]


def _build_providers():
    global _PROVIDERS
    providers = []
    if settings.OPENCODE_ZEN_API_KEY:
        providers.append({
            "model": f"openai/{settings.OPENCODE_ZEN_MODEL}",
            "api_key": settings.OPENCODE_ZEN_API_KEY,
            "api_base": settings.OPENCODE_ZEN_BASE_URL,
        })
    if settings.HACK_CLUB_AI_API_KEY:
        providers.append({
            "model": settings.LITELLM_MODEL,
            "api_key": settings.HACK_CLUB_AI_API_KEY,
            "api_base": settings.HACK_CLUB_AI_BASE_URL,
        })
    elif settings.GEMINI_API_KEY:
        providers.append({
            "model": settings.LITELLM_MODEL,
            "api_key": settings.GEMINI_API_KEY,
        })
    providers.append({
        "model": "gemini/gemini-2.0-flash-lite",
        "api_key": settings.GEMINI_API_KEY,
    })
    _PROVIDERS = providers


HACK_CLUB_EMBEDDING_MODEL = "qwen/qwen3-embedding-8b"
HACK_CLUB_BASE_URL = "https://ai.hackclub.com/proxy/v1"


async def embedding_with_fallback(text: str) -> list[float]:
    """
    Generates embedding using Hack Club (Qwen) as primary.
    """
    hc_key = settings.HACK_CLUB_AI_API_KEY
    if not hc_key:
        raise Exception("HACK_CLUB_AI_API_KEY required for Qwen embeddings.")

    try:
        client = AsyncOpenAI(
            api_key=hc_key,
            base_url=HACK_CLUB_BASE_URL,
        )

        response = await client.embeddings.create(
            model=HACK_CLUB_EMBEDDING_MODEL,
            input=[text],
        )

        embedding = response.data[0].embedding
        if len(embedding) > 768:
            logger.info(f"Slicing embedding from {len(embedding)} to 768")
            embedding = embedding[:768]

        return embedding

    except Exception as e:
        logger.error(f"Hack Club embedding failed: {e}")
        raise e


def count_tokens(text: str, model: str = "gpt-4") -> int:
    try:
        enc = tiktoken.encoding_for_model(model)
        return len(enc.encode(text))
    except Exception:
        return len(text) // 4


async def call_llm(
    db_session: AsyncSession | None,
    system_prompt: str,
    user_prompt: UserPrompt,
    session_context: dict | None = None,
    cache_key: str | None = None,
    model_override: str | None = None,
    max_tokens: int = 1024,
) -> str:
    if not _PROVIDERS:
        _build_providers()

    if cache_key and settings.LLM_CACHE_ENABLED:
        try:
            from app.services.cache import get_cached_response

            cached = await get_cached_response(cache_key)
            if cached is not None:
                logger.info("LLM cache hit for %s", cache_key)
                return cached
        except Exception:
            pass

    last_error: Exception | None = None
    start = time.monotonic()

    for provider in _PROVIDERS:
        model = model_override or provider["model"]
        try:
            response = await litellm.acompletion(
                model=model,
                api_key=provider.get("api_key"),
                api_base=provider.get("api_base"),
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                temperature=0.3,
                max_tokens=max_tokens,
            )

            elapsed_ms = int((time.monotonic() - start) * 1000)
            content = response.choices[0].message.content or ""
            usage = getattr(response, "usage", None)

            prompt_text = _prompt_to_text(system_prompt, user_prompt)
            input_tokens = usage.prompt_tokens if usage else count_tokens(prompt_text)
            output_tokens = usage.completion_tokens if usage else count_tokens(content)

            provider_name = model.split("/")[0] if "/" in model else "unknown"

            if db_session is not None:
                usage_record = AIUsage(
                    operation=(session_context or {}).get("operation"),
                    source_file_id=(session_context or {}).get("source_file_id"),
                    source_event_id=(session_context or {}).get("source_event_id"),
                    data=(session_context or {}).get("data", {}),
                    provider=provider_name,
                    model=model,
                    input_tokens=input_tokens,
                    output_tokens=output_tokens,
                    cost=_estimate_cost(provider_name, input_tokens, output_tokens),
                    latency_ms=elapsed_ms,
                )
                db_session.add(usage_record)
                await db_session.flush()

            if cache_key and settings.LLM_CACHE_ENABLED:
                try:
                    from app.services.cache import set_cached_response

                    await set_cached_response(cache_key, content)
                except Exception:
                    pass

            logger.info(
                "LLM call: model=%s input=%d output=%d latency=%dms",
                model,
                input_tokens,
                output_tokens,
                elapsed_ms,
            )
            return content

        except Exception as exc:
            last_error = exc
            logger.warning("Provider %s failed: %s", model, exc)
            continue

    raise RuntimeError(f"All LLM providers failed. Last error: {last_error}") from last_error


async def transcribe_audio(file_path: str, language: str | None = None) -> str:
    """Transcribe audio through LiteLLM's provider-neutral transcription API."""
    if not _PROVIDERS:
        _build_providers()
    last_error: Exception | None = None
    for provider in _PROVIDERS:
        try:
            with open(file_path, "rb") as audio_file:
                response = await litellm.atranscription(
                    model=settings.TRANSCRIPTION_MODEL,
                    file=audio_file,
                    language=language,
                    api_key=provider.get("api_key"),
                    api_base=provider.get("api_base"),
                )
            return str(response.text)
        except Exception as exc:
            last_error = exc
            logger.warning("Transcription provider failed: %s", exc)
    raise RuntimeError(f"All transcription providers failed. Last error: {last_error}") from last_error


def _prompt_to_text(system_prompt: str, user_prompt: UserPrompt) -> str:
    if isinstance(user_prompt, str):
        return system_prompt + user_prompt
    return system_prompt + json.dumps(user_prompt, default=str)


def _estimate_cost(provider: str, input_tokens: int, output_tokens: int) -> float:
    rates = {
        "gemini": {"input": 0.000000075, "output": 0.000000300},
        "openai": {"input": 0.000001500, "output": 0.000006000},
    }
    rate = rates.get(provider, rates["openai"])
    return (input_tokens * rate["input"] + output_tokens * rate["output"]) / 1000
