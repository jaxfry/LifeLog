"""Interactive, evidence-grounded LifeLog assistant harness."""

import json
import re
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from pydantic_ai import Agent, ModelRetry, RunContext, UsageLimits
from pydantic_ai.models.google import GoogleModel
from pydantic_ai.models.openai import OpenAIChatModel
from pydantic_ai.providers.google import GoogleProvider
from pydantic_ai.providers.openai import OpenAIProvider
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.accounting import AIUsage
from app.services.ai import ensure_ai_budget, estimate_model_cost
from app.services.model_router import ModelRole, model_router
from app.services.tools import execute_tool


@dataclass
class EvidenceLedger:
    citations: list[dict[str, Any]] = field(default_factory=list)

    def add_source(self, hit: dict[str, Any]) -> str:
        for citation in self.citations:
            if (
                citation.get("source_type") == hit.get("source_type")
                and citation.get("source_id") == hit.get("source_id")
            ):
                return citation["id"]
        marker = f"S{1 + sum(item['id'].startswith('S') for item in self.citations)}"
        self.citations.append({"id": marker, **hit})
        return marker

    def add_tool(self, name: str, arguments: dict[str, Any], result: dict[str, Any]) -> str:
        marker = f"T{1 + sum(item['id'].startswith('T') for item in self.citations)}"
        self.citations.append(
            {"id": marker, "tool": name, "arguments": arguments, "result": result}
        )
        return marker

    def add_fact(self, name: str, arguments: dict[str, Any], result: dict[str, Any]) -> str:
        marker = f"F{1 + sum(item['id'].startswith('F') for item in self.citations)}"
        self.citations.append(
            {"id": marker, "fact_tool": name, "arguments": arguments, "result": result}
        )
        return marker


@dataclass
class IntelligenceDeps:
    session: AsyncSession
    user_id: uuid.UUID
    area_id: uuid.UUID | None
    scope_name: str
    timezone: str
    history: list[tuple[str, str]]
    ledger: EvidenceLedger = field(default_factory=EvidenceLedger)


@dataclass
class IntelligenceResult:
    response: str
    citations: list[dict[str, Any]]
    tools_used: list[str]
    usage: dict[str, int]


INSTRUCTIONS = """You are LifeLog AI, the user's grounded assistant over their life.

LifeLog's tools are your memory. You have no personal facts until a tool returns
them. Search iteratively: broaden, narrow, inspect an entity, or calculate from
durable data as needed. Do not rely on a fixed recent context window.
Stop as soon as the evidence is sufficient. Do not inspect the graph after a
search merely to restate an already-grounded answer; use graph traversal only
when the question actually requires relationships or connected facts.

Rules:
- Cite every personal-memory claim with the exact [S#] marker returned by search.
- Cite accepted/current/historical facts with the exact [F#] marker returned by
  claim-history inspection.
- Cite every calculated or structural claim with the exact [T#] marker returned
  by a deterministic tool.
- Conversation history is continuity, never evidence.
- Clearly distinguish evidence, inference, advice, and uncertainty.
- If evidence is missing or conflicting, say so and explain what is missing.
- Never claim to have changed state. This assistant currently has read-only tools.
- Never invent citations, dates, totals, events, people, or completed actions.
- Answer naturally and directly; do not narrate tool mechanics unless useful.
"""


assistant_agent: Agent[IntelligenceDeps, str] = Agent(
    deps_type=IntelligenceDeps,
    output_type=str,
    instructions=INSTRUCTIONS,
)


@assistant_agent.instructions
async def runtime_context(ctx: RunContext[IntelligenceDeps]) -> str:
    now = datetime.now().astimezone().isoformat()
    history = "\n".join(f"{role.title()}: {content}" for role, content in ctx.deps.history)
    return (
        f"Current local datetime supplied by the server: {now}. User timezone: "
        f"{ctx.deps.timezone}. Active privacy/relevance scope: {ctx.deps.scope_name}.\n"
        "Conversation continuity (not evidence):\n"
        f"{history or 'No previous turns.'}"
    )


async def _run_read_tool(
    ctx: RunContext[IntelligenceDeps], name: str, arguments: dict[str, Any]
) -> dict[str, Any]:
    result = await execute_tool(
        ctx.deps.session,
        user_id=ctx.deps.user_id,
        area_id=ctx.deps.area_id,
        name=name,
        arguments=arguments,
    )
    if "error" in result:
        return result
    marker = ctx.deps.ledger.add_tool(name, arguments, result)
    return {"citation": f"[{marker}]", **result}


