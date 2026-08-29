# LifeLog Intelligence and Memory Upgrade Plan

## Status and purpose

This is the implementation plan for upgrading the current LifeLog codebase into
a trustworthy, lifelong intelligence system. It translates the existing product
model and assistant design into an incremental code plan informed by Graphiti,
Neo4j GraphRAG, Microsoft GraphRAG, LightRAG, Google LangExtract, Docling,
WhisperX, LiteLLM, durable-workflow systems, and modern LLM evaluation practice.

This is not a rewrite and not a move to Neo4j. LifeLog remains a self-hosted
Python modular monolith using PostgreSQL/pgvector, FastAPI, SQLModel, ARQ, Redis,
LiteLLM, and Pydantic AI. Database changes, backfills, and compatibility code are
implementation mechanics inside the upgrade, not a separate product migration.

### Implementation snapshot (2026-08-28)

The first production-shaped slice of this plan is now implemented. This table is
the authoritative status summary; the phase descriptions below remain the full
acceptance criteria, including work that still requires fixtures, infrastructure,
or a real longitudinal pilot.

| Area | Status | Implemented now | Still required |
| --- | --- | --- | --- |
| Explicit ownership | Implemented | Owner identity is carried through raw logs, events, sessions, timeline, summaries, files, commitments, actions, relations, measurements, usage, and recall candidates. Legacy read/search/analytics paths filter before returning candidates. | Run the PostgreSQL backfill against a production copy and inspect quarantined ambiguous rows. |
| Model harness | Implemented core | Capability roles, compatible deployment selection, fallbacks, timeouts, circuit breaking, versioned cache keys, redacted readiness, per-owner accounting, and optional daily budgets. | Calibrate provider price/capability metadata and add load/concurrency policy from real deployments. |
| Evidence and claims | Implemented core | Versioned `EvidenceDocument`/`EvidenceSpan`, exact locators, claim/mention/evidence ledgers, deterministic projection claims, dual-write compatibility, derivation lineage, and recall indexing. | Layout-aware Docling fixtures and time/speaker-aligned transcription adapters remain to be integrated and evaluated. |
| Ontology and identity | Implemented conservative core | A bounded core ontology, compatible manifest contributions, exact owner/type/alias resolution, durable decisions, rejected-pair constraints, and review for ambiguity. | Fuzzy/vector/context candidate generation is intentionally disabled until a labelled precision corpus exists. |
| Reconciliation | Implemented core | Owner-scoped corroboration/conflict handling, many-to-many fact evidence, valid-time and knowledge-time queries, grouped review, and coalesced dirty scopes. | Complete source-removal support accounting and projection invalidation for every legacy projection. |
| Recall and assistant | Implemented core | Owner filtering before lexical/vector ranking, separate span/claim source types, typed query planning, exact evidence/history/coverage tools, deterministic aggregate/action-state tools, typed citations, clause-level citation checks, and a read-only bounded agent. | Version embeddings independently, add evaluated reranking/diversity, and build the complete question-family evaluation set. |
| Durable stage DAG | Partial | Existing versioned `ProcessingJob` stages, append-only derivation attempts, idempotent keys, ARQ execution, progressive capture state, DLQ, and degradation-safe lexical preservation. | Transactional outbox, per-page/window fan-out, leases/heartbeats, and independent retry of one failed span/window. |
| Longitudinal consolidation | Schema only | `MemorySummary` and `DirtyScope` persistence contracts exist. | Summary generation is deliberately deferred; no free-running background agent has been added. |
| Evaluation and pilot | Partial | Unit/integration ownership, grounding, identity, reconciliation, query-planning, citation, and migration checks exist. | PostgreSQL/pgvector execution, fixture corpora, quality thresholds, cost/load tests, and several weeks of messy real use remain release gates. |

Migrations `013`–`017` introduce the new evidence/claim/lineage records and carry
explicit ownership through memory and recall. They form one Alembic head and
compile for PostgreSQL. A live PostgreSQL upgrade is still required before a
production deployment because a local database service was not available during
this implementation pass.

The normative product boundaries remain:

- [PRODUCT_MODEL.md](PRODUCT_MODEL.md): Capabilities, Sources, and Life Areas;
- [INTELLIGENCE_LAYER.md](INTELLIGENCE_LAYER.md): one bounded, evidence-grounded
  assistant and deterministic reconciliation before background intelligence;
- [architecture.md](architecture.md): modular-monolith and source-truth rules.

## Outcome

After this plan is complete, LifeLog will be able to:

1. Preserve photos, documents, recordings, notes, source records, and sensor data
   as immutable evidence.
2. Produce layout-aware documents and time-aligned, speaker-aware transcripts.
3. Extract typed claims whose support points to exact text, page regions, audio
   intervals, source records, or normalized events.
4. Resolve identities conservatively across sources and time without merging
   people or concepts merely because their names are similar.
5. Represent both when a fact was true and when LifeLog learned it, preserving
   corrections, contradictions, and late-arriving evidence.
6. Distinguish source assertions, canonical facts, deterministic projections,
   model inferences, user confirmations, and advice.
7. Retrieve the right combination of primary evidence, current facts, historical
   facts, graph structure, deterministic calculations, and higher-level summaries.
8. Answer specific, temporal, relational, aggregate, reflective, planning, and
   whole-life questions with inspectable citations and honest uncertainty.
9. Reprocess safely when models, prompts, parsers, ontology, or source data change.
10. Measure extraction quality, retrieval quality, answer faithfulness, latency,
    and cost before promoting a change.

