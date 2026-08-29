# LifeLog System Architecture

## 1. Purpose and invariants

LifeLog is a self-hosted, Python-native system for collecting personal data,
reconstructing a timeline, and building correctable AI-assisted memory over a
lifetime. It is a modular monolith: one FastAPI deployment with explicit
`api -> services -> models` boundaries, ARQ workers for durable background
work, APScheduler for periodic orchestration, PostgreSQL/pgvector for durable
state and recall, and Redis for the queue and distributed locks.

The architecture follows four invariants:

1. Raw source material is retained; derived state is rebuildable.
2. Every derived fact has explicit provenance and versioning.
3. AI may propose uncertain knowledge but cannot silently turn unsupported text
   into authoritative memory.
4. Extensions adapt sources. The base owns durable memory, retrieval, planning,
   and policy. The normative boundary is in
   [EXTENSION_CONTRACT.md](EXTENSION_CONTRACT.md).

The end-user and product abstraction is defined in
[PRODUCT_MODEL.md](PRODUCT_MODEL.md): reusable **Capabilities**, narrow
**Sources**, and non-siloed **Life Areas** all operate over one LifeLog memory.

All database timestamps are stored as naive UTC. Alembic exclusively owns
schema creation and upgrades; application startup checks connectivity but does
not call `create_all`.

## 2. Runtime architecture

```text
device capture / source connections / direct artifact uploads
                 |
                 v
       Capture / immutable RawLog / FileAttachment
                 |
         versioned ProcessingJob stages
                 |
       Event + ContentChunk + provenance
          |              |
     sessionization      +--> MemoryProposal --> reviewed/promoted memory
          |                              |
          v                              v
 Session --> TimelineEntry          Entity / Relation
          |                              |
          +-----------> SearchDocument <-+
                              |
                 hybrid recall + graph context
                              |
                  grounded chat / planning
```

Redis or an AI provider may be unavailable without preventing immutable
ingestion. Lexical recall remains available without embeddings. Work that
cannot complete is retained as pending source state or a durable
`ProcessingFailure`, not only in application logs.

## 3. Code boundaries

```text
server/app/
├── api/         thin HTTP validation, authentication, response models
├── services/    domain logic and orchestration
├── models/      SQLModel persistence schema
├── core/        configuration, DB, auth, logging, files, shared infrastructure
├── workers/     ARQ entry points for normalization and artifact processing
└── loader/      validated extension contracts and trusted module loading
```

- `api/` may call services and query models for simple reads.
- Business workflows belong in `services/`, not route handlers.
- Workers are durable entry points and delegate to services.
- Extensions never own an authoritative shadow memory store.

## 4. Persistent domains

The schema is grouped by responsibility rather than an obsolete fixed count.

### Identity and configuration

| Table | Purpose |
| --- | --- |
| `users` | JWT-authenticated users and superuser state. |
| `devices` | User-owned hashed device credentials and sync cursors; device keys may use universal capture. |
| `extensions` | Installed manifest, API version, configuration, active state, and cron schedule. |
| `system_config` | Runtime configuration records. |
| `prompts` | Versioned AI prompt templates. |
| `ai_usage` | Provider/model/token/cost/latency accounting with operation and source lineage. |

### Immutable ingestion and episodic processing

| Table | Purpose |
| --- | --- |
| `raw_logs` | Immutable source envelopes deduplicated by canonical device-or-source revision identity. |
| `events` | Versioned normalized observations linked to a raw log. |
| `sessions` | Logical-date-bounded active or idle episodes split by authoritative AFK windows, elapsed-time limits, and genuine event gaps. |
| `timeline_entries` | Structured, evidence-backed episodic records with title, factual detail, category, tags, source timezone, confidence, explicit inference labels, and supporting event IDs. |
| `daily_summaries` | Rebuildable cross-source summaries with concise key activities, open loops, and separately labeled inferences. |

`timeline_entries` do **not** contain embeddings. Semantic indexing is isolated
in the rebuildable recall projection described below.

### Sources and universal capture