async def _run_fact_tool(
    ctx: RunContext[IntelligenceDeps], name: str, arguments: dict[str, Any]
) -> dict[str, Any]:
    result = await execute_tool(
        ctx.deps.session,
        user_id=ctx.deps.user_id,
        area_id=ctx.deps.area_id,
        name=name,
        arguments=arguments,
    )
    if "error" in result:
        return result
    marker = ctx.deps.ledger.add_fact(name, arguments, result)
    return {"citation": f"[{marker}]", **result}


@assistant_agent.tool
async def search_lifelog(
    ctx: RunContext[IntelligenceDeps], query: str, limit: int = 10
) -> dict[str, Any]:
    """Search the user's indexed lifetime memory. Refine the query if needed."""
    result = await execute_tool(
        ctx.deps.session,
        user_id=ctx.deps.user_id,
        area_id=ctx.deps.area_id,
        name="search_memories",
        arguments={"query": query, "limit": limit},
    )
    if "error" in result:
        return result
    cited_hits = []
    for hit in result.get("hits", []):
        marker = ctx.deps.ledger.add_source(hit)
        cited_hits.append({"citation": f"[{marker}]", **hit})
    return {"hits": cited_hits}


@assistant_agent.tool
async def inspect_entity_graph(
    ctx: RunContext[IntelligenceDeps],
    entity_name: str,
    entity_type: str | None = None,
    depth: int = 2,
    limit: int = 25,
) -> dict[str, Any]:
    """Inspect facts and relationships around one named entity."""
    arguments = {
        "entity_name": entity_name,
        "entity_type": entity_type,
        "depth": depth,
        "limit": limit,
    }
    return await _run_read_tool(ctx, "traverse_graph", arguments)


@assistant_agent.tool
async def calculate_recorded_duration(
    ctx: RunContext[IntelligenceDeps],
    predicate: str | None = None,
    entity_type: str | None = None,
    entity_name: str | None = None,
    occurred_from: datetime | None = None,
    occurred_until: datetime | None = None,
) -> dict[str, Any]:
    """Calculate exact recorded duration, optionally scoped to an entity and time range."""
    arguments = {
        "predicate": predicate,
        "entity_type": entity_type,
        "entity_name": entity_name,
        "occurred_from": occurred_from,
        "occurred_until": occurred_until,
    }
    return await _run_read_tool(ctx, "calculate_duration", arguments)


@assistant_agent.tool
async def summarize_measurements(
    ctx: RunContext[IntelligenceDeps],
    entity_type: str | None = None,
    entity_name: str | None = None,
    metric: str | None = None,
    occurred_from: datetime | None = None,
    occurred_until: datetime | None = None,
) -> dict[str, Any]:
    """Compute exact statistics for recorded numeric measurements such as sleep."""
    arguments = {
        "entity_type": entity_type,
        "entity_name": entity_name,
        "metric": metric,
        "occurred_from": occurred_from,
        "occurred_until": occurred_until,
    }
    return await _run_read_tool(ctx, "aggregate_measurements", arguments)


@assistant_agent.tool
async def compare_recorded_periods(
    ctx: RunContext[IntelligenceDeps],
    from_1: datetime,
    until_1: datetime,
    from_2: datetime,
    until_2: datetime,
    predicate: str | None = None,
    entity_type: str | None = None,
    entity_name: str | None = None,
) -> dict[str, Any]:
    """Compare exact recorded durations between two half-open time ranges."""
    arguments = {
        "from_1": from_1,
        "until_1": until_1,
        "from_2": from_2,
        "until_2": until_2,
        "predicate": predicate,
        "entity_type": entity_type,
        "entity_name": entity_name,
    }
    return await _run_read_tool(ctx, "compare_time_periods", arguments)


@assistant_agent.tool
async def plan_memory_query(
    ctx: RunContext[IntelligenceDeps], question: str
) -> dict[str, Any]:
    """Plan retrieval for a complex, ambiguous, longitudinal, or multi-part question."""
    return await execute_tool(
        ctx.deps.session,
        user_id=ctx.deps.user_id,
        area_id=ctx.deps.area_id,
        name="plan_query",
        arguments={"question": question},
    )


