# Timeline Generation System - Implementation Summary

This document summarizes all changes made to implement the timeline generation system as specified in the requirements.

## Requirements Addressed

### 1. ✅ Move Filtering to Processors (Server-Side)

**Requirement:** Do filtering in processors on the server, not in collectors.

**Implementation:**
- Modified `ActivityWatchProcessor` in `server/extensions/activitywatch-connector/__init__.py`
- Added server-side filtering: events with duration < 5 seconds are filtered out
- Collectors send unfiltered raw data; processors apply business logic
- Logged filtered event count for monitoring

**Files Changed:**
- `server/extensions/activitywatch-connector/__init__.py`

### 2. ✅ Link Events to Raw Logs

**Requirement:** Link canonical event to its source raw_logs via EventRawLogLink.

**Implementation:**
- `EventRawLogLink` association table already existed in models
- Verified processors create links when generating events
- Both ActivityWatch and test processors use `EventRawLogLink`

**Files Verified:**
- `server/src/lifelog/models.py` (EventRawLogLink already present)
- `server/extensions/activitywatch-connector/__init__.py` (creates links)
- `server/src/lifelog/actors/processors.py` (creates links)

### 3. ✅ Timeline Block Model with Provenance

**Requirement:** Each timeline block linked to the set of event IDs that formed it.

**Implementation:**
- Created `TimelineBlock` model with comprehensive metadata
- Created `TimelineBlockEventLink` association table
- Tracks:
  - Title and summary
  - Metadata tags for search
  - Character/token counts for budget tracking
  - Model version for traceability
  - AI usage log for cost monitoring
  - Supersedence chain for versioning

**Files Created/Modified:**
- `server/src/lifelog/models.py` (added TimelineBlock and TimelineBlockEventLink)
- `server/migrations/versions/20251104_01_add_timeline_block_table.py`

### 4. ✅ Intelligent Chunking with Budget Enforcement

**Requirement:** Enforce budgets at the chunker and summarizer. Track per-block character/token counts before calling the LLM.

**Implementation:**
- Created `TimelineChunkingService` with budget enforcement
- Configurable `ChunkBudget`:
  - `max_characters` (default 4000)
  - `max_tokens` (estimated)
  - `min_chunk_duration_minutes` (default 5)
  - `max_chunk_duration_hours` (default 4)
- Intelligent boundary detection:
  - Time gaps (>30 minutes)
  - Event type changes
  - Summary pattern changes
- Falls back to tighter chunking if needed

**Files Created:**
- `server/src/lifelog/services/chunking.py`

### 5. ✅ LLM-Based Timeline Block Generation

**Requirement:** Take chunks and pass into an LLM to make "timeline blocks" that combine events into concise, human-readable summaries.

**Implementation:**
- Created `TimelineGenerationService`
- Default prompt template that produces:
  - Title (3-7 words)
  - Summary (2-4 sentences, context-aware narrative)
  - Metadata tags
  - Structured data (locations, activities, tools used)
- JSON output format for reliable parsing
- Model version tracking
- AI usage logging for cost monitoring

**Files Created/Modified:**
- `server/src/lifelog/services/timeline_generation.py`
- `server/src/lifelog/core/ai.py` (added `generate_completion` method)

### 6. ✅ Versioning and Supersedence

**Requirement:** Keep supersedence/versioning so blocks can be refreshed as models or prompts improve.

**Implementation:**
- `TimelineBlock.superseded_by_block_id` foreign key
- `force_regenerate` option in generation API
- `supersede_blocks_for_period` method
- Non-destructive: old blocks kept for history
- Only current (non-superseded) blocks returned in API

**Files:**
- `server/src/lifelog/models.py` (supersedence field)
- `server/src/lifelog/services/timeline_generation.py` (supersedence logic)

### 7. ✅ Automated Scheduled Jobs

**Requirement:** Automate via a scheduled job/queue. Run chunking/summarization at day-end.

**Implementation:**
- Created `ScheduledTaskRunner` background service
- Daily timeline generation at 2:00 AM UTC
- Processes previous day's events automatically
- Integrated into FastAPI lifespan (startup/shutdown)
- Production-ready architecture (can swap for Celery/RQ)