| Table | Purpose |
| --- | --- |
| `source_connections` | A user's configured instance of an installed source adapter, separate from its reusable manifest. |
| `source_secrets` | Per-connection credentials encrypted at rest and never serialized through source responses. |
| `source_checkpoints` | Versioned stream cursors advanced only after returned records are durably processed. |
| `source_records` | Stable external identities pointing to the newest known immutable raw revision and update policy. |
| `captures` | A durable photo, scan, recording, note, or file capture with lightweight context and privacy hints. |
| `capture_artifacts` | Ordered many-file membership linking one capture action to original artifacts. |
| `upload_sessions` | Offset-checked, expiring resumable uploads for large or intermittently connected clients. |
| `processing_jobs` | Versioned stage-level state, attempts, errors, and output references for derived work. |

`Extension` remains the installed adapter definition for compatibility;
`SourceConnection` is the user's configured instance. Public connection config
rejects credential-shaped fields. Secret plaintext exists only while invoking
the trusted adapter and is not placed in manifests, logs, checkpoints, or API
responses.

### Memory kernel

| Table | Purpose |
| --- | --- |
| `entities` | User-owned current or superseded concepts, with optional source-scoped external identity. Display names are not global identity keys. |
| `entity_aliases` | Deterministic identity aliases and normalized lookup keys. |
| `relations` | Typed entity/event edges with valid time, confidence, supersession, source event/file/chunk, extractor, and extraction version. |
| `entity_merges` | Durable consequential decisions containing the survivor, retired entity, decider/review lineage, and the snapshot needed for guarded reversal. |

### Evidence, claims, and intelligence lineage

| Table | Purpose |
| --- | --- |
| `evidence_documents` | Versioned normalized representations of immutable files, notes, recordings, or structured evidence. |
| `evidence_spans` | Exact citable text/page/region/audio ranges, optionally linked to compatibility chunks. |
| `entity_mentions` | Grounded source mentions before identity is settled. |
| `memory_claims` | Immutable typed assertions separated from accepted canonical projections. |
| `claim_evidence` | Many-to-many direct, contextual, contradictory, corrective, or user-confirmed support. |
| `fact_evidence` | Links accepted relations, measurements, or commitments back to supporting claims. |
| `entity_resolution_decisions` | Durable candidate scores and accepted, rejected, or review identity outcomes. |
| `derivation_runs` / `derivation_attempts` | Idempotent derived computations and append-only retry history. |
| `dirty_scopes` | Coalesced bounded time/entity regions requiring reconciliation after changed evidence. |
| `memory_summaries` | Versioned longitudinal consolidation contract; generation remains deferred. |

Claims are not facts merely because a model emitted them. Exact grounding,
ontology validation, ownership/privacy checks, conservative identity resolution,
and reconciliation policy decide whether a claim corroborates, conflicts with,
or becomes support for a canonical projection. Deterministic event mappings use
the same claim/evidence ledger at higher authority and lower cost.

The graph is a rebuildable semantic projection, not source truth. Automatically
extracted relations carry explicit lineage. Stable identity is scoped by owner,
entity type, source namespace, and external key; equal display names alone never
prove identity. Merge candidates are pair-stable Inbox items. Applying a merge
locks both entities in deterministic order, preserves conflicting attributes and
the stricter privacy policy, and records a guarded reversal snapshot. Historical
measurements and relations resolve through the current entity family so aggregates
remain correct after a merge. Neighborhood traversal is bounded to depth 1–3 and
a capped edge count. Predicate filters and valid-time duration rollups provide
general structural and aggregate recall.

### Artifacts, action, and delivery

| Table | Purpose |
| --- | --- |
| `file_attachments` | Content-addressed source files and durable processing state. |
| `content_chunks` | Versioned native text, OCR, or transcript excerpts with locators. |
| `memory_proposals` | Evidence-grounded entity/relation/commitment candidates with review state. |
| `commitments` | Domain-neutral obligations and outcomes. |
| `commitment_progress` | Evidence of work completed, optionally linked to events. |
| `plan_blocks` | Revisable planned allocations toward commitments. |
| `notifications` | Base-owned durable notification/outbox records. |

The base selects native extraction, image or scanned-PDF OCR, and audio/video
transcription. Compatibility proposals remain user-visible, but new semantic
output also enters the claim ledger. Model confidence alone never authorizes
promotion: exact grounding, schema/ontology validity, source authority,
resolution, reconciliation, and review policy determine the outcome.

### Recall and resilience

| Table | Purpose |
| --- | --- |
| `search_documents` | Disposable, versioned recall projection over events, timeline, summaries, chunks, and entities. |
| `processing_failures` | Durable dead-letter records with stage, source, attempts, traceback, context, and resolution state. |

