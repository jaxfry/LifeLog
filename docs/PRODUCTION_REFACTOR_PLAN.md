# LifeLog Production Refactor — Implementation Status

This document records the state of the production refactor. Historical design
intent that no longer matches the implementation has been removed; the
normative system description is [architecture.md](architecture.md), and the
extension ownership boundary is [EXTENSION_CONTRACT.md](EXTENSION_CONTRACT.md).

## Objective

Deliver a self-hosted modular monolith that can retain lifetime source data,
rebuild its derived timeline and memory, support domain extensions without
fragmenting intelligence, and provide evidence-grounded AI assistance.

## Completed phases

### Phase 0–2: platform, security, and ingestion — complete

- FastAPI/SQLModel async server and Alembic-owned schema.
- JWT user auth, bcrypt passwords, hashed device API keys, rate limits, CORS,
  trusted hosts, and production `SECRET_KEY` enforcement.
- Immutable/deduplicated raw ingestion and versioned normalized Events.
- Redis/ARQ integration degrades safely when Redis is unavailable.

### Phase 3–5: processing, AI enrichment, and APIs — complete

- Logical-date-aware 30-minute sessionization and cascading processing state.
- Timeline and daily-summary generation through the centralized LiteLLM service.
- Versioned prompts, response cache, and source-aware AI usage accounting.
- Authenticated timeline, summary, analytics, search, chat, files, commitment,
  extension, and kernel APIs.

### Phase 6–7: client migration and hardening — complete

- Python client buffer/sync recovery and ActivityWatch adapter updates.
- Services-layer migration completed; removed business logic from obsolete
  `core.*` modules and deleted stale aggregate model modules.
- SQLite-safe default tests plus isolated real-PostgreSQL/pgvector verification.
- Ruff policy codifies async/FastAPI/type/time conventions.

### Phase 8: memory kernel — complete

- Canonical entities, aliases, typed entity/event relations, valid-time windows,
  confidence, explicit source lineage, extraction versions, and supersession.
- Deterministic extraction registry and manifest-declared fact mappings.
- Idempotent backfill, explicit merge/history behavior, predicate filtering,
  bounded depth-1–3 graph traversal, and generic duration aggregates.
- Kernel facts participate in normalization correctness and grounded chat.

### Phase 9: artifact intelligence and action — complete

- Content-addressed authenticated uploads for users and permitted extensions.
- Native text/PDF extraction, scanned-document OCR, image analysis, and
  audio/video transcription.
- Versioned cited chunks and evidence-grounded entity/relation/commitment
  proposals with confidence policy and human review.
- Generic commitments, progress evidence, deterministic planning, durable
  notifications, and external delivery-channel boundary.

### Phase 10: lifetime recall and extension runtime — complete

- Rebuildable `SearchDocument` projection over Events, timeline entries, daily
  summaries, artifact chunks, and entities.
- PostgreSQL GIN full-text search and pgvector HNSW cosine search combined with
  reciprocal-rank fusion; lexical fallback when semantic infrastructure is absent.
- Query-aware chat fusion of recency, hybrid memories, cited chunks, and graph facts.
- Background embedding enrichment outside source-write transactions.
- Scheduled sync/async extension pollers, validated manifests/capabilities, and
  durable `ProcessingFailure` dead letters with retry/resolution APIs.

### Phase 11: source instances, universal capture, and staged work — complete

- Per-user `SourceConnection` instances separated from reusable installed
  extension definitions, with encrypted secret storage and manual/cron sync.
- Typed poll envelopes, durable post-processing checkpoints, stable external
  record/revision identity, canonical idempotency, and replacement supersession.
- Universal notes/photos/scans/audio/video/file captures with context/privacy
  hints, multi-artifact membership, immediate note recall, and source lineage.
- Offset-verified resumable uploads with status discovery, cancellation,
  expiration, and temporary-storage cleanup.
- Versioned `ProcessingJob` state for normalization, content extraction, and
  memory enrichment, surfaced through progressive capture readiness.
- Scheduled and manual acquisition enqueued through ARQ, redacted source
  failures, owned-device capture, deterministic classification/review, and
  dependency-aware stage cancellation.
- Consequential commitment revision with stale plan/reminder cancellation and a
  durable review notification.
- User-facing Capture and Sources pages in the web application.