@assistant_agent.tool
async def inspect_exact_evidence(
    ctx: RunContext[IntelligenceDeps], source_id: uuid.UUID, limit: int = 12
) -> dict[str, Any]:
    """Inspect exact page/audio/text spans and locators behind a search result."""
    return await _run_read_tool(
        ctx,
        "inspect_evidence",
        {"source_id": source_id, "limit": limit},
    )


@assistant_agent.tool
async def inspect_memory_claims(
    ctx: RunContext[IntelligenceDeps],
    entity_name: str | None = None,
    entity_type: str | None = None,
    predicate: str | None = None,
    known_at: datetime | None = None,
    valid_at: datetime | None = None,
    limit: int = 20,
) -> dict[str, Any]:
    """Inspect grounded fact history, contradictions, validity, and source evidence."""
    return await _run_fact_tool(
        ctx,
        "inspect_claim_history",
        {
            "entity_name": entity_name,
            "entity_type": entity_type,
            "predicate": predicate,
            "known_at": known_at,
            "valid_at": valid_at,
            "limit": limit,
        },
    )


@assistant_agent.tool
async def list_open_deadlines(
    ctx: RunContext[IntelligenceDeps],
    due_from: datetime | None = None,
    due_until: datetime | None = None,
    limit: int = 20,
) -> dict[str, Any]:
    """List the user's exact current open commitments and deadlines."""
    return await _run_read_tool(
        ctx,
        "list_deadlines",
        {"due_from": due_from, "due_until": due_until, "limit": limit},
    )


@assistant_agent.tool
async def inspect_commitment_work(
    ctx: RunContext[IntelligenceDeps], commitment_title: str
) -> dict[str, Any]:
    """Inspect deterministic progress observations for one commitment."""
    return await _run_read_tool(
        ctx,
        "inspect_commitment_progress",
        {"commitment_title": commitment_title},
    )


@assistant_agent.tool
async def find_schedule_conflicts(
    ctx: RunContext[IntelligenceDeps],
    occurred_from: datetime,
    occurred_until: datetime,
) -> dict[str, Any]:
    """Find exact overlaps among the user's existing plan blocks."""
    return await _run_read_tool(
        ctx,
        "find_scheduling_conflicts",
        {"occurred_from": occurred_from, "occurred_until": occurred_until},
    )


@assistant_agent.tool
async def inspect_source_revisions(
    ctx: RunContext[IntelligenceDeps], external_key: str
) -> dict[str, Any]:
    """Inspect when an owner-scoped connected source changed or corrected a record."""
    return await _run_read_tool(
        ctx,
        "resolve_source_history",
        {"external_key": external_key},
    )


@assistant_agent.tool
async def inspect_data_coverage(
    ctx: RunContext[IntelligenceDeps],
    occurred_from: datetime,
    occurred_until: datetime,
) -> dict[str, Any]:
    """Check whether LifeLog had source coverage before interpreting an absence."""
    return await _run_read_tool(
        ctx,
        "inspect_coverage",
        {"occurred_from": occurred_from, "occurred_until": occurred_until},
    )


@assistant_agent.output_validator
async def validate_citations(ctx: RunContext[IntelligenceDeps], output: str) -> str:
    known = {f"[{item['id']}]" for item in ctx.deps.ledger.citations}
    words = output.replace("(", " ").replace(")", " ").split()
    mentioned = {
        word.rstrip(".,;:!?")
        for word in words
        if word.startswith(("[S", "[F", "[T"))
    }
    unknown = mentioned - known
    if unknown:
        raise ModelRetry(f"Use only citations returned by tools. Unknown: {sorted(unknown)}")
    if known and not any(marker in output for marker in known):
        raise ModelRetry("Cite the relevant returned [S#], [F#], or [T#] markers.")
    unsupported = []
    for sentence in re.split(r"(?<=[.!?])\s+|\n+", output):
        cleaned = sentence.strip()
        if len(cleaned.split()) < 3 or any(marker in cleaned for marker in known):
            continue
        if _requires_personal_citation(cleaned, ctx.deps.ledger.citations):
            unsupported.append(cleaned[:160])
    if unsupported:
        raise ModelRetry(
            "Every sentence asserting a personal fact needs its supporting marker. "
            f"Uncited: {unsupported[:3]}"
        )
    return output


