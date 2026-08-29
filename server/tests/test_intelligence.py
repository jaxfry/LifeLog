from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from pydantic_ai.messages import ModelResponse, TextPart, ToolCallPart
from pydantic_ai.models.function import AgentInfo, FunctionModel

from app.services.intelligence import (
    EvidenceLedger,
    IntelligenceDeps,
    _configured_model,
    _requires_personal_citation,
    assistant_agent,
)


def test_openrouter_is_primary_provider(monkeypatch):
    monkeypatch.setattr(
        "app.services.intelligence.settings.OPENROUTER_API_KEY", "test-openrouter-key"
    )
    monkeypatch.setattr(
        "app.services.intelligence.settings.OPENCODE_ZEN_API_KEY", "test-opencode-key"
    )
    monkeypatch.setattr(
        "app.services.intelligence.settings.HACK_CLUB_AI_API_KEY", "test-hackclub-key"
    )

    _model, provider, model_name = _configured_model()

    assert provider == "openrouter"
    assert model_name == "deepseek/deepseek-v4-flash"


def test_evidence_ledger_reuses_marker_for_same_source():
    ledger = EvidenceLedger()
    hit = {"source_type": "timeline", "source_id": "memory-id", "content": "Study"}

    assert ledger.add_source(hit) == "S1"
    assert ledger.add_source(hit) == "S1"
    assert len(ledger.citations) == 1


def test_personal_clause_validator_distinguishes_fact_from_general_advice():
    citations = [
        {
            "id": "S1",
            "source_type": "transcript",
            "source_id": "one",
            "content": "Jerry said the deadline moved to Friday.",
        }
    ]

    assert _requires_personal_citation("Jerry said the deadline moved.", citations)
    assert not _requires_personal_citation(
        "You could ask for clarification next time.",
        citations,
    )


@pytest.mark.asyncio
@pytest.mark.unit
async def test_agent_can_iteratively_search_and_cite(mock_user):
    calls = 0

    async def model_function(_messages, _info: AgentInfo) -> ModelResponse:
        nonlocal calls
        calls += 1
        if calls == 1:
            return ModelResponse(
                parts=[
                    ToolCallPart(
                        "search_lifelog",
                        {"query": "calculus class", "limit": 5},
                    )
                ]
            )
        return ModelResponse(parts=[TextPart("You studied derivatives [S1].")])

    tool_result = {
        "hits": [
            {
                "source_type": "timeline",
                "source_id": "memory-id",
                "title": "Calculus class",
                "content": "Studied derivatives",
                "occurred_at": "2026-08-20T10:00:00",
                "score": 0.9,
            }
        ]
    }
    deps = IntelligenceDeps(
        session=MagicMock(),
        user_id=mock_user.id,
        area_id=None,
        scope_name="Whole life",
        timezone="America/Vancouver",
        history=[],
    )
    with patch("app.services.intelligence.execute_tool", AsyncMock(return_value=tool_result)):
        result = await assistant_agent.run(
            "What did I study?",
            deps=deps,
            model=FunctionModel(model_function),
        )

    assert result.output == "You studied derivatives [S1]."
    assert calls == 2
    assert deps.ledger.citations[0]["id"] == "S1"


@pytest.mark.asyncio
@pytest.mark.unit
async def test_agent_retries_unknown_citation(mock_user):
    calls = 0

    async def model_function(_messages, _info: AgentInfo) -> ModelResponse:
        nonlocal calls
        calls += 1
        text = "Unsupported personal claim [S99]." if calls == 1 else "I do not have evidence yet."
        return ModelResponse(parts=[TextPart(text)])

    deps = IntelligenceDeps(
        session=MagicMock(),
        user_id=mock_user.id,
        area_id=None,
        scope_name="Whole life",
        timezone="UTC",
        history=[],
    )
    result = await assistant_agent.run(
        "Tell me something",
        deps=deps,
        model=FunctionModel(model_function),
    )

    assert result.output == "I do not have evidence yet."
    assert calls == 2