## Current baseline to preserve

The current code already provides useful foundations. The upgrade must build on,
not discard, these capabilities:

- immutable `RawLog` ingestion and stable `SourceRecord` revisions;
- universal `Capture`, resumable uploads, and content-addressed attachments;
- normalized `Event` records and logical-date sessionization;
- versioned `ProcessingJob` records and ARQ worker entry points;
- `ContentChunk`, `MemoryProposal`, `Entity`, `Relation`, `Measurement`, and
  commitment projections;
- entity aliases, source identities, reversible user-approved merges, and
  supersession history;
- a rebuildable `SearchDocument` projection with lexical and vector recall;
- Life Area context links and purpose-aware memory policies;
- one review Inbox for consequential ambiguity;
- a bounded Pydantic AI assistant with typed, owner-scoped read tools and an
  evidence ledger.

The principal limitations are architectural, not a lack of tables:

- artifact processing is a long, mostly sequential orchestration path;
- PDFs lose important layout, tables, reading order, and coordinates;
- transcripts are currently plain text without reliable segments, speakers, or
  word timestamps;
- extracted output moves too directly from chunk-level model output into graph
  entities, relations, and commitments;
- evidence grounding is normalized substring matching rather than durable spans;
- LLM self-reported confidence drives promotion despite not being calibrated;
- entity matching lacks semantic/contextual candidate generation and a durable
  resolution-decision record;
- relations combine source assertion and accepted graph fact into one structure;
- temporal validity and knowledge time are incomplete and inconsistent across
  entities, relations, commitments, summaries, and source revisions;
- predicates and entity types are syntactically constrained but not governed by
  an explicit, versioned ontology;
- model routing is provider-first rather than operation/capability-first;
- embedding configuration is tied to one provider and one hard-coded model;
- broad longitudinal synthesis has no versioned consolidation projection;
- evaluation currently proves code behavior, not memory or answer quality;
- several legacy records still lack explicit owner identity, limiting safe tool
  exposure and multi-user correctness.

## Non-negotiable architecture decisions

### 1. Evidence is immutable; intelligence is derived

Original bytes, source envelopes, normalized events, and user-authored text are
evidence. Claims, entities, facts, timelines, summaries, plans, and search indexes
are versioned derivations. Reprocessing creates or supersedes derivations; it
does not mutate the original evidence.

### 2. Source assertions and canonical memory are separate

An extracted statement is not immediately a canonical fact. The system first
records a grounded claim. Resolution and reconciliation decide whether that claim
supports, revises, disputes, or merely coexists with current memory.

### 3. Time is bi-temporal

LifeLog records at least:

- `occurred_at` or `valid_from`/`valid_until`: when something happened or was true;
- `observed_at`: when the source or device observed it, when available;
- `received_at`: when the server received the evidence;
- `learned_at`: when a derived claim/fact became part of LifeLog memory;
- `invalidated_at`: when LifeLog learned the derivation was no longer current.

Late evidence may revise current understanding without rewriting what LifeLog
previously knew.

### 4. One graph, multiple typed projections

PostgreSQL remains the authoritative store. `Relation`, `Measurement`,
`Commitment`, timeline, and summary records remain purpose-built projections.
A claim layer supplies their shared evidence and reconciliation semantics. Life
Areas organize this shared memory without creating separate graphs.

### 5. AI proposes and disambiguates; policy promotes

The model may extract, classify, rank candidates, explain conflicts, and
synthesize answers. Deterministic policy validates schemas, verifies evidence,
computes promotion scores, applies ownership/privacy, performs calculations, and
decides whether human review is required.

### 6. No free-running background agent

New or late evidence marks bounded time/entity scopes dirty. Deterministic jobs
reconcile those scopes. Model calls happen only for a typed purpose, material
information delta, explicit user request, or scheduled consolidation that passes
budgets. There is no continuous autonomous process “thinking about the user.”

### 7. Adopt concepts selectively

- Adopt Graphiti's episode provenance, temporal validity, fact invalidation, and
  incremental reconciliation semantics.
- Adopt Neo4j GraphRAG's staged schema/extraction/resolution pipeline, not its
  database requirement.
- Adopt LangExtract's exact-span grounding, chunk parallelism, and optional
  multi-pass recall strategy.
- Integrate Docling behind a LifeLog document-parser interface after fixture
  validation.
- Integrate WhisperX as an optional self-hosted transcript backend behind a
  provider-neutral interface.
- Adopt Microsoft GraphRAG community summaries only as a sparse, versioned
  consolidation projection.
- Adopt LightRAG's detail/concept retrieval split and incremental-update ideas,
  not a second memory store.
- Use LiteLLM routing for model deployments while LifeLog owns role policy,
  privacy, lineage, and budgets.
- Keep ARQ initially; borrow durable-workflow semantics before deciding whether
  DBOS adds enough value to justify another runtime.

## Target data flow

```text
source record / note / photo / PDF / recording / sensor batch
                            |
                            v
                 immutable evidence preserved
                            |
                            v
              modality-specific normalization
         document structure / transcript / typed event
                            |
                +-----------+-----------+
                |                       |
                v                       v
          searchable spans       deterministic mappings
                |                       |
                +-----------+-----------+
                            v
                  typed claim extraction
                            |
                  exact grounding checks
                            |
                  entity mention resolution
                            |
             temporal/contradiction reconciliation
                            |
      +---------------------+------------------------+
      |                     |                        |
      v                     v                        v
 canonical graph      commitments/metrics       review Inbox
      |                     |                        |
      +---------------------+------------------------+
                            v
             recall projections and dirty scopes
                            |
             assistant tools / sparse consolidation
                            |
                 cited answer or safe proposal
```