def _requires_personal_citation(
    sentence: str,
    citations: list[dict[str, Any]],
) -> bool:
    """Conservatively distinguish personal assertions from standalone advice."""
    lowered = sentence.casefold()
    advisory = bool(
        re.search(r"\b(you (?:could|should|might|can)|consider|try|one option)\b", lowered)
    )
    evidence_language = bool(
        re.search(
            r"\b(your|you (?:did|were|had|have|spent|studied|slept|said|told|missed|completed)|"
            r"lifelog recorded|the records?|the evidence|according to)\b",
            lowered,
        )
    )
    if evidence_language:
        return True

    corpus = json.dumps(citations, default=str, ensure_ascii=False).casefold()
    stopwords = {
        "about",
        "after",
        "again",
        "could",
        "from",
        "have",
        "might",
        "should",
        "their",
        "there",
        "these",
        "they",
        "this",
        "those",
        "with",
        "would",
    }
    sentence_terms = {
        token
        for token in re.findall(r"[a-z0-9][a-z0-9_-]{3,}", lowered)
        if token not in stopwords
    }
    overlap = {term for term in sentence_terms if term in corpus}
    factual_verb = bool(
        re.search(
            r"\b(was|were|did|worked|studied|slept|said|told|went|recorded|spent|"
            r"completed|missed|seemed|felt|happened|started|ended|changed)\b",
            lowered,
        )
    )
    number_or_date = bool(re.search(r"\b\d+(?::\d+|[-/]\d+)?\b", sentence))
    if advisory and not factual_verb and not number_or_date and len(overlap) < 2:
        return False
    return factual_verb or number_or_date or len(overlap) >= 2


def _configured_model() -> tuple[Any, str, str]:
    deployment = model_router.require(ModelRole.ASSISTANT)[0]
    if deployment.provider in {"openrouter", "opencode_zen", "hackclub"}:
        model_name = deployment.model.removeprefix("openrouter/").removeprefix("openai/")
        return (
            OpenAIChatModel(
                model_name,
                provider=OpenAIProvider(
                    base_url=deployment.api_base,
                    api_key=deployment.api_key,
                ),
            ),
            deployment.provider,
            model_name,
        )
    if deployment.provider == "gemini":
        model_name = deployment.model.removeprefix("gemini/")
        model = GoogleModel(model_name, provider=GoogleProvider(api_key=deployment.api_key))
        return model, deployment.provider, model_name
    raise RuntimeError(f"Unsupported assistant deployment provider: {deployment.provider}")


async def run_interactive_assistant(
    *,
    session: AsyncSession,
    user_id: uuid.UUID,
    area_id: uuid.UUID | None,
    scope_name: str,
    timezone: str,
    history: list[tuple[str, str]],
    message: str,
) -> IntelligenceResult:
    deps = IntelligenceDeps(
        session=session,
        user_id=user_id,
        area_id=area_id,
        scope_name=scope_name,
        timezone=timezone,
        history=history,
    )
    await ensure_ai_budget(session, owner_user_id=user_id)
    model, provider, model_name = _configured_model()
    started = time.monotonic()
    result = await assistant_agent.run(
        message,
        model=model,
        deps=deps,
        model_settings={"max_tokens": settings.ASSISTANT_MAX_OUTPUT_TOKENS},
        usage_limits=UsageLimits(
            request_limit=settings.ASSISTANT_MAX_REQUESTS,
            tool_calls_limit=settings.ASSISTANT_MAX_TOOL_CALLS,
            total_tokens_limit=settings.ASSISTANT_MAX_TOTAL_TOKENS,
        ),
    )
    usage = result.usage
    session.add(
        AIUsage(
            owner_user_id=user_id,
            operation="interactive_assistant",
            data={"life_area_id": str(area_id) if area_id else None, "tool_calls": usage.tool_calls},
            provider=provider,
            model=model_name,
            input_tokens=usage.input_tokens or 0,
            output_tokens=usage.output_tokens or 0,
            cost=estimate_model_cost(
                provider,
                model_name,
                usage.input_tokens or 0,
                usage.output_tokens or 0,
            ),
            latency_ms=int((time.monotonic() - started) * 1000),
        )
    )
    return IntelligenceResult(
        response=result.output,
        citations=deps.ledger.citations,
        tools_used=[item["tool"] for item in deps.ledger.citations if "tool" in item],
        usage={
            "requests": usage.requests,
            "tool_calls": usage.tool_calls,
            "input_tokens": usage.input_tokens or 0,
            "output_tokens": usage.output_tokens or 0,
        },
    )
