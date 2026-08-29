# LifeLog Base and Extension Contract

LifeLog extensions are source adapters. They connect LifeLog to a particular
system, device, service, or capture workflow. They do not own durable memory or
general intelligence infrastructure.

This contract describes the **Source** part of LifeLog's product model. Base
**Capabilities** and user-facing **Life Areas** are separate concepts; see
[PRODUCT_MODEL.md](PRODUCT_MODEL.md). Prefer source-specific adapters such as
Canvas or a folder watcher over a broad extension that attempts to own the
entire School experience.

## Responsibility boundary

| Concern | LifeLog base | Extension |
| --- | --- | --- |
| Source authentication and polling | Provides secrets/config storage and scheduling | Implements the source-specific API or device protocol |
| Collection and cursors | Provides ingestion, deduplication, retries, and immutable storage | Produces source records and advances only source-specific cursors |
| Normalization | Validates the Event envelope and versions processing | Maps proprietary payload fields into generic Events |
| Artifact upload | Owns content-addressed storage, processing state, and provenance | Captures or discovers files and submits them with optional hints |
| OCR and transcription | Owns provider selection, retry policy, text storage, chunking, and versions | May supply language/category hints; must not create a parallel OCR store |
| Memory extraction | Owns AI policy, evidence checks, proposals, confidence thresholds, review, graph identity, and supersession | May declare deterministic `fact_mappings`; may not write authoritative graph state directly |
| Retrieval and chat | Owns indexing, source selection, citations, authorization, and LLM accounting | May contribute UI suggestions, never bypass retrieval policy |
| Commitments and reminders | Owns lifecycle, scheduling, completion state, and notification outbox | May submit candidates or implement an explicitly permitted delivery channel |
| User model and long-term adaptation | Owns durable, inspectable, correctable memory | Never keeps an authoritative shadow profile |

## Capabilities

An extension manifest declares a subset of:

- `collector`: obtains records from a source.
- `normalizer`: converts those records to the versioned Event envelope.
- `artifact_source`: uploads files or recordings to the base artifact API.
- `notification_channel`: delivers base-owned notification records through a
  user-approved channel. It does not decide what or when to notify.

Extensions declare `network`, `filesystem`, or `notifications` permissions.
Unknown API versions and malformed IDs are rejected by the manifest contract.

Collectors may provide a default `scheduler_cron` and a `poller.py` exposing
sync or async `poll(runtime) -> PollResult`. Each user creates a separate
`SourceConnection` with its own schedule, public config, encrypted secrets, and
durable stream checkpoint. The runtime object has this shape:

```json
{
  "connection_id": "uuid",
  "config": {"base_url": "https://school.example"},
  "secrets": {"access_token": "available only during invocation"},
  "checkpoint": {"updated_after": "opaque source cursor"}
}
```

Return records as typed envelopes with `payload` and, whenever the source
supports them, `external_key`, `external_revision`, `source_updated_at`, and an
`update_policy` of `append`, `replace`, or `snapshot`. Return the next checkpoint
only for data represented by that page. LifeLog advances it after all returned
records are durably ingested and processed, so replay is safe. Legacy list
returns are supported as append-only records without checkpointing.

The base owns connection scheduling, manual sync queuing, idempotency,
revision reconciliation, normalization, indexing, and durable failures. Pollers
are trusted installed code; manifest permissions are an auditable declaration,
not an operating-system sandbox.

For stable actionable fields, a manifest may also declare
`commitment_mappings` with `event_type`, `title_path`, optional due/not-before/
description paths, and confidence. The base owns revisions: when the same
external record changes a deadline or other consequential field, LifeLog
supersedes the old commitment, cancels stale reminders/plans, and asks the user
to review the replacement.

## Deterministic fact mappings

When a normalized event has a stable domain field, extensions should declare a
mapping instead of asking an LLM to rediscover it. For example:

```json
{
  "event_type": "assignment_received",
  "predicate": "for_course",
  "object_entity_type": "course",
  "value_path": "course.name",
  "transform": "none",
  "confidence": 1.0
}
```

LifeLog resolves the entity, writes explicit event/file lineage, and applies
idempotency and supersession. AI extraction remains base-owned for facts that
cannot be mapped reliably.

## Artifact-source rule

An artifact-source extension submits the original bytes, MIME type,
`source_extension_id`, and optional descriptive hints. After upload, the base
performs all generic processing:

```text
immutable file -> OCR/transcription/text extraction -> versioned chunks
 -> evidence-grounded proposals -> reviewed/promoted memory
 -> retrieval with citations -> commitments and notifications
```

This means a school capture extension, email extension, medical-record import,
or meeting recorder all reuse the same pipeline. Domain-specific behavior stays
small and replaceable while the user's lifetime memory remains coherent.