### Context, policy, and review

| Table | Purpose |
| --- | --- |
| `life_areas` | User-owned, declarative lenses over shared memory: vocabulary, recognition hints, cards, questions, and policy hints. |
| `context_links` | Many-to-many relevance links from any durable or derived target to a Life Area; records are never copied into an area. |
| `memory_policies` | Owner-scoped disclosure rules propagated with derivation lineage (`global`, `selected_areas`, or `private`). |
| `review_items` | One user Inbox projection over classification, memory-proposal, and consequential revision workflows. |

Context and privacy propagate Capture → artifact/chunk and SourceConnection →
RawLog → Event, then into graph facts and commitments. Global recall remains the
owner's whole-life view. A Life Area-scoped retrieval requires both relevance
and policy permission; graph and cited artifact retrieval use the same scope.

PostgreSQL lexical recall uses `to_tsvector('english', content)` with a GIN
index. Semantic recall uses 768-dimensional pgvector embeddings and an HNSW
cosine index. Reciprocal-rank fusion combines lexical and semantic rankings.
SQLite tests use deterministic lexical fallbacks; production PostgreSQL is the
semantic execution target.

Embedding enrichment runs in a bounded scheduled batch outside ingestion
transactions. When the embedding provider is unavailable, source writes and
lexical search still succeed. `/search/reindex` rebuilds projections from
durable source tables.

## 5. Core workflows

### Event ingestion

1. A device submission or configured source returns an envelope.
2. The base computes a canonical ingestion identity. Device writes deduplicate
   by device and content; connected sources deduplicate by connection, stable
   external key, and external revision (or content when no revision exists).
3. The immutable envelope enters `raw_logs`; a normalization `ProcessingJob`
   exposes durable progress and attempts.
4. ARQ or the trusted runtime calls the extension `normalize(payload)` adapter.
5. The base writes `events`, applies deterministic/registered fact extraction,
   and writes recall documents with explicit lineage.
6. Replacement/snapshot revisions supersede earlier events, graph relations,
   and recall documents only after the replacement exists.
7. Sessionization quarantines focus records observed during authoritative AFK
   windows and bounds active episodes by elapsed time. High-frequency records
   are aggregated into compact evidence groups before AI processing.
8. Timeline generation atomically claims each session and requires structured
   output tied to supporting event IDs. A database uniqueness invariant permits
   only one timeline projection per session.
9. Daily synthesis fuses timeline episodes with direct captures and notes, so
   unfinished work and tentative deadlines can correct weaker activity traces.
   Observations, open loops, and uncertain inferences remain distinct.

### Source synchronization

1. A user creates a `SourceConnection` for an installed collector and stores
   public config separately from encrypted secrets.
2. Cron or `POST /sources/{id}/sync` starts its poller with config, secrets, and
   the last durable checkpoint.
3. The poller returns typed record envelopes containing payload, stable external
   identity/revision, update policy, timestamps, and an optional next checkpoint.
4. LifeLog ingests and processes every record before persisting that checkpoint.
   A failed page is therefore safely replayable.
5. APScheduler only enqueues a uniquely keyed ARQ poll job; source code and
   network acquisition never run inside the API scheduler process.
6. Connection sync state and `ProcessingFailure` retain errors for inspection.
   Runtime secret values are replaced before error messages or tracebacks are
   persisted or logged.
7. Manifest `commitment_mappings` deterministically project actionable records.
   A consequential revision supersedes the prior commitment, cancels obsolete
   reminders and plan blocks, and creates an immediate review notification.

### Universal capture

1. `POST /captures/notes`, multipart `POST /captures`, or a resumable upload
   creates the capture independently of final classification.
2. Original text/bytes, capture time, intent, context hints, and privacy hints
   are preserved first. A capture can contain multiple ordered artifacts.
3. Note text is indexed immediately. File processing creates explicit content
   extraction, broad classification, and memory-enrichment jobs.
4. Classification uses user intent first and deterministic content/media hints
   second. Uncertain classification or pending memory proposals sets
   `awaiting_review`; a user confirmation clears that ambiguity.
5. Stage dependencies are enforced: failed prerequisite work cancels blocked
   later stages, while independent completed evidence remains available.
6. Capture state progresses through preserved, processing, awaiting-review, ready,
   partially-ready, or failed while completed evidence remains usable.