## Target persistence model

Names may be adjusted during implementation, but responsibilities must remain
separate.

### Ownership and time additions

Add explicit `user_id`/`owner_user_id` to every user-memory record that can be
retrieved or acted upon, including attachments, sessions, timeline entries,
daily summaries, relations, measurements, commitments, progress, plan blocks,
notifications, and processing jobs. Remove fallbacks that infer the only active
user.

Add common observation metadata where applicable:

- `occurred_at` or valid-time bounds;
- `observed_at`;
- `received_at`;
- `source_timezone`;
- `time_precision` and `time_source`;
- `learned_at` and `invalidated_at` for accepted derivations.

### `EvidenceDocument`

A versioned normalized representation of one attachment or capture payload.

Core fields:

- owner, source file/capture, representation kind;
- parser and parser version;
- source content hash and derivation fingerprint;
- normalized full text;
- structured document JSON for pages, blocks, headings, lists, tables, figures,
  reading order, and transcript segments;
- language and technical metadata;
- current/superseded status and creation time.

The JSON structure is a durable interchange representation, not an opaque model
response. Docling output is converted into this LifeLog-owned contract.

### `EvidenceSpan`

A stable, citable piece of an `EvidenceDocument`.

It supports:

- character start/end in normalized text;
- page and bounding box for documents/images;
- start/end seconds and optional word indices for audio/video;
- speaker label and optional resolved speaker entity;
- table cell or structural path;
- exact source text and a content hash.

`ContentChunk` remains a recall unit during transition, but new claims cite one
or more `EvidenceSpan` rows rather than carrying only a quote string.

### `EntityMention`

A source-grounded mention before identity is settled.

Core fields:

- owner, evidence span, surface text, normalized text;
- proposed entity type and attributes;
- extractor/ontology/derivation versions;
- `resolution_status`: unresolved, resolved, ambiguous, rejected;
- resolved entity ID when known;
- candidate summary and resolution-decision lineage.

The same source mention is not re-created for an identical derivation key.

### `MemoryClaim`

An immutable assertion extracted from or deterministically mapped to evidence.

Supported forms include relation, attribute, measurement, commitment candidate,
classification, and temporal assertion. Core fields include:

- owner and claim kind;
- subject mention/entity;
- predicate from the ontology registry;
- object mention/entity or typed literal;
- polarity, modality, and explicit/inferred status;
- valid-time bounds and their precision;
- extraction score and deterministic quality features;
- reconciliation state: pending, accepted, corroborating, conflicting,
  superseded, rejected, or review;
- derivation fingerprint and timestamps.

Model confidence is retained for diagnostics but is never the sole promotion
criterion.

### `ClaimEvidence`

A many-to-many link from claims to exact spans, events, source records, or user
decisions. It records the evidence role: direct support, contextual support,
contradiction, correction, or user confirmation.

This replaces the assumption that one relation has exactly one source chunk.

### `FactEvidence` or equivalent projection linkage

Canonical `Relation`, `Measurement`, and `Commitment` records need many-to-many
links to their supporting claims. Existing source columns remain for backward
compatibility until all reads use evidence links.

### `EntityResolutionDecision`

Records candidate generation and identity decisions:

- mention and candidate entity;
- method: external ID, alias, exact, fuzzy, semantic, contextual model, or user;
- component scores and decision threshold;
- model/prompt version when applicable;
- outcome and reviewer lineage.

Entity merges continue using the existing reversible `EntityMerge` mechanism.
Resolution decisions link to it rather than bypassing it.

### `DerivationRun` and job attempts

Either extend `ProcessingJob` or add a companion record so every derived output
has:

- owner and typed purpose;
- source/input fingerprint;
- processor, parser, model-role, prompt, ontology, and configuration versions;
- idempotency/derivation key;
- budget and policy snapshot;
- status, timings, costs, output references, and failure lineage.

Record retries separately instead of overwriting all attempt history on one job.

### `DirtyScope`

A bounded reconciliation request created by deterministic invalidation:

- owner;
- affected time range, entities, source records, and reason;
- evidence dependency hash;
- materiality score;
- quiet-until time;
- queued/running/resolved status.

Overlapping scopes coalesce. Receiving thousands of ActivityWatch events must
not create thousands of model calls.

### `MemorySummary`

A versioned, rebuildable consolidation projection for an entity, topic, project,
relationship, routine, Life Area, or time period. It contains:

- scope and owner;
- structured observations plus narrative summary;
- dependency fingerprint and evidence coverage;
- valid/knowledge time;
- citations to claims/facts/spans;
- prompt/model/derivation lineage;
- current/superseded status.

Daily summaries eventually become one subtype of this general mechanism, while
their existing API remains compatible.

## Core service boundaries

Create narrow services instead of expanding `artifacts.py`, `kernel.py`, or
`ai.py` into god modules.

