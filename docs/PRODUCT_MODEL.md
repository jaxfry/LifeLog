# LifeLog Product Model

## One life, one memory

LifeLog is one application and one coherent, provenance-backed memory of a
person's life. School, work, health, relationships, projects, and other parts
of life must not become separate databases, assistants, or incompatible plugin
silos.

The product should be designed from the user's experience inward:

1. **Capture** something happening now.
2. **See** what matters now.
3. **Ask** about anything LifeLog remembers.

Implementation boundaries exist to make those experiences dependable. Users
should not need to understand Events, fact mappings, graph predicates,
processing workers, or which extension owns a record.

## The three-part distinction

LifeLog distinguishes **Capabilities**, **Sources**, and **Life Areas**. All
three contribute to the same underlying timeline, artifact store, memory graph,
commitment system, retrieval projection, and assistant.

### 1. Capabilities

Capabilities are reusable things the LifeLog application can do:

- take a photo or scan a document;
- record audio;
- write a note;
- import or upload a file;
- perform OCR and transcription;
- capture location or other device observations;
- retrieve memories and answer with citations;
- plan work and deliver notifications.

General-purpose capture and intelligence capabilities belong to the LifeLog
base. A School experience may present an “Record class” shortcut, but it uses
the same base recording, transcription, storage, and provenance pipeline as a
meeting, medical appointment, or personal voice note.

### 2. Sources

Sources connect LifeLog to systems or places where data originates:

- Canvas or Google Classroom;
- Google Calendar;
- ActivityWatch;
- a filesystem folder;
- email, health data, Spotify, or a device sensor.

A source adapter owns only source-specific work: authentication, acquisition,
pagination/cursors, proprietary formats, and normalization into LifeLog's
generic input contracts. The base owns durable ingestion, updates and
supersession, processing, memory, retrieval, actions, and failure handling.

In the UI, users should experience this as **Sources -> Add Source -> Connect**,
not as installing a miniature application with its own memory model.

Prefer source-oriented integrations such as `com.lifelog.canvas` over one large
`com.lifelog.school` integration that attempts to own every school workflow.
Multiple sources can contribute to the same Life Area.

### 3. Life Areas

Life Areas are user-facing lenses and workflows over the unified LifeLog
memory. Examples include:

- School;
- Work;
- Health;
- Relationships;
- Projects;
- Finances.

A Life Area may provide vocabulary, views, cards, recognition hints, planning
policies, suggested questions, and scoped assistant entry points. It does not
own the records it displays.

The internal mechanism is **context**: entities, relationships, time, source
lineage, and user organization determine which memories are useful in a view.
One memory can appear in multiple areas without being copied. A conversation
with a teacher may be relevant to School and Relationships. Sleep can inform a
global plan without exposing health details in a school-scoped conversation.

“School Hub” is reasonable UI language. `LifeArea` or `Context` may be used in
internal APIs, but the product must preserve the non-silo invariant.

## Unified experience

The main application should make capture universal and context lightweight:

```text
Today
• Chemistry class at 9:00
• Calculus assignment due tomorrow
• Work shift at 4:00

[ Take photo ] [ Record audio ] [ Write note ] [ More ]

Ask LifeLog anything…
```

LifeLog may suggest context from the schedule, time, location, recent behavior,
or learned patterns. The user can confirm or change it, but capture must not be
blocked on taxonomy decisions.

### Example: photographing an assignment

The user takes a photo. LifeLog stores the original, performs OCR, preserves
citable evidence, recognizes a likely assignment, associates it with a course,
and proposes a commitment:

```text
Detected:
Calculus 12 — Problem Set 4
Due Friday at 9:00 AM

[ Confirm ] [ Edit ]
```

The user does not select an extension, Event type, entity type, or predicate.
If the course is ambiguous, LifeLog asks one small question and retains that
correction for future organization.

### Example: recording a class

The base recording capability may suggest the current School context:

```text
Suggested: Calculus 12 — Room 204
[ Start recording ]
```

After capture, the base transcribes and can present topics, cited excerpts,
possible assignments, and practice generation. The recording, transcript,
handout, course, commitments, and study history remain part of the same LifeLog
memory used by global chat and planning.

