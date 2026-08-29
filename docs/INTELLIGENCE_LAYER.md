# LifeLog Intelligence Layer

## Status

This document is the normative design for LifeLog intelligence. The first
implementation phase covers the interactive assistant only. Autonomous or
scheduled background intelligence is deliberately deferred until the
interactive harness, evaluation suite, cost controls, and reconciliation
semantics have proved reliable.

## Governing principles

1. LifeLog's evidence stores and deterministic services are authoritative. A
   model may interpret evidence and propose changes; it is never a shadow
   database or an authority merely because it produced fluent text.
2. Chat and any future background workflows must use the same owner-scoped
   tools, policies, evidence ledger, prompts, and model routing.
3. AI cost must scale with meaningful questions and information changes, not
   with raw event volume.
4. Personal claims require traceable evidence. Calculations and state changes
   use deterministic base services.
5. Every run is bounded by permitted tools, model requests, tool calls, tokens,
   time, and scope.
6. Consequential writes require an explicit policy decision or user approval.
   Interactive investigation is read-only by default.

## Interactive assistant

The assistant uses a bounded iterative tool loop rather than a fixed context
dump or one-shot tool planner:

```text
interpret question and conversation
        -> retrieve or calculate with typed LifeLog tools
        -> inspect results and refine if necessary
        -> determine evidence sufficiency and conflicts
        -> synthesize a cited answer
        -> validate citations and budgets
```

The model may decide that a greeting or general explanation needs no memory.
Any answer about the user's life must first inspect LifeLog evidence. A Life
Area is a privacy and relevance scope, not a separate assistant or memory.

The base tool surface is capability-oriented:

- temporal interpretation and bounded memory search;
- primary-evidence retrieval and graph inspection;
- duration and measurement aggregation;
- commitments, progress, availability, conflicts, and read-only plan simulation
  once those records carry enforceable per-user ownership;
- evidence coverage and contradiction inspection;
- separately approved proposals and actions in a later phase.

Tools enforce ownership and disclosure policy internally. The model never gets
raw SQL, unrestricted filesystem access, arbitrary server shell access, source
secrets, or unbounded query results.

The exposed interactive tools are owner-scoped memory search, typed query
planning, exact evidence inspection, accepted/conflicting claim history, entity
graph inspection, duration and measurement aggregation, period comparison,
deadlines, commitment progress, scheduling conflicts, source revision history,
and evidence coverage. The assistant may inspect deterministic plan simulations,
but mutating plan/action tools are not registered with the interactive agent.
Consequential writes remain reviewable proposals outside the read-only harness.

Search candidates are owner-filtered before lexical/vector ranking and before
graph expansion. Citation targets distinguish source evidence (`[S#]`), accepted
or historical facts (`[F#]`), and deterministic tool results (`[T#]`). Output
validation rejects unknown markers and personal factual sentences without a
supporting marker.

## Model policy

Model choice is an operator policy, not a user-facing context-window control.
LifeLog should prefer deterministic code, then a cheap capable model, and only
escalate for genuine ambiguity or difficult synthesis. Provider selection must
remain portable. Each run records the operation, provider, model, token usage,
latency, prompt/tool versions, and scope without placing secrets in traces.

The implemented router selects by role and modality: assistant, vision,
transcription, extraction, resolution, summarization, embedding, reranking, or
general. Preservation and lexical indexing do not depend on model readiness.
Fallbacks, timeouts, short circuit breaking, owner-scoped usage, cache-version
keys, and an optional daily owner budget bound interactive and enrichment work.

## Deferred background intelligence

There is no free-running agent that browses the user's life or invents work.
Future background intelligence, if enabled, will be a sparse layer on top of a
deterministic reconciliation engine.

LifeLog assumes permanently asynchronous arrival. Records distinguish when an
observation occurred, when a source observed it, and when the server received
it. Late evidence marks bounded time/entity windows dirty. It does not trigger
an immediate model call.

Immediate work remains deterministic: preservation, hashing, deduplication,
normalization, indexing, explicit-context propagation, structured mappings,
coverage tracking, dependency invalidation, and batching. Dirty windows
accumulate until a quiet period, user request, consequential change, or other
materiality rule justifies synthesis.

Derived episodes and summaries are versioned projections with evidence
dependency fingerprints. Late data can supersede them without mutating source
truth. An information-delta gate compares new evidence, changed structured
fields, affected identities, temporal coverage, and the prior dependency hash.
Equivalent inputs reuse the existing result.

An AI background run will require all of the following:

- a typed trigger and concrete purpose;
- an owner, privacy scope, and idempotency key;
- material new information;
- a permitted tool set and read/write policy;
- request, token, cost, concurrency, and time budgets;
- an inspectable evidence set and stopping condition.

Likely future run types include capture assimilation, episode reconciliation,
commitment revision review, progress investigation, replanning, and daily or
weekly consolidation. These are event-driven or scheduled bounded workflows,
not continuous autonomous thought.

## Cost hierarchy

Work should stop at the cheapest sufficient level:

1. store and deduplicate;
2. deterministically normalize and link;
3. index lexically;
4. batch embeddings;
5. apply deterministic mappings and calculations;
6. use a small model for classification or extraction;
7. use multi-source synthesis only for material changes or user demand;
8. use a stronger model only when ambiguity or evaluation warrants it.

Daily background budgets, minimum intervals between equivalent work, cached
dependency hashes, and automatic suspension after repeated low-value results
are prerequisites for any future background phase.

## Framework boundary

LifeLog uses Pydantic AI for typed interactive agent execution and selected
generic harness capabilities where they are useful. LifeLog owns the domain
run contract, tools, memory, policy, evidence ledger, and evaluations. Generic
agent memory must never replace the provenance-backed LifeLog memory graph.

Durable background execution is intentionally not selected or installed in the
interactive phase. A Postgres-backed workflow system such as DBOS may be
evaluated later behind the LifeLog run contract; adopting it must not authorize
background autonomy.
