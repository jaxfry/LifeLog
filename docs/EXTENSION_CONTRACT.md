# LifeLog Base and Extension Contract

LifeLog extensions are source adapters. They connect LifeLog to a particular
system, device, service, or capture workflow. They do not own durable memory or
general intelligence infrastructure.

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

Collectors may include `scheduler_cron` and a `poller.py` exposing sync or async
`poll(config) -> list[dict]`. The base schedules it, deduplicates returned
envelopes, normalizes them, indexes them, and records durable failures. Pollers
are trusted installed code; manifest permissions are an auditable declaration,
not an operating-system sandbox.

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
