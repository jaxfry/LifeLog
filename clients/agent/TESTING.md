# LifeLog Agent & ActivityWatch Extension - Testing Guide

This guide walks you through testing the complete flow from agent setup to data collection.

## Prerequisites

- LifeLog server running (Docker Compose)
- Python 3.11+ installed
- Either:
  - ActivityWatch installed and running at http://127.0.0.1:5600, OR
  - Use the mock AW server included with the agent

## Quick Test (5 minutes)

### 1. Start the Mock ActivityWatch Server

In a terminal:
```bash
cd clients/agent
python3 mock_aw_server.py
```

This simulates ActivityWatch without needing the full install.

### 2. Run the Quickstart

In a new terminal:
```bash
cd clients/agent
./quickstart.sh
```

This will:
- ✅ Register the ActivityWatch extension
- ✅ Set up actor routing (activitywatch-source → aw-processor)
- ✅ Create a device and API key
- ✅ Initialize the agent with the key

### 3. Run the Agent

```bash
cd clients/agent
./run.sh
```

The agent will:
1. Poll the server for installed extensions (every 30 seconds)
2. Download the ActivityWatch extension package
3. Start the collector subprocess
4. Collector reads from mock AW server (every 15 seconds)
5. Queue events offline
6. Send to `/ingest` endpoint

### 4. Verify Data Flow

Check the agent terminal for:
```
activitywatch collector started
```

Check the server logs for:
```
POST /ingest/ - 200 OK
```

### 5. View Events

Get a JWT token:
```bash
curl -X POST "http://localhost:8000/api/v1/auth/token" \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "username=admin&password=admin123"
```

View timeline:
```bash
curl "http://localhost:8000/api/v1/timeline" \
  -H "Authorization: Bearer <YOUR_TOKEN>"
```

## Testing with Real ActivityWatch

If you have ActivityWatch installed:

1. Make sure it's running at http://127.0.0.1:5600
2. Skip the mock server step
3. Run the quickstart and agent normally

The collector will auto-discover window buckets like `aw-watcher-window_<hostname>`.

## Troubleshooting

### Agent won't start
- Check `~/.lifelog/agent/config.json` exists
- Verify server is running: `curl http://localhost:8000/health`

### No data being collected
- Check mock AW server is running: `curl http://127.0.0.1:5600/api/0/buckets`
- Look for errors in agent terminal
- Check `~/.lifelog/agent/queue.db` - should grow as data is queued

### Data not appearing in timeline
- Check server logs for processing errors
- Verify actor routing: `curl http://localhost:8000/internal/actor-routing/`
- Check raw logs were ingested: Look in server database

### Collector crashes
- Check environment in agent terminal
- Verify collector config in device metadata
- Look at stderr from collector subprocess

## Manual Testing Steps

### 1. Test Extension Registration
```bash
curl -X POST "http://localhost:8000/internal/extensions/" \
  -H "Authorization: Bearer <TOKEN>" \
  -H "Content-Type: application/json" \
  -d '{
    "slug": "activitywatch-connector",
    "name": "ActivityWatch Connector",
    "version": "1.0.0"
  }'
```

### 2. Test Device Creation
```bash
curl -X POST "http://localhost:8000/internal/devices/" \
  -H "Authorization: Bearer <TOKEN>" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Test Mac",
    "platform": "macos"
  }'
```

### 3. Test Manual Ingestion
```bash
curl -X POST "http://localhost:8000/ingest/" \
  -H "X-Device-Key: <YOUR_DEVICE_KEY>" \
  -H "Content-Type: application/json" \
  -d '{
    "source_actor_slug": "activitywatch-source",
    "data": {
      "bucket": "test",
      "events": [
        {
          "timestamp": "2025-10-31T12:00:00Z",
          "duration": 60,
          "data": {
            "app": "Code",
            "title": "Testing"
          }
        }
      ]
    }
  }'
```

### 4. Test Processing Trigger
```bash
# Get raw_log_id from previous ingestion response
curl -X POST "http://localhost:8000/internal/processing/trigger/<raw_log_id>" \
  -H "Authorization: Bearer <TOKEN>"
```

## File Locations

- Agent config: `~/.lifelog/agent/config.json`
- Agent queue: `~/.lifelog/agent/queue.db`
- Extension packages: `~/.lifelog/agent/extensions/`
- Server extensions: `server/extensions/activitywatch-connector/`

## Expected Data Flow

```
ActivityWatch (5600)
  ↓
Collector (subprocess)
  ↓ stdout NDJSON
Agent Supervisor
  ↓ SQLite queue
Periodic Flush
  ↓ POST /ingest
LifeLog Server
  ↓ Creates RawLog
Auto/Manual Processing
  ↓ Processor Actor
Events Created
  ↓ GET /api/v1/timeline
Client Apps
```