| Service | Responsibility |
| --- | --- |
| `model_router.py` | Select a deployment by model role and required capabilities; enforce budgets/fallbacks. |
| `evidence.py` | Create normalized evidence documents/spans and preserve locator invariants. |
| `document_processing.py` | Docling/native/vision parser adapters and LifeLog document conversion. |
| `audio_processing.py` | Provider and WhisperX transcription adapters, VAD, alignment, and diarization contracts. |
| `ontology.py` | Versioned entity/predicate registry, aliases, validation, and extension contributions. |
| `claim_extraction.py` | Schema-constrained deterministic and LLM claim/mention extraction. |
| `grounding.py` | Exact/fuzzy span alignment, locator validation, and evidence-quality features. |
| `entity_resolution.py` | Candidate generation, scoring, contextual verification, and review decisions. |
| `reconciliation.py` | Corroboration, conflict, supersession, bi-temporal validity, and projection updates. |
| `dirty_scopes.py` | Coalescing and scheduling bounded reconciliation/consolidation work. |
| `recall.py` | Candidate generation and fusion across lexical, vector, graph, time, and structured facts. |
| `query_planning.py` | Typed question classification and retrieval/tool strategy, not answer generation. |
| `consolidation.py` | Sparse, dependency-versioned entity/topic/period summaries. |
| `evaluation.py` | Dataset runners and deterministic metrics; optional external trace exporter. |

The existing public service functions stay as compatibility façades until their
callers are moved.

## Implementation phases

Each phase must ship with its tests, documentation, feature flag, backfill, and
rollback path. A phase is not complete because models or tables exist.

### Phase 0 — Freeze a trustworthy baseline

Objective: make the current state reproducible before changing memory semantics.

Work:

1. Preserve the existing dirty working tree; commit the current platform in
   logical chunks before starting this upgrade.
2. Run and record SQLite, PostgreSQL/pgvector, Alembic, Ruff, and web-build gates.
3. Correct documentation drift: the current interactive assistant uses iterative
   tools, not the older fixed recency-context design still described elsewhere.
4. Add representative fixture packs for scans, native PDFs, tables, handwriting,
   long recordings, noisy audio, structured source revisions, and late data.
5. Snapshot current response contracts and create compatibility tests for search,
   chat, captures, Inbox, kernel, commitments, and timelines.
6. Add feature flags for the new evidence, claims, resolver, reconciler, model
   router, and consolidation paths.

Exit gate:

- the complete current suite passes on SQLite and PostgreSQL;
- there is one Alembic head and a tested upgrade from the current production head;
- representative data can be replayed deterministically;
- no later phase begins on an uncommitted, unrepeatable baseline.

### Phase 1 — Explicit ownership, lineage, and time

Objective: remove unsafe implicit ownership and establish shared temporal fields.

Work:

1. Add ownership to all retrievable/actionable records.
2. Backfill ownership only through unambiguous capture, device, source connection,
   or source-record lineage. Quarantine ambiguous legacy rows instead of guessing.
3. Require owner filters inside services, not only API routes.
4. Add observation/receipt/learning timestamps and precision metadata where the
   source contract supports them.
5. Add derivation fingerprints and immutable job-attempt history.
6. Extend source/capture policy propagation to every new derivation.
7. Make owner, privacy scope, processor version, prompt version, and ontology
   version mandatory in new intelligence paths.

Exit gate:

- no assistant or retrieval tool uses an “only active user” fallback;
- commitments and schedule tools can be safely exposed per user;
- cross-user fixtures prove search, graph traversal, reviews, plans, summaries,
  and source history fail closed;
- every new derivation is attributable to inputs and code/model configuration.

### Phase 2 — Capability-based model router

Objective: stop routing OCR, transcription, extraction, embeddings, and chat
through one provider/model list.

Work:

1. Introduce model roles: vision, transcription, extraction, resolution,
   summarization, assistant, embedding, and reranking.
2. Define deployments with required modalities, structured-output support,
   context/output limits, embedding dimensions, provider, price metadata, and
   privacy/locality policy.
3. Wrap LiteLLM Router or equivalent logic behind a LifeLog `ModelRouter`.
4. Validate role capabilities at startup and expose a redacted readiness report.
5. Add role-specific timeouts, retry/fallback chains, concurrency, request and
   daily cost budgets, and circuit-breaker behavior.
6. Remove direct provider selection from `call_llm`, transcription, embedding,
   and Pydantic AI model construction.
7. Version cache keys with role, provider, model, prompt, schema, and normalized
   input hash.
8. Record cost and latency from provider response metadata; do not rely on a
   small hard-coded price map for unknown deployments.

Exit gate:

- a text-only model cannot be selected for a vision request;
- an unavailable embedding or enrichment model never blocks preservation or
  lexical indexing;
- fallbacks are tested per role;
- model changes are observable and do not silently reuse incompatible caches or
  embeddings.

### Phase 3 — Rich evidence normalization

Objective: turn artifacts into inspectable, modality-aware evidence before
semantic extraction.

Work:

1. Add `EvidenceDocument` and `EvidenceSpan` with the locator contract above.
2. Build a parser interface returning LifeLog-owned structured representations.
3. Integrate Docling for native and scanned documents behind that interface.
4. Retain native fast paths for plain text and simple PDFs; choose the cheapest
   parser that meets quality requirements.
5. Use the vision role only for pages/regions that need OCR or visual reasoning.
6. Preserve tables, headings, reading order, page regions, and parser confidence.
7. Build a transcription interface with segment and word timing, VAD, speaker
   labels, language, and backend metadata.
8. Add WhisperX as an optional self-hosted backend; retain provider transcription
   for installations without suitable compute.
9. Generate recall chunks from document structure rather than fixed characters.
   Align tokenization with the active embedding model and retain span membership.
