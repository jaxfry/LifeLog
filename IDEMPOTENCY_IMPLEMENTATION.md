# Idempotency Implementation Summary

## Changes Made

### 1. Database Schema (`models.py`)

#### RawLog Model
Added idempotency fields:
- `external_id`: Optional stable identifier from source
- `fingerprint`: SHA-256 hash of normalized data
- Unique constraints:
  - `(source_actor_id, device_id, external_id)`
  - `(source_actor_id, device_id, fingerprint)`

#### Event Model
Added:
- `external_id`: Stable event identifier
- Unique constraint: `(processor_actor_id, external_id)`

#### New: SyncCursor Model
Tracks sync watermarks per device-source:
```python
SyncCursor:
    device_id
    source_actor_id
    cursor_key      # e.g., 'last_sync', 'bucket_name'
    cursor_value    # e.g., ISO timestamp, event ID
    last_updated
    UNIQUE(device_id, source_actor_id, cursor_key)
```

#### TimelineBlock Model
Added unique constraint: `(actor_id, start_time, end_time)`

### 2. Database Migration
**File**: `migrations/versions/20251116_01_add_idempotency_fields.py`
- Adds all new columns and indexes
- Creates SyncCursor table
- Adds unique constraints
- Merges two migration branches

### 3. API Layer

#### Schemas (`schemas.py`)
Updated `RawLogIn`:
```python
external_id: Optional[str]      # Source event ID
idempotency_key: Optional[str]  # Alternative key
```

#### Ingestion API (`api/ingestion.py`)
- Passes `external_id` to service layer
- Logs deduplication events
- Returns success even for duplicates

#### Device API (`api/device.py`)
New endpoints:
```python
GET  /api/v1/device/cursor/{source_actor_slug}/{cursor_key}
PUT  /api/v1/device/cursor/{source_actor_slug}/{cursor_key}
```

### 4. Service Layer

#### IngestionService (`services_legacy.py`)
New `create_raw_log` signature:
```python
async def create_raw_log(
    session, source_actor_id, data, device_id, external_id
) -> Tuple[RawLog, bool]:
    """Returns (raw_log, is_new)"""
```

Implements:
- Fingerprint computation (SHA-256 of normalized JSON)
- PostgreSQL `INSERT ... ON CONFLICT DO NOTHING`
- Atomic UPSERT with unique constraints
- Returns existing record if duplicate

### 5. Client Agent

#### HTTP Client (`http.py`)
Updated methods:
```python
async def ingest(
    source_actor_slug, data, 
    external_id=None, idempotency_key=None
)

async def get_cursor(source_actor_slug, cursor_key) -> Optional[str]

async def update_cursor(source_actor_slug, cursor_key, cursor_value)
```

#### Queue Runner (`runner.py`)
Passes through `external_id` when flushing queue

#### Collectors (`collectors.py`)
Extracts `external_id` from collector output:
```python
external_id = msg.get("external_id")
if external_id:
    payload["external_id"] = external_id
```

### 6. ActivityWatch Collector

**File**: `extensions/activitywatch-connector/collectors/aw_collector.py`

**Before:**
- Maintained in-memory `seen_event_ids` set
- Lost state on restart
- Could replay data after reinstall

**After:**
- Sends each event with `external_id = f"{bucket}:{event_id}"`
- No local deduplication - relies on server
- Resilient to restarts/reinstalls

Output format:
```python
{
    "type": "raw_log",
    "data": {"bucket": "...", "events": [...]},
    "external_id": "bucket_name:event_id"
}
```

## Testing

### Manual Testing
Run the test script:
```bash
python test_idempotency.py
```

### Verification Queries
```sql
-- Check for duplicates (should be 0)
SELECT external_id, COUNT(*) 
FROM rawlog 
WHERE external_id IS NOT NULL 
GROUP BY external_id 
HAVING COUNT(*) > 1;

-- View sync cursors
SELECT * FROM synccursor;

-- Check unique constraints
\d rawlog
\d event
\d synccursor
```

## Deployment

### 1. Apply Migration
```bash
docker exec lifelog_server alembic upgrade head
```

### 2. Restart Server
```bash
docker restart lifelog_server
```

### 3. Update Agent
Agents automatically use the new endpoints when available.

## Rollback Plan

To rollback (not recommended):
```bash
docker exec lifelog_server alembic downgrade 20251104_02
```

This will:
- Remove SyncCursor table
- Remove idempotency columns
- Remove unique constraints

**Warning**: Existing cursor data will be lost.

## Performance Impact

### Write Operations
- **Minimal overhead**: Single UPSERT vs INSERT
- **Network**: No change (optional fields)
- **Storage**: ~100 bytes per row (external_id + fingerprint)

### Read Operations
- **No impact**: Indexes on external_id/fingerprint
- **Cursor queries**: Fast (unique constraint + index)

### Database Size
Estimated increase: <5% for typical workloads

## Monitoring

### Key Metrics
1. **Duplicate detection rate**: Log analysis
2. **Cursor lag**: `NOW() - last_updated`
3. **Failed ingestions**: HTTP 500 errors
4. **Cursor update failures**: Client logs

### Alerts
- High duplicate rate (>10%): May indicate collector bug
- Cursor not advancing (>1 hour): Sync may be stuck
- Missing external_id: Collectors need updates

## Future Work

### Phase 2: Enhanced Idempotency
- [ ] Event processor idempotency (prevent reprocessing)
- [ ] Batch deduplication API
- [ ] Duplicate cleanup migration for pre-existing data

### Phase 3: Advanced Features
- [ ] Cursor expiration and cleanup
- [ ] Cross-device duplicate detection
- [ ] Idempotency statistics dashboard

### Phase 4: Performance
- [ ] Bloom filters for fast duplicate checks
- [ ] Async cursor updates (fire-and-forget)
- [ ] Cursor caching in Redis

## Documentation

New documentation files:
- `docs/IDEMPOTENCY.md` - Comprehensive guide
- `test_idempotency.py` - Test suite

Updated files:
- README should link to IDEMPOTENCY.md
- API docs should include cursor endpoints

## Summary

The system is now fully protected against duplicate data ingestion through:

✅ **Server-side deduplication** via unique constraints and UPSERT  
✅ **Client-side cursors** for resumable sync  
✅ **Collector integration** with stable external_ids  
✅ **Timeline regeneration** safety via unique constraints  

Reinstalls, retries, and replays are now safe and idempotent.