### Phase 12: contextual life, privacy, and connector ergonomics — complete

- User-owned Life Areas as many-to-many context over shared memory, with
  declarative definitions and extension-contributed templates.
- Explicit/recognized context propagation across capture, sources, events,
  artifact chunks, graph facts, and commitments without record duplication.
- Purpose-scoped privacy policies enforced consistently by hybrid recall,
  artifact citations, graph context, Life Area views, and scoped AI chat.
- One Inbox and decision service for classification ambiguity, evidence-backed
  memory proposals, and consequential commitment revisions.
- A small typed `lifelog_sdk` with stable revisions, paged polling contracts,
  secret-safe contexts, normalizer validation, and connector contract tests.
- User-facing Life Areas, scoped Capture/Sources/chat controls, and Inbox pages.

### Phase 13: safe identity resolution and merging — complete

- Entities are owner-isolated and may carry a source namespace plus stable
  external identity; matching display names no longer create global identity.
- Merge suggestions are bounded, pair-stable Inbox decisions and never cross
  users or conflate distinct identities from the same source namespace.
- Merge application uses deterministic row locking, preserves aliases,
  non-conflicting metadata, explicit conflicts, context, and the stricter privacy
  policy, and retires stale recall documents.
- Every applied merge has decision lineage and a reversal snapshot. Reversal is
  guarded against later survivor edits, superseding merges, and external identity
  reuse instead of silently discarding newer knowledge.
- Scoped measurements and duration aggregates resolve historical members through
  the current entity family while enforcing owner, Life Area, and privacy policy.

## Verified baseline

As of 2026-08-13:

- Alembic revision `009` is the single head and applies cleanly to an empty
  PostgreSQL database. A controlled revision `008` upgrade verifies that an
  existing single-user entity is assigned to that owner; multi-user upgrades do
  not guess ownership.
- SQLite suite: 187 passed, with the PostgreSQL-only hybrid test skipped.
- PostgreSQL/pgvector suite: 185 passed and 3 environment-specific tests skipped.
- A controlled PostgreSQL test exercises both real cosine retrieval and lexical
  rank fusion.
- Alembic schema comparison, Ruff, the production web build, and diff whitespace
  checks pass.

## Remaining production work

These are not hidden as “deferred architecture”; they are the explicit next
hardening milestones.

### Operational scale

- Split large returned source pages into bounded fan-out normalization jobs when
  real connector volume demonstrates that per-connection ARQ jobs are too coarse.
- Add metrics and alerting for queue age, failure stages, embedding backlog,
  retrieval latency, transcription/OCR cost, and notification delivery.
- Exercise backup/restore, disaster recovery, storage retention, and large
  reindex operations against representative lifetime-sized data.
- Define content-storage encryption policy and external key-management/rotation
  operations for source secrets.

### Retrieval quality

- Evaluate embedding models and fusion weights on a versioned personal-recall
  benchmark rather than relying only on correctness tests.
- Replace substring entity discovery with indexed alias/entity recall when graph
  cardinality warrants it.
- Add cautious embedding-assisted entity-resolution proposals; never auto-merge
  identities solely from vector similarity.
- Add contradiction review and optional graph-community summaries when enough
  long-term data exists to validate their usefulness.

### Extension safety and ecosystem

- Decide on an isolation model for third-party extensions. Current installed
  extensions are managed-trust Python code; declared permissions are auditable
  but not sandbox enforcement.
- Add an isolation boundary and resource budgets for high-volume pollers, plus
  idempotent notification-channel delivery receipts.
- Build packaging/signing/upgrade rules before introducing an extension marketplace.

### Product validation

- Run an end-to-end school-domain pilot with recordings, scanned assignments,
  due-date review, course mappings, generated study questions, planning, and
  progress adaptation.
- Measure citation accuracy, missed commitments, false entity merges, and plan
  usefulness with correction workflows enabled.
- Complete accessibility, privacy export/deletion, and user-facing recovery UX.

## Readiness statement

The base architecture is ready for first-party life-domain extensions and
serious personal use. It is not yet evidence for unlimited lifetime scale or
untrusted third-party extension execution. Production readiness now depends on
operational validation, retrieval evaluation, backups, privacy controls, and
real longitudinal use—not missing foundational ownership boundaries.