10. Dual-write `ContentChunk` during compatibility rollout.

Exit gate:

- a table row retains its header context;
- every displayed excerpt can navigate to a page region or audio interval;
- reprocessing the same content/config produces the same derivation key;
- parsing failure leaves the original available and creates a retryable stage,
  not a failed entire capture when other artifacts are usable.

### Phase 4 — Grounded claim layer and ontology

Objective: insert an auditable layer between extracted text and canonical memory.

Work:

1. Add `EntityMention`, `MemoryClaim`, and `ClaimEvidence`.
2. Define a deliberately small base ontology with typed predicates and allowed
   subject/object pairs.
3. Store the ontology as a versioned LifeLog-owned registry with Pydantic
   validation. Manifests may contribute aliases and compatible typed additions.
4. Map existing deterministic event/fact/measurement/commitment extractors into
   the same claim contract.
5. Replace free-form chunk extraction with schema-guided extraction that returns
   mentions, relations, literals, temporal expressions, polarity, modality, and
   exact evidence text.
6. Align extracted evidence to `EvidenceSpan` character ranges and locators.
   Ungrounded output remains diagnostic data or is rejected; it cannot promote.
7. For long documents, run bounded parallel chunks and an optional second pass
   only when the first-pass coverage/materiality gate warrants it.
8. Deduplicate overlapping chunk claims by normalized claim fingerprint while
   retaining all supporting spans.
9. Replace auto-accept-by-model-confidence with a policy score composed of
   grounding, source authority, extraction method, schema validity, temporal
   clarity, corroboration, and calibrated model performance.
10. Keep the current `MemoryProposal` API as an Inbox projection until clients
    use grouped claim reviews.

Exit gate:

- no new AI-derived relation, measurement, or commitment exists without a claim
  and exact evidence;
- unknown ontology terms cannot silently create predicate drift;
- deterministic source mappings remain cheaper and higher authority than model
  extraction;
- overlapping chunks do not create duplicate commitments or facts.

### Phase 5 — Conservative entity resolution

Objective: resolve mentions across a lifetime without unsafe automatic merges.

Candidate sequence:

1. source-scoped external identity;
2. existing explicit user mapping;
3. exact canonical identifier or alias;
4. normalized exact name within compatible types;
5. bounded trigram/fuzzy candidates;
6. embedding candidates within owner/type/privacy scope;
7. graph, time, location, course/project, and source-context features;
8. contextual model verification over only the top candidates;
9. user review when ambiguity remains or the identity type is consequential.

Work:

1. Add durable resolution decisions and component scores.
2. Build indexed candidate generation; never full-scan entity names in the normal
   path.
3. Establish conservative type-specific thresholds. Person identity requires
   stronger evidence than a topic or application name.
4. Auto-resolve only when policy has high precision on the evaluation corpus.
5. Continue to use pair-stable Inbox reviews and reversible merges.
6. Learn accepted aliases/source mappings from corrections without treating all
   future similar strings as identical.
7. Support “not the same” constraints so rejected pairs are not repeatedly
   proposed.

Exit gate:

- merge and split accuracy meet the evaluation thresholds below;
- no automatic merge is based solely on vector or fuzzy similarity;
- every resolution can explain which signals caused it;
- user correction immediately affects future resolution and remains reversible.

### Phase 6 — Temporal reconciliation and contradiction handling

Objective: transform grounded claims into a coherent, historical memory.

Work:

1. Add many-to-many evidence links to canonical facts and projections.
2. Reconcile claims by owner, resolved subject, predicate, object/value, temporal
   overlap, source authority, and modality.
3. Implement deterministic outcomes:
   - duplicate/corroborating claim: attach evidence;
   - newer authoritative revision: close the previous current fact and create the
     replacement;
   - non-overlapping valid periods: retain both historically;
   - explicit negation/cancellation: invalidate current fact at learned time;
   - compatible additive facts: retain both;
   - unresolved material conflict: create one grouped Inbox review.
4. Never infer “newer received” means “newer true.” Use valid and knowledge time.
5. Propagate source replacement/cancellation through claims, canonical facts,
   commitments, reminders, plans, search documents, and summaries.
6. Create and coalesce `DirtyScope` rows for affected time/entity neighborhoods.
7. Rebuild only projections whose dependency fingerprints changed.
8. Add “what LifeLog knew at time X” and “what was true at time X” query support.

Exit gate:

- late evidence can correct an old deadline without rewriting history;
- contradictory low-authority evidence cannot silently replace confirmed truth;
- deleting/superseding one source removes its support and only invalidates a fact
  when no valid support remains;
- commitment cascade behavior remains deterministic and notification-safe.

### Phase 7 — Durable staged processing

Objective: replace monolithic artifact work with independently retryable,
progressively available stages.

Target DAG:

```text
preserve
  -> normalize_media
      -> persist_spans
          -> lexical_index
          -> embed_spans
          -> classify_context
          -> extract_claims
              -> ground_claims
                  -> resolve_mentions
                      -> reconcile_memory
                          -> project_actions
                          -> mark_dirty_scopes
```

Work:

1. Make every stage an idempotent service plus small ARQ entry point.
2. Commit outputs and enqueue dependents transactionally using an outbox or
   database-backed enqueue record.
3. Fan out document pages/chunks and audio windows with bounded concurrency;
   fan in before cross-chunk deduplication.
