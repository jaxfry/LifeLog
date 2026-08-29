import hashlib
import json
import time
import uuid
from datetime import UTC, datetime
from typing import Any, Union

import litellm
import tiktoken
from openai import AsyncOpenAI
from sqlalchemy import func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from app.core.config import settings
from app.core.logger import get_logger
from app.models.accounting import AIUsage
from app.services.model_router import ModelRole, model_router

logger = get_logger(__name__)

_PROVIDERS: list[dict[str, Any]] = []  # Explicit compatibility/test override.
_CIRCUITS: dict[tuple[str, str], tuple[int, float]] = {}

UserPrompt = Union[str, list[dict[str, Any]]]


def _build_providers(role: ModelRole = ModelRole.GENERAL) -> list[dict[str, Any]]:
    return [deployment.as_litellm_provider() for deployment in model_router.require(role)]


def _provider_candidates(role: ModelRole) -> list[dict[str, Any]]:
    return _PROVIDERS or _build_providers(role)


async def embedding_with_fallback(text: str) -> list[float]:
    """Generate one embedding through the capability router."""
    embeddings = await embeddings_with_fallback([text])
    return embeddings[0]


async def embeddings_with_fallback(texts: list[str]) -> list[list[float]]:
    """Generate a batch of recall embeddings in one provider request."""
    last_error: Exception | None = None
    for deployment in model_router.require(ModelRole.EMBEDDING):
        try:
            client = AsyncOpenAI(
                api_key=deployment.api_key,
                base_url=deployment.api_base,
            )
            model = (
                deployment.model.removeprefix("openrouter/")
                if deployment.provider == "openrouter"
                else deployment.model.removeprefix("openai/")
            )
            response = await client.embeddings.create(model=model, input=texts)
            ordered = sorted(response.data, key=lambda item: item.index)
            dimensions = deployment.embedding_dimensions or settings.EMBEDDING_DIMENSIONS
            return [item.embedding[:dimensions] for item in ordered]
        except Exception as exc:
            last_error = exc
            logger.warning(
                "Embedding deployment %s/%s failed: %s",
                deployment.provider,
                deployment.model,
                exc,
            )
    raise RuntimeError(f"All embedding deployments failed. Last error: {last_error}") from last_error


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
    response_format: dict[str, Any] | None = None,
    role: ModelRole = ModelRole.GENERAL,
) -> str:
    if db_session is not None:
        await ensure_ai_budget(
            db_session,
            owner_user_id=(session_context or {}).get("owner_user_id"),
        )
    last_error: Exception | None = None
    start = time.monotonic()

    for provider in _provider_candidates(role):
        model = model_override or provider["model"]
        circuit_key = (str(provider.get("provider_name") or "unknown"), model)
        failures, open_until = _CIRCUITS.get(circuit_key, (0, 0.0))
        if open_until > time.monotonic():
            logger.info("Skipping temporarily unhealthy deployment %s/%s", *circuit_key)
            continue
        effective_cache_key = _versioned_cache_key(
            cache_key,
            role=role,
            provider=str(provider.get("provider_name") or "unknown"),
            model=model,
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            response_format=response_format,
        )
        if effective_cache_key and settings.LLM_CACHE_ENABLED:
            try:
                from app.services.cache import get_cached_response

                cached = await get_cached_response(effective_cache_key)
                if cached is not None:
                    logger.info("LLM cache hit for %s", effective_cache_key)
                    return cached
            except Exception:
                pass
        try:
            # Reasoning models consume completion tokens before emitting visible text.
            # A generic 1K ceiling can therefore yield a successful but empty answer.
            effective_max_tokens = max(max_tokens, 4096) if "deepseek" in model.casefold() else max_tokens
            completion_kwargs: dict[str, Any] = {
                "model": model,
                "api_key": provider.get("api_key"),
                "api_base": provider.get("api_base"),
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                "temperature": 0.3,
                "max_tokens": effective_max_tokens,
                "timeout": provider.get("timeout_seconds", settings.AI_REQUEST_TIMEOUT_SECONDS),
            }
            if response_format is not None:
                completion_kwargs["response_format"] = response_format
            response = await litellm.acompletion(
                **completion_kwargs,
            )

            elapsed_ms = int((time.monotonic() - start) * 1000)
            content = response.choices[0].message.content or ""
            if not content.strip():
                raise RuntimeError(
                    f"Provider {model} returned an empty response; "
                    "the completion may have exhausted its token budget while reasoning"
                )
            usage = getattr(response, "usage", None)

            prompt_text = _prompt_to_text(system_prompt, user_prompt)
            input_tokens = usage.prompt_tokens if usage else count_tokens(prompt_text)
            output_tokens = usage.completion_tokens if usage else count_tokens(content)

            provider_name = provider.get("provider_name") or (
                "hackclub"
                if provider.get("api_base") == settings.HACK_CLUB_AI_BASE_URL
                else (model.split("/")[0] if "/" in model else "unknown")
            )

            if db_session is not None:
                usage_record = AIUsage(
                    owner_user_id=(session_context or {}).get("owner_user_id"),
                    operation=(session_context or {}).get("operation"),
                    source_file_id=(session_context or {}).get("source_file_id"),
                    source_event_id=(session_context or {}).get("source_event_id"),
                    data=(session_context or {}).get("data", {}),
                    provider=provider_name,
                    model=model,
                    input_tokens=input_tokens,
                    output_tokens=output_tokens,
                    cost=_response_cost(response, provider_name, input_tokens, output_tokens),
                    latency_ms=elapsed_ms,
                )
                db_session.add(usage_record)
                await db_session.flush()

            if effective_cache_key and settings.LLM_CACHE_ENABLED:
                try:
                    from app.services.cache import set_cached_response

                    await set_cached_response(effective_cache_key, content)
                except Exception:
                    pass

            logger.info(
                "LLM call: model=%s input=%d output=%d latency=%dms",
                model,
                input_tokens,
                output_tokens,
                elapsed_ms,
            )
            _CIRCUITS.pop(circuit_key, None)
            return content

        except Exception as exc:
            last_error = exc
            failures += 1
            _CIRCUITS[circuit_key] = (
                failures,
                time.monotonic() + 60.0 if failures >= 3 else 0.0,
            )
            logger.warning("Provider %s failed: %s", model, exc)
            continue

    raise RuntimeError(f"All LLM providers failed. Last error: {last_error}") from last_error


