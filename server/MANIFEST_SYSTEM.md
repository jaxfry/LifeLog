# Extension Manifest System - Implementation Guide

## Overview

The LifeLog extension manifest system is now fully implemented per the architecture v3.3 specification. Extensions are declaratively defined in `manifest.json` files and installed via the Internal API.

## What's New

### Core Components

1. **Manifest Schema (`manifest.py`)**
   - Complete Pydantic models for `manifest.json` structure
   - Validates server-side actors, event types, prompt templates
   - Validates client-side collectors and UI components with permissions
   - Example schema included with proper typing

2. **Processing Status Constants (`constants.py`)**
   - `ProcessingStatus` enum replaces magic strings
   - Values: SUCCESS, FAILURE, SKIPPED, BATCH_SUBMITTED, BATCH_PROCESSING, PENDING
   - Used in `ActorProcessingLog` for consistency

3. **Manifest Ingestion Service (`services.py`)**
   - `ExtensionService.create_extension_from_manifest()`
   - Handles creation and upgrades
   - Auto-registers actors, event types, prompt templates
   - Detects version changes for reprocessing triggers

4. **Extension API Endpoints (`api/extensions.py`)**
   - `POST /internal/extensions/from-manifest` - Install/upgrade from manifest
   - Returns installation summary with upgrade detection

5. **Reprocessing System (`services.py` + `api/processing.py`)**
   - `ProcessingService.find_raw_logs_for_reprocessing()` - Finds old data
   - `POST /internal/processing/reprocess-actor/{actor_slug}` - Triggers batch reprocessing
   - Uses background tasks for async execution
   - Automatically supersedes old events

6. **Non-Destructive Event Superseding**
   - `EventService.supersede_prior_events_for_raw_log()` - Single raw_log
   - `EventService.supersede_event_set()` - Batch operations
   - TestProcessor updated to supersede on reprocessing

## manifest.json Structure

```json
{
  "slug": "my-extension",
  "name": "My Extension",
  "version": "1.0.0",
  "description": "Optional description",
  "author": "Your Name",
  "server_side": {
    "actors": [
      {
        "slug": "my-processor",
        "type": "PROCESSOR",
        "version": "1.0.0",
        "description": "What it does"
      }
    ],
    "event_types": [
      {
        "slug": "my-event",
        "description": "Event description"
      }
    ],
    "prompt_templates": [
      {
        "slug": "my-prompt",
        "description": "Prompt description",
        "template_text": "Your prompt: {{data}}",
        "version": 1
      }
    ]
  },
  "client_side": {
    "platforms": {
      "macos": {
        "collectors": [...],
        "ui_components": [...]
      }
    }
  }
}
```

## Workflows

### Installing a New Extension

```bash
# 1. Prepare manifest.json
# 2. POST to API
curl -X POST http://localhost:8000/internal/extensions/from-manifest \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"manifest": {...}, "update_if_exists": false}'

# 3. Extension, actors, and event types are registered
# 4. Actor code must be deployed separately (in actors/*.py)
```

### Upgrading an Extension

```bash
# 1. Update version in manifest.json
# 2. POST with update_if_exists=true
curl -X POST http://localhost:8000/internal/extensions/from-manifest \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"manifest": {...}, "update_if_exists": true}'

# 3. If actor versions changed, trigger reprocessing:
curl -X POST http://localhost:8000/internal/processing/reprocess-actor/my-processor \
  -H "Authorization: Bearer $TOKEN"

# 4. Old events are superseded, new events created
# 5. Timeline automatically shows latest events
```

### Processing Flow with Versioning

1. **Initial Processing**
   - Raw log ingested → `test-processor` v1.0.0 runs
   - Event created, `ActorProcessingLog` records version "1.0.0"
   - Status: `ProcessingStatus.SUCCESS`

2. **Version Upgrade**
   - Extension upgraded to v1.1.0 via manifest
   - Actor version updated in DB