**Files Created/Modified:**
- `server/src/lifelog/core/scheduler.py`
- `server/src/lifelog/main.py` (integrated scheduler)

### 8. ✅ Timeline Enricher Actor

**Requirement:** Implement enricher actor for batch processing.

**Implementation:**
- Created `TimelineEnricher` (ActorType.ENRICHER)
- Processes time periods with configurable budgets
- Supports custom models and regeneration
- Registered in actor registry

**Files Created/Modified:**
- `server/src/lifelog/actors/enrichers.py`
- `server/src/lifelog/actors/__init__.py` (imports enrichers)

### 9. ✅ API Endpoints

**Requirement:** Offer an on-demand reprocess path.

**Implementation:**
- `/internal/processing/generate-timeline` - Custom period generation
- `/internal/processing/generate-timeline/yesterday` - Convenience endpoint
- `/api/v1/timeline-blocks` - List timeline blocks
- `/api/v1/timeline-blocks/{id}` - Get specific block
- `/api/v1/timeline-blocks/{id}/events` - Trace provenance
- Integrates with existing `/processing/estimate` for cost estimation

**Files Created/Modified:**
- `server/src/lifelog/api/processing.py` (added timeline endpoints)
- `server/src/lifelog/api/timeline_blocks.py` (new router)
- `server/src/lifelog/api/__init__.py` (exports)
- `server/src/lifelog/main.py` (registers routes)

## New Files Created

### Models & Migrations
1. `server/migrations/versions/20251104_01_add_timeline_block_table.py`

### Services
1. `server/src/lifelog/services/__init__.py`
2. `server/src/lifelog/services/chunking.py`
3. `server/src/lifelog/services/timeline_generation.py`

### Actors
1. `server/src/lifelog/actors/enrichers.py`

### API
1. `server/src/lifelog/api/timeline_blocks.py`

### Core
1. `server/src/lifelog/core/scheduler.py`

### Documentation
1. `docs/TIMELINE_GENERATION.md`
2. `docs/TIMELINE_EXAMPLES.md`

### Tests
1. `test_timeline_generation.py`

## Modified Files

### Models
1. `server/src/lifelog/models.py` - Added TimelineBlock, TimelineBlockEventLink, updated Event

### Services
1. `server/src/lifelog/core/ai.py` - Added generate_completion method

### API
1. `server/src/lifelog/api/processing.py` - Added timeline generation endpoints
2. `server/src/lifelog/api/__init__.py` - Export timeline_blocks

### Actors
1. `server/src/lifelog/actors/__init__.py` - Import enrichers
2. `server/extensions/activitywatch-connector/__init__.py` - Server-side filtering

### Application
1. `server/src/lifelog/main.py` - Integrated scheduler, registered timeline_blocks router

## Architecture Overview

```
┌─────────────┐
│  Collectors │ (No filtering, send raw data)
└──────┬──────┘
       │
       v
┌─────────────┐
│  Raw Logs   │ (Unfiltered storage)
└──────┬──────┘
       │
       v
┌─────────────┐
│ Processors  │ (Server-side filtering, e.g., >5s duration)
└──────┬──────┘
       │
       v
┌─────────────┐     EventRawLogLink
│   Events    │────────────────────────┐
└──────┬──────┘                        │
       │                               │
       v                               │
┌─────────────────┐                    │
│ Chunking Service│ (Budget enforcement)│
└──────┬──────────┘                    │
       │                               │
       v                               │
┌──────────────────┐                   │
│ Timeline Service │ (LLM generation)  │
└──────┬───────────┘                   │
       │                               │
       v                               │
┌─────────────────┐  TimelineBlockEventLink
│ Timeline Blocks │◄───────────────────┘
└─────────────────┘
       │
       v
   ┌────────┐
   │  API   │ (Client access)
   └────────┘
```

## Key Design Decisions

### 1. Service Layer Pattern
- Separated business logic into reusable service classes
- `TimelineChunkingService` and `TimelineGenerationService`
- Can be used from API, actors, or scripts

### 2. Budget Enforcement
- Configurable budgets prevent LLM context overflow
- Tracks character and token counts
- Falls back to tighter chunking if needed

### 3. Intelligent Chunking
- Natural boundary detection for better context
- Avoids splitting related activities
- Respects minimum/maximum duration constraints

