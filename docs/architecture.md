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

All database timestamps are stored as naive UTC. Alembic exclusively owns
schema creation and upgrades; application startup checks connectivity but does
not call `create_all`.

## 2. Runtime architecture

```text
collectors / pollers / artifact uploads
                 |
                 v
        immutable RawLog / FileAttachment
                 |
          normalization / extraction
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
| `devices` | Hashed device credentials and sync cursors. |
| `extensions` | Installed manifest, API version, configuration, active state, and cron schedule. |
| `system_config` | Runtime configuration records. |
| `prompts` | Versioned AI prompt templates. |
| `ai_usage` | Provider/model/token/cost/latency accounting with operation and source lineage. |

### Immutable ingestion and episodic processing

| Table | Purpose |
| --- | --- |
| `raw_logs` | Deduplicated immutable source envelopes. |
| `events` | Versioned normalized observations linked to a raw log. |
| `sessions` | Logical-date-bounded groups of events, normally split after a 30-minute gap. |
| `timeline_entries` | AI-generated episodic narrative linked to a session and prompt. |
| `daily_summaries` | Rebuildable summaries keyed by logical date. |

`timeline_entries` do **not** contain embeddings. Semantic indexing is isolated
in the rebuildable recall projection described below.

### Memory kernel

| Table | Purpose |
| --- | --- |
| `entities` | Current or superseded people, places, courses, projects, applications, and other concepts. |
| `entity_aliases` | Deterministic identity aliases and normalized lookup keys. |
| `relations` | Typed entity/event edges with valid time, confidence, supersession, source event/file/chunk, extractor, and extraction version. |

The graph is a rebuildable semantic projection, not source truth. Automatically
extracted relations carry explicit lineage. Entity merges preserve history via
supersession. Neighborhood traversal is bounded to depth 1–3 and a capped edge
count. Predicate filters and valid-time duration rollups provide general
structural and aggregate recall.

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
transcription. A proposal can auto-promote only when it clears the configured
confidence threshold and its evidence quote occurs in the source chunk.
Otherwise it remains reviewable.

### Recall and resilience

| Table | Purpose |
| --- | --- |
| `search_documents` | Disposable, versioned recall projection over events, timeline, summaries, chunks, and entities. |
| `processing_failures` | Durable dead-letter records with stage, source, attempts, traceback, context, and resolution state. |

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

1. A device or poller submits a source envelope.
2. The base hashes and deduplicates the payload into `raw_logs`.
3. ARQ or the trusted runtime calls the extension `normalize(payload)` adapter.
4. The base writes `events`, applies deterministic/registered fact extraction,
   and writes recall documents with explicit lineage.
5. Sessionization, timeline generation, and daily summaries build episodic
   projections. Corrections supersede old derived records rather than erasing
   their provenance.

### Artifact intelligence

1. A user or `artifact_source` extension uploads original bytes and hints.
2. The base stores bytes by SHA-256 and creates durable processing state.
3. A worker extracts, OCRs, or transcribes into versioned cited chunks.
4. Chunks enter lexical recall immediately; embeddings are added asynchronously.
5. AI emits structured proposals with verbatim evidence.
6. Deterministic policy promotes grounded high-confidence proposals; other
   proposals await review.
7. Commitments can produce reminders, progress evidence, and revisable plans.

### Grounded chat

Chat fuses four sources:

- a bounded recent timeline and summary window;
- query-relevant hybrid `SearchDocument` results;
- directly retrieved artifact chunks with stable `[S#]` citations;
- query-relevant current graph facts.

The model is instructed to cite retrieved evidence, disclose missing evidence,
and never fabricate citation identifiers. AI usage is accounted by operation
and source context.

## 6. Extension contract

Manifests are validated by `loader/contracts.py` and declare an API version,
capabilities, permissions, optional `scheduler_cron`, and optional deterministic
`fact_mappings`.

| Capability | Extension responsibility |
| --- | --- |
| `collector` | Acquire proprietary/source-specific records. |
| `normalizer` | Convert a source payload into generic Event envelopes. |
| `artifact_source` | Submit original files or recordings and optional hints. |
| `notification_channel` | Deliver base-owned notifications through an approved channel. |

An optional `poller.py` exposes sync or async
`poll(config) -> list[dict]`. APScheduler invokes it from the manifest cron,
then the base deduplicates, persists, normalizes, indexes, and records failures.
Installed extensions are trusted Python code; manifest permissions are an
auditable declaration, not an OS sandbox.

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