async def ensure_ai_budget(
    session: AsyncSession,
    *,
    owner_user_id: uuid.UUID | str | None,
) -> None:
    """Reject optional AI work after an owner's configured daily spend is exhausted."""
    if settings.AI_DAILY_BUDGET_USD is None or owner_user_id is None:
        return
    day_start = datetime.now(UTC).replace(
        hour=0,
        minute=0,
        second=0,
        microsecond=0,
        tzinfo=None,
    )
    spent = await session.scalar(
        select(func.coalesce(func.sum(AIUsage.cost), 0.0)).where(
            AIUsage.owner_user_id == owner_user_id,
            AIUsage.created_at >= day_start,
        )
    )
    if float(spent or 0.0) >= settings.AI_DAILY_BUDGET_USD:
        raise RuntimeError("Daily AI budget reached; preserved data remains available")


async def transcribe_audio(file_path: str, language: str | None = None) -> str:
    """Transcribe audio through LiteLLM's provider-neutral transcription API."""
    last_error: Exception | None = None
    for provider in _provider_candidates(ModelRole.TRANSCRIPTION):
        try:
            with open(file_path, "rb") as audio_file:
                response = await litellm.atranscription(
                    model=provider["model"],
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


def _versioned_cache_key(
    base_key: str | None,
    *,
    role: ModelRole,
    provider: str,
    model: str,
    system_prompt: str,
    user_prompt: UserPrompt,
    response_format: dict[str, Any] | None,
) -> str | None:
    if base_key is None:
        return None
    contract = json.dumps(
        {
            "role": role.value,
            "provider": provider,
            "model": model,
            "prompt": _prompt_to_text(system_prompt, user_prompt),
            "response_format": response_format,
        },
        sort_keys=True,
        default=str,
        separators=(",", ":"),
    )
    return f"{base_key}:v2:{hashlib.sha256(contract.encode()).hexdigest()[:24]}"


def _estimate_cost(provider: str, input_tokens: int, output_tokens: int) -> float:
    # Rates are USD per million tokens. Hack Club access is free to the user;
    # do not present an upstream proxy estimate as money they were charged.
    rates = {
        "hackclub": {"input": 0.0, "output": 0.0},
        "gemini": {"input": 0.075, "output": 0.30},
        "openai": {"input": 1.50, "output": 6.00},
    }
    rate = rates.get(provider)
    if rate is None:
        return 0.0
    return (input_tokens * rate["input"] + output_tokens * rate["output"]) / 1_000_000


def estimate_model_cost(
    provider: str,
    model: str,
    input_tokens: int,
    output_tokens: int,
) -> float:
    """Use LiteLLM's current model catalogue when provider metadata lacks actual cost."""
    if provider in {"hackclub", "opencode_zen"}:
        return 0.0
    model_name = f"openrouter/{model}" if provider == "openrouter" else model
    try:
        input_cost, output_cost = litellm.cost_per_token(
            model=model_name,
            prompt_tokens=input_tokens,
            completion_tokens=output_tokens,
        )
        return max(0.0, float(input_cost or 0.0) + float(output_cost or 0.0))
    except Exception:
        return _estimate_cost(provider, input_tokens, output_tokens)


def _response_cost(
    response: Any,
    provider: str,
    input_tokens: int,
    output_tokens: int,
) -> float:
    hidden = getattr(response, "_hidden_params", None) or {}
    actual = hidden.get("response_cost")
    if isinstance(actual, (int, float)) and actual >= 0:
        return float(actual)
    return _estimate_cost(provider, input_tokens, output_tokens)