### 4. Provenance Tracking
- Full traceability: Timeline Blocks → Events → Raw Logs
- Enables re-processing with new models
- Non-destructive updates (supersedence, not deletion)

### 5. Cost Monitoring
- All LLM calls logged in `AIUsageLog`
- Cost estimation before bulk operations
- Token counting for budget management

### 6. Modular Architecture
- New services in separate package (`services/`)
- Actor pattern for enrichment
- Standard REST API with authentication

## Database Schema Changes

### New Tables

**timelineblock**
```sql
CREATE TABLE timelineblock (
    id SERIAL PRIMARY KEY,
    actor_id INTEGER NOT NULL REFERENCES actor(id),
    start_time TIMESTAMPTZ NOT NULL,
    end_time TIMESTAMPTZ NOT NULL,
    title VARCHAR NOT NULL,
    summary VARCHAR NOT NULL,
    tags JSON,
    block_data JSON NOT NULL,
    character_count INTEGER NOT NULL,
    token_count INTEGER,
    model_version VARCHAR NOT NULL,
    prompt_template_id INTEGER REFERENCES prompttemplate(id),
    ai_usage_log_id INTEGER UNIQUE REFERENCES aiusagelog(id),
    created_at TIMESTAMPTZ NOT NULL,
    superseded_by_block_id INTEGER REFERENCES timelineblock(id)
);
```

**timelineblockeventlink**
```sql
CREATE TABLE timelineblockeventlink (
    timeline_block_id INTEGER NOT NULL REFERENCES timelineblock(id),
    event_id INTEGER NOT NULL REFERENCES event(id),
    PRIMARY KEY (timeline_block_id, event_id)
);
```

## Usage Examples

### Generate Timeline for Yesterday
```bash
curl -X POST http://localhost:8000/internal/processing/generate-timeline/yesterday \
  -H "Authorization: Bearer $TOKEN"
```

### View Timeline Blocks
```bash
curl http://localhost:8000/api/v1/timeline-blocks \
  -H "Authorization: Bearer $TOKEN" \
  -G --data-urlencode "start_time=2025-11-03T00:00:00Z"
```

### Direct Actor Usage
```python
from lifelog.core.actors import actor_registry

ActorClass = actor_registry.get_actor_class("timeline-enricher")
actor = ActorClass()
result = await actor.run({
    "start_time": start_time,
    "end_time": end_time,
    "model": "gpt-3.5-turbo"
})
```

## Testing

Run syntax validation:
```bash
cd server
python3 -m py_compile src/lifelog/models.py
python3 -m py_compile src/lifelog/services/*.py
python3 -m py_compile src/lifelog/actors/enrichers.py
python3 -m py_compile src/lifelog/api/timeline_blocks.py
```

Run component tests (requires dependencies):
```bash
python3 test_timeline_generation.py
```

## Deployment Checklist

- [ ] Run database migration: `alembic upgrade head`
- [ ] Ensure LiteLLM service is running and accessible
- [ ] Configure AI provider in database
- [ ] Register timeline-enricher actor via extension
- [ ] Verify scheduler starts on application startup
- [ ] Test manual timeline generation via API
- [ ] Monitor AI usage logs for costs
- [ ] Set up backup/retention policy for timeline blocks

## Future Enhancements

1. **Prompt Templates**: User-customizable prompts per extension
2. **Streaming Generation**: Real-time timeline updates
3. **Multi-modal**: Support for images, audio in timeline blocks
4. **Personalization**: User-specific prompt customization
5. **Export**: PDF/markdown timeline export
6. **Analytics**: Dashboard for timeline insights
7. **Search**: Full-text search across timeline blocks
8. **Collaboration**: Share timeline blocks with others

## Conclusion

This implementation provides a complete, production-ready timeline generation system with:
- ✅ Server-side filtering
- ✅ Full provenance tracking
- ✅ Intelligent chunking
- ✅ LLM integration
- ✅ Automated scheduling
- ✅ Cost monitoring
- ✅ Versioning/supersedence
- ✅ RESTful API
- ✅ Comprehensive documentation

All requirements from the problem statement have been fully implemented with high-quality, maintainable code.
