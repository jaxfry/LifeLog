# LifeLog for iPhone — Product and UX Specification

## Product promise

LifeLog for iPhone makes it effortless to preserve what is happening, safe to
trust the result, and easy to understand what LifeLog learned. The app should
feel like a quiet personal instrument rather than a data-collection dashboard.

Automatic collection is the default product posture. Manual capture supplements
signals that iOS can deliver in the background; it is not the main workflow.

The shortest complete description of the experience is:

> Capture now. It is immediately safe on this iPhone. LifeLog organizes and
> uploads it when possible, then asks only about consequential ambiguity.

V1 limits capability breadth, not design quality. Every included path must feel
finished, intentional, accessible, and trustworthy.

## Experience principles

1. **Preserve before organizing.** Capture must never wait for a category,
   course, Life Area, server response, or AI classification.
2. **Local success is real success.** Once encrypted bytes and metadata are
   durably committed on the device, the UI says `Saved on this iPhone`.
3. **Connectivity is a status, not a blocker.** Offline captures use the same
   flow and visual treatment as online captures.
4. **One capture can become a bundle.** A class can contain audio, bookmarks,
   photos, scans, and notes while remaining one coherent moment.
5. **Privacy happens before upload.** Exclusions and deterministic redaction run
   on the device before an item enters the network queue.
6. **AI is progressive and inspectable.** The original becomes available first;
   transcript, classification, graph facts, and proposals arrive progressively.
7. **No taxonomy homework.** Context is suggested from time, calendar, place,
   recent behavior, or a user-started mode. Correction is optional unless an
   ambiguity affects a deadline, identity, or sensitive action.
8. **One LifeLog.** School, health, work, and projects are lenses over the same
   memory. The iPhone never asks which extension should receive a capture.

## Information architecture

The primary app has four destinations and one universal action:

- **Today** — a quiet ambient timeline and the most relevant next action;
- **Ask** — the global or scoped LifeLog assistant;
- **Capture** — a central, always-reachable action, not a destination;
- **Inbox** — only decisions that genuinely need the user;
- **You** — devices, sources, privacy, retention, and local storage.

The upload queue is a status surface reached from the small safety/sync
indicator on Today. It is not a primary destination in the eventual product.
During early builds it may remain in the navigation for testing.

## Visual language

- Native SwiftUI structure, gestures, Dynamic Type, VoiceOver, Reduce Motion,
  and system material behavior.
- A near-black neutral canvas in dark mode and warm off-white canvas in light
  mode. Violet is used for LifeLog intelligence/context; green means durably
  safe or verified; amber means an inference or decision needs attention.
- Strong typography and restrained surfaces. The timeline is primarily open
  space and a chronological rail, not a wall of cards.
- Status is expressed in human language: `Safe on this iPhone`, `Uploading`,
  `Verified`, `Processing`, `Needs your answer`. Technical job names, offsets,
  checkpoints, retries, and graph predicates never appear in ordinary UI.
- Evidence state has a consistent visual grammar:
  - green dot: directly observed;
  - violet dot: deterministically classified or joined across sources;
  - amber dot: AI inference;
  - checkmark/edit mark: user confirmed or corrected.

## Today

Today answers three questions in order:

1. What is happening now?
2. What matters next?
3. What has LifeLog reconstructed so far?

The header contains the local date and a compact safety indicator such as
`Everything safe · 2 uploading`. Tapping it opens the queue.

The optional **Now** surface reports what LifeLog is already observing and may
offer a passive correction. It must not require the user to announce routine
life activities. For example, Calendar, place, motion, and device observations
can infer a likely class automatically. A manual action is appropriate only for
a capability iOS cannot begin invisibly, such as microphone recording.

Below it, the ambient timeline mixes visits, activity sessions, captures,
commitment changes, and inferred episodes. Each item has a one-line evidence
label and supports a detail sheet containing **Why does LifeLog think this?**,
source lineage, confidence, correction, exclusion, and deletion controls.

## Universal capture