7. JWT users and user-owned device API keys use the same capture contract.
8. Clients can query upload offsets, resume exactly, cancel incomplete uploads,
   and rely on scheduled expiry cleanup for abandoned temporary data.

### Artifact intelligence

1. A user or `artifact_source` extension uploads original bytes and hints.
2. The base stores bytes by SHA-256 and creates durable processing state.
3. A worker extracts, OCRs, or transcribes into compatibility chunks and a
   versioned `EvidenceDocument` with exact `EvidenceSpan` locators.
4. Spans enter lexical recall immediately; embeddings remain degradation-safe
   enrichment.
5. Deterministic mappings and schema-constrained AI extraction create grounded
   mentions and claims, never unsupported canonical facts.
6. Conservative identity resolution and temporal reconciliation attach support,
   preserve conflicts, or create one grouped Inbox review.
7. Accepted projections can produce graph facts, commitments, reminders,
   progress evidence, and revisable plans with claim lineage.

### Grounded chat

Chat uses a bounded iterative tool loop, not a fixed recency dump. It may plan
the query, search span/claim/event/timeline/summary recall, inspect exact evidence
or historical facts, traverse relevant graph structure, inspect coverage and
source revisions, or invoke deterministic aggregate/commitment/planning reads.
It stops when the evidence is sufficient and uses typed `[S#]`, `[F#]`, and
`[T#]` citations. Unknown citations and uncited personal factual sentences are
rejected before the answer is returned. AI usage is owner-accounted by operation
and source context.

Chat has one global entry point and optional Life Area scope. Scoped chat omits
the unfiltered recency dump and applies the same Life Area and memory-policy
check to recall documents, artifact excerpts, and graph lineage. Areas therefore
change presentation and permitted context without creating separate assistants.

### Review and correction

Low-confidence classification, grounded memory proposals below auto-accept
policy, and consequential commitment revisions create or update a `ReviewItem`.
The Inbox dispatches accepted/rejected decisions to the authoritative source
workflow and records the outcome. Direct legacy review endpoints also settle the
corresponding Inbox item, so there is one review state rather than parallel UI
truths. Entity-merge suggestions are keyed by the unordered candidate pair, are
owner-isolated, and can be deferred temporarily. Accepted merges produce a
durable merge record and may be reversed only while doing so cannot overwrite
subsequent edits or reuse of the retired source identity.

## 6. Extension contract

Manifests are validated by `loader/contracts.py` and declare an API version,
capabilities, permissions, optional `scheduler_cron`, deterministic mappings,
and optional declarative Life Area templates.

| Capability | Extension responsibility |
| --- | --- |
| `collector` | Acquire proprietary/source-specific records. |
| `normalizer` | Convert a source payload into generic Event envelopes. |
| `artifact_source` | Submit original files or recordings and optional hints. |
| `notification_channel` | Deliver base-owned notifications through an approved channel. |

An optional `poller.py` exposes sync or async `poll(runtime) -> PollResult`.
`runtime` contains public connection config, ephemeral decrypted secrets, and a
durable checkpoint. `PollResult` contains typed record envelopes, the next
checkpoint, stream, and pagination state. Legacy list returns remain append-only
compatible. APScheduler enqueues both configured schedules and manual syncs into
ARQ. The base persists, reconciles, normalizes, indexes, and records failures.
Installed extensions are trusted Python code; manifest permissions are an
auditable declaration, not an OS sandbox.

Ordinary connectors import typed records, poll pages, contexts, deterministic
revision helpers, and contract-test utilities from `lifelog_sdk`. This boundary
hides persistence, checkpoint commit, replay, supersession, retries, recall,
privacy, and reconciliation. Python remains an acquisition/normalization escape
hatch; it is not the user-facing Life Area implementation.

Deterministic fact mappings project stable Event data paths into entity/relation
facts with transform, confidence, extractor identity
`manifest:{extension_id}:{mapping_index}`, and extraction-version lineage.

## 7. Deployment and verification

Production requires PostgreSQL with pgvector, Redis for queued work, content
storage, a non-default `SECRET_KEY`, and `uv run alembic upgrade head` before
API/worker startup. Docker Compose includes a migration service and an isolated
`pgvector/pgvector:pg16` test database profile.

The default test suite runs safely on SQLite for speed and portability. The
PostgreSQL gate applies the full Alembic chain and exercises real full-text and
pgvector cosine/RRF behavior through `TEST_DATABASE_URL`.