4. Distinguish required, optional, and degradation-safe dependencies.
5. Preserve completed lexical evidence when semantic enrichment fails.
6. Add leases/heartbeats for abandoned running jobs, retry policies by error
   category, cancellation, and a retryable DLQ resolution flow.
7. Keep processor implementations free of queue-specific APIs.
8. Evaluate DBOS only after these semantics exist. Adopt it only if it materially
   reduces custom recovery code without compromising async SQLModel integration.

Exit gate:

- restarting API, worker, Redis, or an AI call cannot duplicate accepted claims
  or lose completed evidence;
- a failed chunk can retry independently;
- long recordings do not hold one database transaction or one worker lease for
  their entire semantic pipeline;
- capture progress accurately reports usable partial results.

### Phase 8 — Unified recall and query planning

Objective: retrieve according to the question rather than treating all memory as
similar text.

Add a typed `QueryPlan` with one or more intents:

- direct evidence lookup;
- temporal reconstruction;
- entity/relationship exploration;
- deterministic aggregate or comparison;
- commitment/planning state;
- contradiction or evidence-coverage inspection;
- reflective/advice synthesis;
- broad longitudinal/global synthesis.

Work:

1. Index evidence spans, accepted claims, canonical facts, entities, timeline
   episodes, and memory summaries as separate source types.
2. Separate `SearchDocument` content from versioned embedding records so an
   embedding-model change can be built and validated before cutover.
3. Generate candidates through lexical search, vector search, entity/alias
   lookup, graph proximity, temporal constraints, and structured filters.
4. Fuse candidates with RRF, then apply optional reranking and source diversity.
5. Prefer primary evidence and accepted facts over narrative summaries when both
   answer the same question.
6. Add graph-fact retrieval by resolved entity/predicate/time rather than
   substring-first entity scanning.
7. Add evidence-coverage metadata so “no result” is distinguishable from “LifeLog
   had no data for that period/source.”
8. Keep deterministic aggregate tools authoritative for totals and comparisons.
9. Evaluate retrieval by intent and source type, not only aggregate top-k recall.

Exit gate:

- specific questions retrieve exact spans and local facts;
- temporal questions respect valid time and user timezone;
- aggregate questions invoke deterministic services;
- scoped retrieval applies owner, Life Area, and privacy constraints before
  ranking, graph expansion, or reranking;
- semantic-provider failure degrades to lexical/structured recall.

### Phase 9 — Complete the interactive assistant harness

Objective: let one assistant answer the full range of LifeLog questions safely.

Work:

1. Retain the bounded iterative Pydantic AI tool loop and evidence ledger.
2. Add owner-safe tools after Phase 1:
   - inspect evidence and claim history;
   - inspect current/historical fact state;
   - list deadlines and commitment progress;
   - find schedule conflicts and simulate plans;
   - compare periods and inspect data coverage;
   - inspect contradictions and source revision history.
3. Make query planning advisory: the agent may refine searches, while service
   policy still bounds every tool.
4. Give citations typed targets: source spans `[S#]`, accepted facts `[F#]`, and
   deterministic computations `[T#]`.
5. Validate that every personal factual clause is supported, not merely that one
   known citation appears somewhere in the answer.
6. Teach response policy to distinguish observation, accepted fact, inference,
   advice, uncertainty, and missing evidence.
7. Add explicit stopping rules and evidence budgets by query type.
8. Keep write operations as reviewable proposals. The assistant cannot silently
   change commitments, plans, identities, or policies.
9. Consider a restricted analysis sandbox only after typed tools prove
   insufficient. If added, it receives a bounded exported dataset, has no network,
   secrets, database, or general filesystem access, and its results cite the
   exported rows.

Exit gate:

- the assistant answers the evaluation question families below;
- tool and citation traces are inspectable;
- it cannot access another owner or bypass an area/privacy policy;
- advice clearly identifies the evidence and assumptions used;
- absent/conflicting evidence produces uncertainty rather than fabrication.

### Phase 10 — Sparse longitudinal consolidation

Objective: support lifetime-scale themes without constantly re-reading raw data.

Work:

1. Materialize entity, topic, relationship, routine, course/project, weekly,
   monthly, and Life Area summaries only where data volume warrants them.
2. Detect graph communities or stable clusters deterministically; use the model
   to summarize a bounded evidence set, not to invent the cluster.
3. Reuse summaries when the dependency fingerprint is unchanged.
4. Coalesce late evidence in dirty scopes and wait for a quiet period unless a
   consequential correction requires immediate deterministic handling.
5. Run global/map-reduce synthesis on demand for broad questions; do not rebuild
   Microsoft GraphRAG-style reports on every capture.
6. Track summary coverage, freshness, citations, and supersession.
7. Never let a summary become the sole evidence for a consequential action.

Exit gate:

- broad questions such as long-term themes or changes over months are both useful
  and cited;
- low-volume users do not pay for unnecessary consolidation;
- adding equivalent evidence causes no new model run;
- a late record invalidates only summaries that actually depended on the changed
  scope.

### Phase 11 — Evaluation, observability, and production hardening

Objective: make intelligence quality and operational behavior measurable.

Build versioned datasets for:

1. document layout/OCR and table extraction;
2. transcript accuracy, timestamps, and diarization;
3. entity/relation/commitment claim extraction;
4. exact evidence grounding;
5. identity resolution, including hard non-matches;
6. temporal corrections, contradictions, and late arrival;
7. retrieval by lexical, semantic, graph, temporal, aggregate, and global intent;
8. assistant faithfulness, citation entailment, uncertainty, and policy behavior;
9. school pilot scenarios and cross-life planning;
10. privacy, deletion, and adversarial source content.

