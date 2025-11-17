# Idempotency & Data Replay Protection

## Overview

LifeLog now includes comprehensive idempotency protections to prevent duplicate data ingestion when:
- Agents are reinstalled or reset
- Network failures cause retries
- Collectors replay old data
- Multiple identical events are sent

This document describes the multi-layered approach to ensuring data consistency and preventing duplicates.

## Architecture

### 1. Server-Side Deduplication

#### RawLog Idempotency
Each `RawLog` entry can be identified by:
- **External ID**: Stable identifier from the source (e.g., `activitywatch:bucket_name:event_id`)
- **Fingerprint**: SHA-256 hash of normalized data when external ID unavailable

**Database Schema:**
```sql
-- Unique constraints prevent duplicates
UNIQUE (source_actor_id, device_id, external_id)
UNIQUE (source_actor_id, device_id, fingerprint)
```

**Ingestion Flow:**
```python
# Server automatically computes fingerprint if external_id missing
raw_log, is_new = await IngestionService.create_raw_log(
    session, actor_id, data,
    external_id=external_id  # Optional
)

# Postgres ON CONFLICT DO NOTHING ensures atomic upsert
# Returns existing record if duplicate detected
```

#### Event Idempotency
Processed `Event` records include:
- **External ID**: Composite identifier (e.g., `processor:source:timestamp:hash`)
- **Unique constraint** on `(processor_actor_id, external_id)`

Prevents duplicate processing of the same raw data by the same processor.

#### TimelineBlock Idempotency
Timeline generation is idempotent through:
- **Unique constraint** on `(actor_id, start_time, end_time)`
- Regenerating the same time period updates the existing block (via UPSERT)

### 2. Client-Side Sync Cursors

#### SyncCursor Table
Tracks watermarks per device-source combination:
```sql
CREATE TABLE synccursor (
    device_id INT,
    source_actor_id INT,
    cursor_key VARCHAR,  -- e.g., 'last_sync', 'bucket_name'
    cursor_value VARCHAR,  -- e.g., ISO timestamp, event ID
    last_updated TIMESTAMPTZ,
    UNIQUE (device_id, source_actor_id, cursor_key)
)
```

#### API Endpoints
**Get Cursor:**
```bash
GET /api/v1/device/cursor/{source_actor_slug}/{cursor_key}
```

**Update Cursor:**
```bash
PUT /api/v1/device/cursor/{source_actor_slug}/{cursor_key}
Body: {"cursor_value": "2024-11-16T12:34:56Z"}
```

#### Agent Integration
Agents fetch cursors on startup and update after successful sync:
```python
# On startup
last_sync = await client.get_cursor("aw-collector", "last_sync")

# After successful batch
await client.update_cursor("aw-collector", "last_sync", new_timestamp)
```

### 3. Collector Implementation

#### ActivityWatch Collector
**Before (vulnerable to replay):**
- Maintained local `seen_event_ids` set in memory
- Lost state on restart/reinstall
- Could send duplicates after reset

**After (replay-resistant):**
```python
# Each event includes stable external_id
external_id = f"{bucket_name}:{event_id}"

output = {
    "type": "raw_log",
    "data": {"bucket": bucket, "events": [event]},
    "external_id": external_id  # Server handles deduplication
}
```

No local deduplication needed - server guarantees idempotency.

## Migration Guide

### Database Migration
```bash
# Apply idempotency migration
docker exec lifelog_server alembic upgrade head
```

This adds:
- `external_id` and `fingerprint` columns to `rawlog`
- `external_id` column to `event`
- `synccursor` table
- Unique constraints for idempotency
- TimelineBlock unique constraint

### Backward Compatibility
- **Existing data**: No changes required
- **Old clients**: Continue working (fingerprint-based dedup)
- **New clients**: Benefit from external_id deduplication

### Collector Updates
Collectors should emit `external_id` when available:
```python
{
    "type": "raw_log",
    "data": {"key": "value"},
    "external_id": "source:unique_id"  # Optional but recommended
}
```

## Benefits

### 1. Reinstall Safety
- Agent can be reinstalled without duplicating historical data
- Server recognizes previously ingested events by external_id

### 2. Network Retry Safety
- Failed requests can be retried safely
- Duplicate submissions are silently deduplicated

### 3. Multiple Device Safety
- Different devices can sync the same source without conflicts
- Device-specific cursors prevent cross-contamination

### 4. Timeline Regeneration Safety
- Regenerating timelines for the same period updates existing blocks
- No duplicate timeline entries

## Testing Idempotency

### Test 1: Duplicate Ingestion
```python
# Send the same event twice
for _ in range(2):
    response = await client.ingest(
        "aw-collector",
        {"bucket": "test", "events": [...]},
        external_id="test:event:123"
    )
    
# Only one RawLog should exist
assert RawLog.count(external_id="test:event:123") == 1
```

### Test 2: Agent Reinstall
```bash
# Install agent, sync data
./agent/run.sh

# Simulate reinstall (clear local state)
rm -rf ~/.lifelog/agent

# Restart - should not duplicate data
./agent/run.sh
```

### Test 3: Network Failure Retry
```python
# Simulate network retry
for attempt in range(3):
    try:
        await client.ingest(...)
        break
    except NetworkError:
        continue  # Safe to retry with same external_id
```

## Monitoring

### Deduplication Metrics
Track duplicate detection rate:
```python
# In ingestion service
if not is_new:
    logger.info(
        f"Duplicate detected: source={source}, "
        f"external_id={external_id}"
    )
```

### Cursor Health
Monitor cursor lag:
```sql
SELECT 
    source_actor_id,
    cursor_key,
    last_updated,
    NOW() - last_updated as lag
FROM synccursor
WHERE NOW() - last_updated > INTERVAL '1 hour';
```

## Future Enhancements

### 1. Cursor Cleanup
- Automatically remove stale cursors (e.g., >30 days old)
- Prune cursors for deleted devices/extensions

### 2. Duplicate Cleanup Migration
- One-time script to identify and remove pre-idempotency duplicates
- Use fingerprint matching on existing data

### 3. Metrics & Alerting
- Daily duplicate detection rate
- Alert on high duplicate rate (may indicate collector bug)

### 4. Event Deduplication at Processing Layer
- Extend idempotency to processor actors
- Prevent reprocessing when rerunning processors on same raw data

## Troubleshooting

### "Duplicate raw_log detected" logs
**Cause**: Client sending data already ingested
**Fix**: Verify collector is using cursors properly

### Cursor not advancing
**Cause**: Client failing to update cursor after successful sync
**Fix**: Check client error logs, ensure cursor update in success path

### Data still duplicating after upgrade
**Cause**: Collector not sending external_id
**Fix**: Update collector to include external_id in output

## API Reference

### Ingestion with Idempotency
```bash
POST /ingest/
{
    "source_actor_slug": "aw-collector",
    "data": {...},
    "external_id": "optional:stable:id",
    "idempotency_key": "alternative:key"
}
```

### Cursor Management
```bash
# Get cursor
GET /api/v1/device/cursor/{source_actor_slug}/{cursor_key}

# Update cursor
PUT /api/v1/device/cursor/{source_actor_slug}/{cursor_key}
{
    "cursor_value": "2024-11-16T12:34:56Z"
}
```

## Summary

The idempotency system provides multiple layers of protection:

1. **Server-side deduplication**: Via unique constraints on external_id/fingerprint
2. **Client-side cursors**: Prevent replaying old data after restart
3. **Collector integration**: Sources provide stable external_ids
4. **Timeline regeneration**: Idempotent via unique time range constraints

This ensures data consistency even with network failures, reinstalls, and retries.
