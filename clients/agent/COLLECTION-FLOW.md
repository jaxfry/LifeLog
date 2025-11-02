# Data Collection Flow - No Overlap Guarantee

## How the ActivityWatch Collector Prevents Duplicates

### The Collection Strategy

```
┌─────────────────────────────────────────────────────────────────────┐
│                    ActivityWatch Collector                          │
│                                                                     │
│  State (in-memory):                                                 │
│  • last_ts_per_bucket: {"bucket-id": "2025-10-31T21:48:15.287Z"}  │
│  • seen_event_ids: {"bucket-id": {3329, 3327, 3325, ...}}          │
└─────────────────────────────────────────────────────────────────────┘
```

### Poll Cycle (Every 15 seconds by default)

**Poll 1 (t=0s)** - Initial Collection
```
1. Query: GET /api/0/buckets/{bucket}/events?limit=100
   (No start parameter - fetches latest 100 events)

2. Response: 100 events with IDs [3329, 3327, 3325, ..., 3167]

3. Deduplication: None yet (seen_event_ids is empty)

4. Send ALL 100 events → LifeLog /ingest

5. Update state:
   • seen_event_ids = {3329, 3327, 3325, ..., 3167}
   • last_ts = "2025-10-31T21:26:05.838Z" (from event 3167)
```

**Poll 2 (t=15s)** - Incremental Collection
```
1. Query: GET /api/0/buckets/{bucket}/events?start=2025-10-31T21:26:05.838Z&limit=100
   (Fetches events AFTER last_ts - ActivityWatch uses inclusive start)

2. Response: 5 events [3330, 3329, 3327, 3167, 3165]
   (May include some overlapping events due to inclusive timestamp)

3. Deduplication Filter:
   • Event 3330: ✅ NEW (not in seen_event_ids) → KEEP
   • Event 3329: ❌ DUPLICATE (already sent) → SKIP
   • Event 3327: ❌ DUPLICATE → SKIP
   • Event 3167: ❌ DUPLICATE → SKIP
   • Event 3165: ✅ NEW → KEEP

4. Send ONLY [3330, 3165] → LifeLog /ingest (2 events)

5. Update state:
   • seen_event_ids += {3330, 3165}
   • last_ts = "2025-10-31T21:48:53.529Z" (from event 3330)
```

**Poll 3 (t=30s)** - Continued Collection
```
1. Query with new last_ts

2. Filter using seen_event_ids

3. Only send NEW events

4. Update state...
```

## Memory Management

```python
# Prevent unbounded memory growth
if len(seen_event_ids[bucket]) > 1000:
    # Keep only the most recent 500 event IDs
    oldest = sorted(seen_event_ids[bucket])[:500]
    seen_event_ids[bucket] -= set(oldest)
```

### Why This Works:
- ActivityWatch events are **immutable** (IDs never change)
- Events are queried in **reverse chronological order** (newest first)
- We keep the 500 **newest** IDs (most likely to be fetched again)
- Dropping old IDs is safe (we've moved past them with `last_ts`)

## End-to-End Pipeline

```
┌──────────────────┐
│  ActivityWatch   │  Tracks window focus every second
│  (Local Server)  │  Stores events with unique IDs
└────────┬─────────┘
         │ HTTP GET every 15s
         │ /api/0/buckets/{bucket}/events?start=...&limit=100
         ↓
┌─────────────────────────────────────────────────┐
│  AW Collector (subprocess)                      │
│  • Polls AW API with incremental timestamps     │
│  • Deduplicates by event ID (in-memory)         │
│  • Emits NDJSON to stdout                       │
│    {"type": "raw_log", "data": {...}}          │
└────────┬────────────────────────────────────────┘
         │ stdout pipe
         ↓
┌─────────────────────────────────────────────────┐
│  Agent Supervisor (runner.py)                   │
│  • Reads collector stdout line-by-line          │
│  • Enqueues to SQLite (queue.py)                │
│  • Offline-first with retry                     │
└────────┬────────────────────────────────────────┘
         │ Periodic flush (30s)
         │ POST /ingest with X-Device-Key
         ↓
┌─────────────────────────────────────────────────┐
│  LifeLog Server                                 │
│  • Creates RawLog (immutable)                   │
│  • Triggers processor via routing               │
│    activitywatch-source → aw-processor          │
└────────┬────────────────────────────────────────┘
         │ Processor run()
         ↓
┌─────────────────────────────────────────────────┐
│  AW Processor Actor                             │
│  • For each event in raw_log:                   │
│    - Parse timestamp, duration, app, title      │
│    - Create Event with type=computer-activity   │
│  • Links Event ← RawLog (many-to-many)          │
└────────┬────────────────────────────────────────┘
         │
         ↓
┌─────────────────────────────────────────────────┐
│  Database (Events table)                        │
│  • Queryable timeline                           │
│  • GET /api/v1/timeline                         │
└─────────────────────────────────────────────────┘
```

## Key Anti-Duplicate Guarantees

1. **Collector Level** (1st defense)
   - Event ID deduplication in-memory
   - Only new events are emitted to stdout

2. **Agent Queue** (2nd defense)  
   - SQLite AUTOINCREMENT ensures unique queue rows
   - No deduplication (collector already handled it)

3. **Server RawLog** (3rd defense)
   - Each ingestion creates a NEW RawLog
   - RawLogs are immutable (never updated)
   - Duplicates CAN exist here (same event, multiple RawLogs)

4. **Processor Level** (4th defense)
   - Creates Events from RawLogs
   - Could deduplicate by event ID + bucket if needed
   - Currently creates 1 Event per AW event (may duplicate if re-ingested)

## Potential Edge Cases

### Collector Restart
```
Problem: Collector loses in-memory seen_event_ids
Solution: First poll after restart fetches 100 events
          Some may be duplicates in RawLog
          
Mitigation: Processor could track (bucket, event_id) uniqueness
```

### Clock Skew
```
Problem: ActivityWatch server clock jumps backward
Solution: Timestamp-based filtering may miss events
          
Mitigation: Event ID filtering catches them anyway
```

### Very High Event Rate
```
Problem: >100 events in 15 seconds
Solution: Limit=100 means we might miss some
          
Mitigation: Decrease poll interval or increase limit
```

## Configuration Tuning

```json
{
  "aw_base_url": "http://127.0.0.1:5600",
  "interval_sec": 15,        // ↓ Lower = less latency, more overhead
  "buckets": [],             // Empty = auto-discover window buckets
  "event_limit": 100         // ↑ Higher = fewer missed events in busy periods
}
```

## Summary

**No overlaps sent to LifeLog** because:
- ✅ Collector deduplicates by event ID before sending
- ✅ Each unique event is only in ONE stdout line
- ✅ Agent queues each line exactly once
- ✅ Each queue item is ingested exactly once

**Duplicate RawLogs only occur if:**
- Collector restarts and re-fetches
- Manual re-ingestion
- Multiple agents collect the same bucket

These are **acceptable** since RawLogs are immutable records of ingestion.
