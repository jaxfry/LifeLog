# Idempotency Quick Reference

## For Developers

### Sending Data with Idempotency

**Python (Agent/Client):**
```python
await client.ingest(
    "aw-collector",
    {"bucket": "test", "events": [...]},
    external_id="bucket:event_id"  # Stable, unique identifier
)
```

**HTTP API:**
```bash
curl -X POST http://localhost:8000/ingest/ \
  -H "X-Device-Key: YOUR_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "source_actor_slug": "aw-collector",
    "data": {"bucket": "test", "events": [...]},
    "external_id": "bucket:event_id"
  }'
```

### Cursor Management

**Save Cursor:**
```python
await client.update_cursor(
    "aw-collector", 
    "last_sync", 
    "2024-11-16T12:34:56Z"
)
```

**Resume from Cursor:**
```python
last_sync = await client.get_cursor("aw-collector", "last_sync")
if last_sync:
    # Resume from last_sync timestamp
else:
    # First sync, start from beginning
```

## For Collectors

### Output Format
```python
{
    "type": "raw_log",
    "data": {...},
    "external_id": "source:stable_id"  # Include this!
}
```

### Best Practices
1. **Always provide external_id** when available
2. Use format: `{source}:{unique_id}`
3. IDs must be stable across restarts
4. IDs should be globally unique per source

### Examples

**ActivityWatch:**
```python
external_id = f"{bucket_name}:{event_id}"
```

**File System Watcher:**
```python
external_id = f"fs:{file_path}:{mtime_timestamp}"
```

**Location Tracker:**
```python
external_id = f"location:{device_id}:{timestamp}"
```

## For System Operators

### Check Deduplication Rate
```sql
-- Count duplicates caught today
SELECT COUNT(*) FROM rawlog 
WHERE ingested_at >= NOW() - INTERVAL '1 day'
AND external_id IN (
    SELECT external_id FROM rawlog 
    GROUP BY external_id HAVING COUNT(*) > 1
);
```

### Monitor Cursor Health
```sql
-- Find stale cursors (not updated in >1 hour)
SELECT 
    d.name as device,
    a.slug as source,
    sc.cursor_key,
    sc.last_updated,
    NOW() - sc.last_updated as lag
FROM synccursor sc
JOIN device d ON sc.device_id = d.id
JOIN actor a ON sc.source_actor_id = a.id
WHERE NOW() - sc.last_updated > INTERVAL '1 hour'
ORDER BY lag DESC;
```

### Verify Unique Constraints
```sql
-- Should return 0 rows (no duplicates)
SELECT external_id, COUNT(*) 
FROM rawlog 
WHERE external_id IS NOT NULL 
GROUP BY external_id 
HAVING COUNT(*) > 1;
```

## Troubleshooting

### "Duplicate raw_log detected" in logs
✅ **Expected behavior** - idempotency working correctly  
ℹ️ Client is resending data that was already ingested  
💡 Check if collector is using cursors to avoid replays

### Data still duplicating
❌ **Collector not sending external_id**  
💡 Update collector to include stable IDs  
💡 Verify output format includes `external_id` field

### Cursor not advancing
❌ **Client not updating cursor after sync**  
💡 Check client code updates cursor on success  
💡 Verify cursor update endpoint returns 200

### High duplicate rate (>10%)
⚠️ **Potential collector bug**  
💡 Check collector is using proper cursor/watermark  
💡 Verify external_id generation is stable

## Migration Checklist

- [x] Database migration applied
- [x] Server restarted with new code
- [x] RawLog table has external_id/fingerprint columns
- [x] Event table has external_id column
- [x] SyncCursor table exists
- [x] Unique constraints verified
- [ ] Collectors updated to send external_id
- [ ] Agents using cursor endpoints
- [ ] Monitoring dashboards updated
- [ ] Documentation updated

## API Endpoints

### Ingestion
```
POST /ingest/
Body: {
    "source_actor_slug": "...",
    "data": {...},
    "external_id": "...",        # Optional
    "idempotency_key": "..."     # Optional
}
```

### Cursor Management
```
GET /api/v1/device/cursor/{source_actor_slug}/{cursor_key}
Response: {
    "cursor_key": "...",
    "cursor_value": "...",
    "last_updated": "..."
}

PUT /api/v1/device/cursor/{source_actor_slug}/{cursor_key}
Body: {"cursor_value": "..."}
```

## Testing Commands

```bash
# Run idempotency tests
python test_idempotency.py

# Check database schema
docker exec lifelog_db psql -U lifelog -d lifelog_db -c "\d rawlog"

# View recent duplicates
docker logs lifelog_server 2>&1 | grep "Duplicate raw_log detected" | tail -10

# Check cursor count
docker exec lifelog_db psql -U lifelog -d lifelog_db -c "SELECT COUNT(*) FROM synccursor;"
```

## Key Design Decisions

1. **Server-side deduplication**: Centralizes logic, survives client reinstalls
2. **Fingerprint fallback**: Works even without external_id
3. **Postgres UPSERT**: Atomic, race-condition free
4. **Device-scoped cursors**: Prevents cross-device conflicts
5. **Optional fields**: Backward compatible with old clients

## Performance Notes

- **Ingestion**: ~5% slower (UPSERT vs INSERT)
- **Storage**: +100 bytes per row
- **Queries**: No impact (indexed fields)
- **Cursors**: <1ms per operation

## Support

- **Documentation**: `docs/IDEMPOTENCY.md`
- **Implementation**: `IDEMPOTENCY_IMPLEMENTATION.md`
- **Tests**: `test_idempotency.py`