3. **Reprocessing**
   - Call `POST /internal/processing/reprocess-actor/test-processor`
   - Service finds raw logs processed by v1.0.0
   - Background tasks re-run processor v1.1.0
   - New events created, old events superseded via `superseded_by_event_id`
   - New processing log entries created with version "1.1.0"

4. **Timeline Query**
   - Always filters `WHERE superseded_by_event_id IS NULL`
   - Only shows latest events automatically

## Testing

Run the included test script:

```bash
cd server
./scripts/test_manifest_system.sh
```

This demonstrates:
- Manifest validation and installation
- Actor and event type registration
- Data ingestion and processing
- Version upgrade simulation
- Reprocessing trigger
- Timeline queries showing superseded events

## Code Changes Summary

### New Files
- `constants.py` - ProcessingStatus enum
- `manifest.py` - Pydantic manifest models
- `example_manifest.json` - Example extension
- `scripts/test_manifest_system.sh` - Integration test

### Modified Files
- `services.py`
  - Added `ExtensionService.create_extension_from_manifest()`
  - Added `ProcessingService.find_raw_logs_for_reprocessing()`
  - Added `EventService.supersede_prior_events_for_raw_log()`
  - Added `EventService.supersede_event_set()`
  
- `api/extensions.py`
  - Added `POST /internal/extensions/from-manifest`
  
- `api/processing.py`
  - Added `POST /internal/processing/reprocess-actor/{actor_slug}`
  
- `actors/processors.py`
  - Updated to use `ProcessingStatus` enum
  - Integrated superseding on reprocessing

## Architecture Alignment

✅ **Extension-First Design**: Manifest-driven registration  
✅ **Immutable Raw Layer**: Never delete raw_logs  
✅ **Versioning & Reprocessing**: Actor versions tracked, old data reprocessable  
✅ **Non-Destructive Superseding**: Events marked superseded, not deleted  
✅ **Stateless Actors**: No changes needed, actors remain stateless  
✅ **Canonical Timeline**: Queries filter superseded events automatically  
✅ **State Management**: Processing log tracks all versions  

## Next Steps

1. **Deploy Real Extensions**
   - Create manifest.json for actual extensions
   - Implement actor logic in `actors/*.py`
   - Register via `/internal/extensions/from-manifest`

2. **Add Managed Schemas** (Optional)
   - Extend manifest to support `managed_schemas`
   - Auto-create `_details` tables from manifest

3. **Client-Side Integration** (Future)
   - Client apps fetch manifests
   - Deploy collectors and UI components per platform
   - Enforce sandbox permissions

4. **Async Task Queue** (Production)
   - Replace background tasks with Celery/RQ
   - Scale reprocessing across workers

## API Reference

### POST /internal/extensions/from-manifest

**Request:**
```json
{
  "manifest": { /* ExtensionManifest */ },
  "update_if_exists": false
}
```

**Response:**
```json
{
  "message": "Extension 'my-ext' version 1.0.0 installed successfully",
  "extension_slug": "my-ext",
  "version": "1.0.0",
  "is_upgrade": false,
  "actors_registered": 2,
  "event_types_registered": 1
}
```

### POST /internal/processing/reprocess-actor/{actor_slug}

**Response:**
```json
{
  "message": "Queued 42 raw_logs for reprocessing with actor version 1.1.0",
  "actor_slug": "my-processor",
  "current_version": "1.1.0",
  "raw_logs_queued": 42
}
```

## Troubleshooting

**Q: Extension install fails with "already exists"**  
A: Set `update_if_exists: true` in the request body

**Q: Reprocessing endpoint returns 0 queued**  
A: All raw_logs already processed by current version, or no processing logs exist

**Q: Events aren't being superseded**  
A: Check that `EventService.supersede_prior_events_for_raw_log()` is called in actor's `run()` method after flush

**Q: Timeline shows duplicate events**  
A: Verify queries filter `WHERE superseded_by_event_id IS NULL`

---

**Status**: ✅ Extension manifest system fully implemented per architecture v3.3