Metrics and initial release thresholds:

- grounded promoted claims: 100%;
- unsupported consequential auto-promotion: 0 in the release corpus;
- person auto-resolution precision: at least 99.5%;
- non-person auto-resolution precision: at least 99%;
- commitment/deadline extraction precision: at least 98%, with ambiguous dates
  reviewed rather than guessed;
- temporal reconciliation correctness: at least 99% on deterministic cases;
- retrieval recall@10: at least 95% for direct-evidence benchmark questions;
- citation validity: 100%;
- cited-claim entailment: at least 98% before broad rollout;
- cross-owner/privacy leakage: 0;
- preservation success independent of AI provider: 100%;
- every model role reports latency, tokens, estimated/actual cost, cache status,
  derivation key, and failure class.

Use deterministic evaluators wherever possible. Model judges may supplement but
never replace span checks, identity labels, temporal assertions, ownership tests,
or expected calculations. A self-hosted Langfuse integration may receive
redacted traces and experiment scores, but LifeLog retains its own evaluation
dataset and run metadata as the source of truth.

Operational gates:

- queue age, stage latency, retry counts, DLQ age, embedding backlog, dirty-scope
  backlog, provider health, spend, and review volume are observable;
- backup/restore preserves evidence, provenance, identities, and job state;
- reindex and re-derivation are bounded, resumable, and do not block capture;
- storage retention/deletion removes derived search and summaries while retaining
  only policy-permitted audit lineage;
- model/prompt/ontology changes support canary evaluation and rollback.

### Phase 12 — Real longitudinal pilot and cutover

Objective: prove the architecture with messy, connected personal use.

Pilot sequence:

1. Replay the realistic ActivityWatch day plus noisy phone location/device data.
2. Add class recordings with interruptions, multiple speakers, offline arrival,
   and poor audio.
3. Add native and photographed worksheets, whiteboards, handwritten notes, and
   source-system revisions.
4. Connect calendar and school-source records where available.
5. Run the assistant benchmark: factual recall, last-Thursday reconstruction,
   course relationships, deadlines, aggregate behavior, sleep/activity trends,
   reflective advice, and cross-life planning.
6. Measure false/missed claims, identity errors, deadline corrections, review
   burden, citation usefulness, cost, and latency for several weeks.
7. Compare old and new projections in shadow mode before switching reads.
8. Cut over one projection/tool at a time; retain rebuildable rollback until the
   new path passes longitudinal gates.

The new system becomes default only after real late data, corrections, model
outages, reprocessing, and user edits have been observed successfully.

## Compatibility and rollout strategy

No phase performs a destructive big-bang conversion.

1. **Expand:** add nullable/new tables and new services without changing current
   reads.
2. **Dual write:** produce current `ContentChunk`/`MemoryProposal`/`Relation`
   outputs and new evidence/claim outputs from the same source.
3. **Backfill:** replay immutable inputs through versioned jobs in bounded batches.
4. **Compare:** inspect old/new counts, evidence, identities, commitments, search
   results, and assistant answers.
5. **Shadow read:** execute the new path for evaluation without serving it.
6. **Canary:** enable by user, source, capture type, or model role.
7. **Cut over:** switch one read/projection at a time behind a flag.
8. **Contract:** remove old fields and compatibility façades only after all callers,
   backfills, rollback windows, and docs are complete.

Each schema change needs both upgrade and downgrade reasoning. Applied migrations
remain immutable. Backfills are resumable application jobs, not long blocking
Alembic operations.

## Concrete code map

Expected new or split modules:

```text
server/app/models/
  evidence.py
  claims.py
  intelligence.py

server/app/services/
  model_router.py
  evidence.py
  document_processing.py
  audio_processing.py
  ontology.py
  claim_extraction.py
  grounding.py
  entity_resolution.py
  reconciliation.py
  dirty_scopes.py
  recall.py
  query_planning.py
  consolidation.py
  evaluation.py

server/app/workers/
  evidence.py
  intelligence.py

server/app/ontology/
  core.yaml
  aliases.yaml

server/tests/fixtures/intelligence/
server/tests/evals/
```

Expected major changes:

- `models/files.py`: compatibility links and eventual simplification of chunks
  and proposals;
- `models/kernel.py`: owner, bi-temporal fact state, and evidence links;
- `models/retrieval.py`: separate text and embedding-version concerns;
- `models/captures.py`: derivation/job attempt and progressive-stage changes;
- `models/processing.py`: ownership and summary transition;
- `services/artifacts.py`: become a compatibility orchestrator, then shrink;
- `services/extraction.py`: emit claims through deterministic mappings;
- `services/kernel.py`: canonical fact projection and resolution-safe graph APIs;
- `services/retrieval.py`: become a façade over unified recall;
- `services/ai.py`: become a compatibility façade over `ModelRouter`;
- `services/intelligence.py` and `services/tools.py`: new evidence/fact tools and
  stronger citation validation;
- `loader/contracts.py`: ontology aliases/types and source-authority metadata;
- `workers/main.py`: register small staged tasks rather than monolithic artifact
  work;
- `api/inbox.py`, `api/search.py`, `api/ai_chat.py`, and `api/kernel.py`: expose
  evidence history and grouped decisions while preserving current contracts.

## Security, privacy, and safety requirements

