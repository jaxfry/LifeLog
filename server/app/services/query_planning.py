import re
from enum import StrEnum

from pydantic import BaseModel, Field


class QueryIntent(StrEnum):
    AGGREGATE = "aggregate_or_comparison"
    COMMITMENT = "commitment_or_planning"
    CONTRADICTION = "contradiction_or_coverage"
    DIRECT_EVIDENCE = "direct_evidence"
    ENTITY_GRAPH = "entity_relationship"
    LONGITUDINAL = "longitudinal_synthesis"
    REFLECTIVE = "reflective_or_advice"
    TEMPORAL = "temporal_reconstruction"


class QueryPlan(BaseModel):
    intents: list[QueryIntent]
    retrieval_steps: list[str]
    needs_primary_evidence: bool = True
    needs_deterministic_computation: bool = False
    evidence_budget: int = Field(default=12, ge=1, le=40)
    explanation: str


def plan_query(question: str) -> QueryPlan:
    """Cheap deterministic intent hints; service policy remains authoritative."""
    text = question.casefold()
    intents: list[QueryIntent] = []
    if re.search(r"\b(how much|total|average|compare|trend|change|over the past)\b", text):
        intents.append(QueryIntent.AGGREGATE)
    if re.search(r"\b(deadline|due|assignment|plan|schedule|conflict|what should i do)\b", text):
        intents.append(QueryIntent.COMMITMENT)
    if re.search(r"\b(last|yesterday|today|week|month|when|between|during|on monday|on tuesday)\b", text):
        intents.append(QueryIntent.TEMPORAL)
    if re.search(r"\b(connected|relationship|who is|what is|related|with [A-Z])\b", question):
        intents.append(QueryIntent.ENTITY_GRAPH)
    if re.search(r"\b(conflict|contradict|do you have data|coverage|missing|source)\b", text):
        intents.append(QueryIntent.CONTRADICTION)
    if re.search(r"\b(over time|long.term|lifetime|months|years|pattern|theme)\b", text):
        intents.append(QueryIntent.LONGITUDINAL)
    if re.search(r"\b(should i|how should|advice|could i|why do i)\b", text):
        intents.append(QueryIntent.REFLECTIVE)
    if not intents:
        intents.append(QueryIntent.DIRECT_EVIDENCE)
    intents = list(dict.fromkeys(intents))
    steps = ["hybrid_recall"]
    if QueryIntent.TEMPORAL in intents:
        steps.append("time_filtered_evidence")
    if QueryIntent.ENTITY_GRAPH in intents:
        steps.append("owner_scoped_graph")
    if QueryIntent.AGGREGATE in intents:
        steps.append("deterministic_aggregate")
    if QueryIntent.COMMITMENT in intents:
        steps.append("commitment_state")
    if QueryIntent.CONTRADICTION in intents:
        steps.append("claim_and_source_history")
    return QueryPlan(
        intents=intents,
        retrieval_steps=steps,
        needs_deterministic_computation=QueryIntent.AGGREGATE in intents,
        evidence_budget=20 if QueryIntent.LONGITUDINAL in intents else 12,
        explanation="Intent hints select bounded LifeLog tools; they do not grant access or mutate state.",
    )