The center Capture control opens a bottom sheet with four primary choices:

- **Record** — audio or an explicit context session;
- **Scan** — camera document scanning, whiteboard, receipt, or ordinary photo;
- **Note** — text, dictation, mood, measurement, expense, idea, or decision;
- **Import** — Files, Photos, or pasted/shared content.

Below these are optional context shortcuts such as Class, Study, Workout, and
Meeting. They never create different data models. They prefill intent and
context hints for the universal capture contract.

The capture control should also be exposed through:

- Action Button and Lock Screen controls;
- widgets and Shortcuts intents;
- a Share extension;
- Spotlight/App Intents;
- a long-press menu for Record, Scan, and Note.

## Class and long-form recording

A class recording is a foreground-started capture bundle.

### Before recording

The app suggests a context from Calendar, current location, and recent patterns.
The user can start immediately or tap the label to change it. Microphone
permission is requested only at this moment, with an explanation tied to the
requested action.

### During recording

The screen emphasizes duration, waveform, context, and the statement
`Recording safely on this iPhone`. Three secondary actions remain reachable:

- **Bookmark** — marks a significant timestamp with haptic confirmation;
- **Add photo** — appends a photo/scan to the same capture bundle;
- **Add note** — appends timestamped text or dictation.

Audio is written in short finalized segments to an encrypted local store. A
crash, force quit, or low-memory termination can lose at most the current small
segment, not the entire class. A Live Activity exposes duration, bookmark, and
finish controls while the session is active.

### Finishing

Finish returns immediately after the final local commit. The confirmation is:

```text
Class saved safely
Uploading in the background
```

The app does not force an extraction review. A later progressive result may say:

```text
Physics · 52 min
Transcript ready · 3 topics · 1 possible assignment

[ Review assignment ] [ Open class ]
```

## Scan and photo

The scanner defaults to automatic edge detection, perspective correction, and
multi-page bundling. Retake and reorder happen before the final local save, but
classification does not.

After saving, a compact result may progressively reveal OCR, likely context,
and a consequential proposal:

```text
Problem Set 4 · 3 pages
Likely Calculus 12
Due Friday at 9:00 AM

[ Add assignment ] [ Edit ]
```

The original image remains available even if OCR, upload, or AI processing
fails.

## Notes

The note composer opens directly into an empty field with dictation available.
There is no required title, folder, tag, Life Area, or type. Notes save locally
while typing and close with a downward swipe. Optional lightweight affordances
can recognize measurements, expenses, moods, and commitments after capture.

## Offline buffer and reliable upload

The local queue is an encrypted, durable state machine backed by SwiftData or
SQLite plus files protected with iOS Data Protection.

```text
draft → locally_committed → redacting → queued → uploading
      → server_verified → processing → ready
```

Required behavior:

- Generate one stable UUID idempotency key before the first local write.
- Commit metadata and the first durable artifact segment transactionally.
- Store content hashes, total size, local path, capture time, timezone, intent,
  context hints, privacy decision, and upload state.
- Use a background `URLSession` for transport and `BGProcessingTask` only as a
  best-effort opportunity to reconcile work.
- Create a server capture draft, then use the existing resumable-upload API.
- Before each chunk, query or retain the server offset; on `409`, adopt the
  server's expected offset rather than restarting blindly.
- Mark a local artifact verified only after upload completion returns the
  server-side content hash.
- Retry transient failures with bounded exponential backoff and jitter.
- Never delete the sole local original. Apply retention only after server
  verification and the configured grace period.
- Surface actionable failures in plain language, while automatic retries remain
  quiet.

Queue copy distinguishes three independent truths:

- `Safe on this iPhone` — local durability;
- `Verified by server` — remote preservation;
- `Searchable` — minimum useful processing completed.

## Device-local exclusions and redaction

Privacy rules execute before upload queue admission. The first release includes:

- excluded applications and shared-content origins;
- private-place geofences for ambient sources;
- capture-mode exclusions;
- deterministic patterns for API keys, bearer tokens, passwords, card/account
  numbers, email addresses, phone numbers, and custom regular expressions;