1. Owner and purpose scope are applied before candidate generation, embeddings,
   graph expansion, model reranking, or summary assembly.
2. Derived memory inherits the strictest applicable source policy unless a user
   explicitly changes it.
3. Model requests exclude secret fields and respect deployment locality policy.
4. Prompt-injection content inside personal artifacts is evidence, never system
   instruction. Extractors and the assistant receive it in clearly delimited data
   structures.
5. Traces redact secrets and support disabling raw content while retaining hashes,
   timings, and structural metrics.
6. Deletion/forget workflows enumerate and invalidate dependent claims, facts,
   embeddings, summaries, caches, and exports.
7. Consequential identity, deadline, health, financial, and external-action
   changes use explicit policy and review thresholds.
8. An optional analysis sandbox receives only explicitly exported, owner-scoped
   rows and cannot reach production services.

## Cost policy

The implementation must retain the cheapest-sufficient hierarchy:

1. preserve, hash, and deduplicate;
2. deterministic normalization and source mappings;
3. structure-aware local parsing;
4. lexical indexing;
5. batched embeddings;
6. cheap structured extraction;
7. contextual resolution only for ambiguous candidates;
8. reconciliation model calls only for unresolved material conflict;
9. higher-order consolidation only after a meaningful dependency delta;
10. stronger assistant models only for difficult synthesis.

Budgets are per owner, role, day, source, and run type. Provider failure or budget
exhaustion delays optional enrichment but never loses captures or source records.

## Documentation work

As phases land:

1. update `architecture.md` to distinguish evidence, claims, canonical facts,
   projections, and recall;
2. update `INTELLIGENCE_LAYER.md` with the implemented query-plan/tool surface;
3. update `EXTENSION_CONTRACT.md` with ontology contribution and source-authority
   rules while keeping connectors narrow;
4. update `CONNECTOR_SDK.md` with evidence time and authority metadata;
5. replace phase-complete claims in `PRODUCTION_REFACTOR_PLAN.md` with measured
   evaluation status;
6. document parser/transcriber deployment profiles for CPU, GPU, and provider
   modes;
7. document how users inspect, correct, forget, merge, split, and understand why
   LifeLog believes something.

## Definition of done

This plan is complete only when all of the following are true:

- every personal fact served to the assistant can be traced through a canonical
  projection, claim, exact evidence, immutable input, and derivation run;
- current and historical truth can be queried independently of ingestion time;
- late and contradictory evidence reconciles deterministically or produces one
  useful review question;
- entity resolution is conservative, measured, explainable, owner-safe, and
  correctable;
- modality processors retain useful layout, timing, and speaker evidence;
- model routing is capability-aware, portable, observable, and budgeted;
- pipeline stages are idempotent, independently retryable, and progressively
  available;
- direct, temporal, structural, aggregate, reflective, planning, and broad
  longitudinal questions pass versioned evaluation suites;
- no Life Area or extension creates a parallel memory or assistant;
- AI outages degrade enrichment, never preservation;
- real longitudinal use demonstrates acceptable accuracy, review burden, cost,
  latency, privacy, recovery, and correction behavior.

## Explicitly out of scope until these gates pass

- a free-running autonomous background agent;
- silent assistant writes or external actions;
- migrating the authoritative graph to Neo4j solely because GraphRAG examples use
  it;
- generic framework-owned agent memory;
- automatic person merging based only on embeddings or string similarity;
- global community-summary regeneration after each capture;
- arbitrary SQL, shell, filesystem, or unrestricted code execution by the
  assistant;
- an extension marketplace before isolation, signing, upgrade, and resource
  policies exist.

These are deliberate safeguards, not missing ambition. The goal is a LifeLog
that can grow for decades without turning accumulated model guesses into an
uncorrectable version of the user's life.

## Primary implementation references

These projects are references or optional components, not alternate sources of
truth inside LifeLog:

- [Graphiti](https://github.com/getzep/graphiti) for incremental episode-backed,
  temporal knowledge graphs and hybrid graph retrieval;
- [Graphiti episode concepts](https://help.getzep.com/graphiti/core-concepts/adding-episodes)
  for provenance and knowledge-time behavior;
- [Neo4j GraphRAG KG builder](https://neo4j.com/docs/neo4j-graphrag-python/current/user_guide_kg_builder.html)
  for staged parsing, schema-guided extraction, graph writing, and resolution;
- [Microsoft GraphRAG architecture](https://microsoft.github.io/graphrag/index/architecture/)
  for claims, communities, versioned workflows, caching, and local/global query
  modes;
- [LightRAG](https://github.com/HKUDS/LightRAG) for incremental graph/vector
  retrieval and detail/concept fusion;
- [Google LangExtract](https://github.com/google/langextract) for schema-guided,
  exact-span-grounded, parallel long-document extraction;
- [Docling chunking](https://docling-project.github.io/docling/concepts/chunking/)
  for hierarchical, token-aware document segmentation;
- [WhisperX](https://github.com/m-bain/whisperX) for VAD, batched transcription,
  word alignment, and diarization;
- [LiteLLM](https://docs.litellm.ai/) for portable provider APIs, model routing,
  fallbacks, accounting, and observability hooks;
- [DBOS Python](https://docs.dbos.dev/python/integrating-dbos) for an optional
  future Postgres-backed durable-execution implementation;
- [Langfuse evaluation concepts](https://langfuse.com/docs/evaluation/core-concepts)
  for datasets, experiment runs, deterministic evaluators, and production trace
  feedback.
