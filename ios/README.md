# LifeLog for iPhone

Native SwiftUI client for automatic, privacy-filtered, offline-first LifeLog
collection. The app targets iOS 18 and builds with Xcode 26.

## Run

1. Open `LifeLog.xcodeproj` in Xcode.
2. Select your personal development team for the LifeLog target.
3. Enable HealthKit and Background Modes (`Audio`, `Location updates`,
   and `Background processing`) in Signing & Capabilities.
4. Install on your iPhone and enter the LifeLog server URL and device API key
   under **You**.
5. Tap **Turn on LifeLog**, then enable the sensitive signals you want once from
   **Signals**. LifeLog requests each permission in context and continues
   collecting automatically afterward.

For a local HTTP development server, add a narrow App Transport Security
exception for that host or use HTTPS. The committed `Info.plist` intentionally
does not disable ATS globally.

## Automatic collection

- Core Location visits and significant-change monitoring; optional precise
  background trails.
- Core Motion classification with six-hour backfill plus pedometer summaries.
- HealthKit observer queries and background delivery for steps, heart rate,
  active energy, distance, sleep, and workouts.
- EventKit calendar and reminders, refreshed on store changes.
- New Photos-library metadata, capture time, dimensions, and approved location.
- User-approved Contacts identity metadata and Contacts-store changes.
- Connectivity, battery, charge, low-power, and thermal transitions.
- Batched signal transport, background-safe resumable artifact upload, and
  server-side SHA-256 verification before local originals become eligible for
  retention cleanup.

Audio recording is user-initiated because iOS does not permit a hidden
always-on microphone daemon. Once initiated, the `audio` background mode and
`AVAudioSession` allow it to continue while the screen is locked or another app
is foregrounded, subject to interruptions and system policy. Long recordings
roll into five-minute finalized segments sharing one capture identity; completed
segments are encrypted immediately and unfinished files are recovered on launch.

## Privacy and durability

Queue metadata is stored as an append-only encrypted journal, and artifacts are
AES-GCM encrypted in bounded 2 MB pieces using a device-only Keychain key. Files
also use iOS Data Protection and remain available after first unlock so
background delivery can append and synchronize them. Text exclusions and
redaction run before queue admission; binary originals are encrypted but are not
silently rewritten. Retry state and stable idempotency IDs are persisted locally.

See [`../docs/IOS_CLIENT_UX.md`](../docs/IOS_CLIENT_UX.md) for the complete UX
contract and operating-system boundaries.
