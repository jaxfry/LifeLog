import time
from typing import Any, Optional

import litellm
import tiktoken
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.logger import get_logger
from app.models.accounting import AIUsage

logger = get_logger(__name__)

_PROVIDERS: list[dict[str, Any]] = []


def _build_providers():
    global _PROVIDERS
    providers = []
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


def count_tokens(text: str, model: str = "gpt-4") -> int:
    try:
        enc = tiktoken.encoding_for_model(model)
        return len(enc.encode(text))
    except Exception:
        return len(text) // 4


async def call_llm(
    db_session: AsyncSession,
    system_prompt: str,
    user_prompt: str,
    session_context: Optional[dict] = None,
    cache_key: Optional[str] = None,
    model_override: Optional[str] = None,
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

    last_error: Optional[Exception] = None
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
                max_tokens=1024,
            )

            elapsed_ms = int((time.monotonic() - start) * 1000)
            content = response.choices[0].message.content or ""
            usage = getattr(response, "usage", None)

            input_tokens = usage.prompt_tokens if usage else count_tokens(system_prompt + user_prompt)
            output_tokens = usage.completion_tokens if usage else count_tokens(content)

            provider_name = model.split("/")[0] if "/" in model else "unknown"

            usage_record = AIUsage(
                provider=provider_name,
                model=model,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                cost=_estimate_cost(provider_name, input_tokens, output_tokens),
                latency_ms=elapsed_ms,
            )
            db_session.add(usage_record)
            await db_session.commit()

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


def _estimate_cost(provider: str, input_tokens: int, output_tokens: int) -> float:
    rates = {
        "gemini": {"input": 0.000000075, "output": 0.000000300},
        "openai": {"input": 0.000001500, "output": 0.000006000},
    }
    rate = rates.get(provider, rates["openai"])
    return (input_tokens * rate["input"] + output_tokens * rate["output"]) / 1000