- an optional face/text-region preview for screenshots and photographs;
- `Exclude the last 15 minutes` for locally buffered ambient observations;
- per-capture `Keep only on this iPhone`, `Do not process`, and `Delete` actions.

Redaction creates a new upload derivative while retaining the original locally
according to the user's retention policy. The client stores an audit record of
which rule ran, its version, when it ran, and which ranges/regions were removed.
It must not store the removed plaintext in that audit record.

Rules are ordered and versioned. A capture records the rule-set version used so
the user can understand why a derivative differs from its original.

## Permissions and onboarding

There is no wall of permission prompts on first launch.

1. Pair with the self-hosted LifeLog server using a QR code or one-time code.
2. Explain local-first capture and choose a local retention duration.
3. Land on Today with camera/note capture already useful.
4. Request Camera, Microphone, Photos, Location, Motion, Health, Calendar, or
   Notifications only when the user enables the corresponding capability.
5. Present an honest capability status screen showing `Available`, `Needs
   permission`, `Limited by iOS`, or `Not supported on this device`.

Sideloading does not alter sandboxing, entitlements, privacy indicators,
permission prompts, or background execution limits. The UX must never promise
continuous capture that iOS cannot deliver reliably.

## Assistant on iPhone

The assistant defaults to whole-life retrieval. A scope control changes the
privacy/relevance lens, not an arbitrary context-window length. Natural phrases
such as `yesterday` or `this semester` determine time scope.

Answers display compact evidence chips. Tapping one opens the originating
capture, transcript timestamp, timeline episode, or deterministic tool result.
Follow-up turns preserve conversation continuity but never treat prior AI text
as evidence.

## Inbox

Inbox contains only decisions with material value:

- confirm or edit a detected deadline;
- choose between genuinely ambiguous contexts;
- approve a proposed plan change;
- merge two identities;
- resolve conflicting source revisions.

Items should be answerable inline with one primary action and one correction
path. Routine successful processing belongs on the capture detail, not Inbox.

## V1 product slice

V1 is intentionally complete around the most important loop:

1. Pair and authenticate one iPhone.
2. Capture notes, scans/photos, files, and long-form audio.
3. Bundle bookmarks, photos, and notes into a recording session.
4. Persist every capture locally before showing success.
5. Apply local exclusions and deterministic text redaction.
6. Upload through recoverable background sessions with visible verification.
7. Show Today, the queue, capture detail, progressive processing, Inbox, and
   grounded Assistant.
8. Provide Action Button, Lock Screen, Live Activity, Share extension, and core
   App Intents.

HealthKit, Screen Time, rich motion/location reconstruction, Reminders sync,
and ambient automation follow as source capabilities. Their absence must not
compromise the polish of V1's core loop.

## Mapping to the current LifeLog base

The base already provides the essential remote contract:

- user-owned device authentication;
- note and multipart capture;
- capture drafts and stable idempotency keys;
- ordered artifacts and context/privacy hints;
- resumable upload sessions with strict offsets;
- completion, cancellation, retry, progressive job state, and review;
- content-addressed storage, processing, retrieval, and grounded chat.

The iOS implementation should add a small client-facing reconciliation layer,
not a parallel memory model. Before production use, the base/client contract
should additionally expose a compact queue reconciliation response containing
server hash, artifact verification state, minimum-useful processing state, and
recommended retry timing. This avoids deriving user-facing reliability state
from internal processing-job details.

## Success criteria

- A capture can be completed in one deliberate action from the Lock Screen.
- No capture is lost when the network disappears, the app is killed, or the
  upload is interrupted.
- The user can always distinguish local safety, remote verification, and AI
  processing.
- No excluded or unredacted content leaves the device.
- Starting a class and bookmarking a moment are operable without looking for
  more than a glance.
- Every important AI interpretation can answer `Why?` and be corrected.
- The user never needs to understand extensions, event types, processing jobs,
  or context-window sizes.