### Example: cross-life planning

When asked when to complete an assignment, LifeLog may consider the deadline,
remaining work, class and work schedules, existing commitments, actual progress,
and user-approved patterns such as productive times or sleep. If planned work
does not happen, LifeLog revises the plan rather than creating a disconnected
school-only schedule.

Cross-area use must respect explicit privacy boundaries. Relevance does not
automatically grant a scoped experience access to every sensitive detail.

## Review and correction

The user-facing review surface is a single quiet **Inbox**, not a collection of
technical “memory proposal” screens. It should ask only about ambiguity or
consequential changes, for example:

- Is this document for Calculus or Physics?
- Canvas says the due date moved. Update the commitment and plan?
- Are `CS101` and `Computer Science 101` the same course?
- A recording mentioned work but provided no due date.

Default policy:

- Searchable extraction can happen automatically.
- Reversible, low-risk organization should usually happen automatically.
- Deadlines, identity merges, grades, and consequential actions may require
  confirmation depending on confidence and user policy.
- Destructive actions and sensitive inferences require confirmation.

Every important memory must support “Why does LifeLog believe this?” The user
must be able to inspect evidence, correct associations, merge or separate
identity, exclude a capture, and forget information subject to retention rules.
An identity merge must retain its decision and evidence lineage and remain
reversible until later edits or identity reuse would make automatic reversal
unsafe; in that case the system must ask for a new explicit correction.

## Assistant behavior

There is one LifeLog assistant. It may operate globally or through a scoped
entry point such as School or a particular course.

A scope changes retrieval and presentation; it does not instantiate a separate
assistant or memory. Deterministic operations—duration totals, numeric
aggregates, deadlines, calendar conflicts, and plan updates—should be computed
by base services/tools. AI selects, explains, and synthesizes those results but
must not approximate calculations from a small context window.

## Design rules derived from the experience

1. **Capture first, classify progressively.** Preserve source material before
   requiring organization.
2. **Strict core, forgiving edges.** Provenance, identity, updates, and actions
   are strict internally; user capture and common integration development are
   simple and declarative.
3. **No domain silos.** Areas filter and organize shared memory; they do not own
   parallel timelines, graphs, artifact stores, or assistants.
4. **Sources are narrow.** A connector should not implement OCR, transcription,
   retrieval, planning, or an authoritative user profile.
5. **Capabilities are reusable.** If camera, audio, OCR, planning, or
   notifications help multiple areas, they belong in the base.
6. **Context is many-to-many.** A memory may matter to several areas, entities,
   commitments, and time periods.
7. **Evidence before confidence.** AI-derived claims retain citations and
   uncertainty; corrections are durable and inspectable.
8. **Consequential changes are visible.** Source updates that move deadlines or
   plans must be reconciled, not silently appended as conflicting truth.
9. **Privacy follows purpose.** Global memory does not imply unrestricted
   disclosure in every scoped view.
10. **Extensions should feel small.** The normal source integration should
    implement collection and normalization through a supported SDK or
    declarative mapping, with Python as an escape hatch.

## Implementation direction

The current extension contract is the Source layer. Future product work should
not overload that contract with Life Area UI or base capture features.

Implemented base foundations:

- a universal capture model/API for photos, recordings, scans, notes, and files,
  with optional intent, context, and privacy hints plus recoverable uploads;
- encrypted per-user source connections, durable cursors/checkpoints, typed
  external identity/revision contracts, and replacement supersession;
- versioned stage-level processing jobs and progressive capture status;
- declarative entity, relationship, and commitment mappings for common sources;
- first-party Capture and Sources pages that hide internal Events, predicates,
  checkpoints, and processing jobs behind capture-first language;

Implemented context and connector foundations:

- a first-class, many-to-many context mechanism for Life Area organization;
- declarative Life Area definitions for views, terminology, cards, suggested
  questions, and policies;
- scoped retrieval/privacy policy enforced by the base;
- a connector SDK that hides ingestion, retries, checkpoints, and update
  reconciliation from ordinary extension authors.

New work must continue to follow this product model: do not place a generally
reusable capability into a domain connector, and do not create a domain-owned
memory silo to simulate a Life Area.
