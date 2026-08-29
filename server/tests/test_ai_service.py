from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.models.accounting import AIUsage
from app.services import ai


@pytest.mark.asyncio
@pytest.mark.unit
async def test_call_llm_rejects_empty_provider_response(monkeypatch):
    monkeypatch.setattr(
        ai,
        "_PROVIDERS",
        [{"model": "openai/test-model", "api_key": "test-key"}],
    )
    response = SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content="   "))],
        usage=SimpleNamespace(prompt_tokens=10, completion_tokens=1024),
    )
    monkeypatch.setattr(ai.litellm, "acompletion", AsyncMock(return_value=response))

    with pytest.raises(RuntimeError, match="empty response"):
        await ai.call_llm(None, "system", "user")


@pytest.mark.unit
def test_hackclub_usage_is_not_reported_as_a_user_charge():
    assert ai._estimate_cost("hackclub", 1_000_000, 1_000_000) == 0
    assert ai._estimate_cost("openai", 1_000_000, 1_000_000) == pytest.approx(7.5)


@pytest.mark.asyncio
@pytest.mark.integration
async def test_owner_daily_budget_applies_to_all_model_entry_points(
    session,
    mock_user,
    monkeypatch,
):
    session.add(
        AIUsage(
            owner_user_id=mock_user.id,
            provider="test",
            model="test",
            cost=1.0,
        )
    )
    await session.commit()
    monkeypatch.setattr(ai.settings, "AI_DAILY_BUDGET_USD", 1.0)

    with pytest.raises(RuntimeError, match="Daily AI budget reached"):
        await ai.ensure_ai_budget(session, owner_user_id=mock_user.id)
