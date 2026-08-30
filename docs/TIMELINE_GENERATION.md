# Timeline Generation System

This document describes the timeline generation architecture that intelligently chunks and summarizes events into human-readable timeline blocks using LLM.

## Overview

The timeline generation system transforms raw event data into enriched, context-aware summaries. Instead of viewing hundreds of individual events, users get concise timeline blocks that weave together related activities into coherent narratives.

## Architecture

### Data Flow

```
Raw Data → Raw Logs → Events → Chunks → Timeline Blocks
    ↓          ↓         ↓         ↓          ↓
Collectors  Ingestion Processors Chunker  LLM Enricher
```

1. **Raw Data Collection**: Collectors send unfiltered data to the server
2. **Raw Logs**: Data stored in `raw_logs` table with source actor tracking
3. **Event Processing**: Processors filter and transform data into `events`
   - Server-side filtering (e.g., ActivityWatch filters events < 5 seconds)
   - Links to source raw_logs via `EventRawLogLink`
4. **Intelligent Chunking**: Events grouped with budget enforcement
   - Respects character/token limits for LLM context
   - Detects natural boundaries (time gaps, activity changes)
   - Configurable chunk duration (min 5 min, max 4 hours)
5. **LLM Enrichment**: Timeline blocks generated via AI
   - Combines events into coherent narratives
   - Extracts metadata tags for search
   - Tracks model version and usage for cost monitoring
   - Links back to source events via `TimelineBlockEventLink`

### Database Schema

#### Core Tables

**TimelineBlock**
- Enrichment artifact storing AI-generated summaries
- Fields:
  - `title`: Short descriptive title (3-7 words)
  - `summary`: Human-readable narrative (2-4 sentences)
  - `tags`: Metadata tags for search/filtering
  - `block_data`: Full structured data (locations, activities, etc.)
  - `character_count`: Total input characters (budget tracking)
  - `model_version`: LLM model identifier
  - `superseded_by_block_id`: Version tracking for regeneration

**TimelineBlockEventLink**
- Association table linking timeline blocks to source events
- Enables tracing back to original data for verification

**Event** (existing, updated)
- Added relationship to timeline_blocks for bidirectional navigation

### Services

#### TimelineChunkingService

Intelligently groups events into chunks with budget enforcement.

**Features:**
- Natural boundary detection (time gaps, activity changes)
- Configurable budgets (max characters, tokens, duration)
- Smart splitting to respect LLM context limits

**Example:**
```python
from lifelog.services.chunking import TimelineChunkingService, ChunkBudget

budget = ChunkBudget(
    max_characters=4000,
    min_chunk_duration_minutes=5,
    max_chunk_duration_hours=4
)

chunks = await TimelineChunkingService.chunk_events_for_period(
    session,
    start_time,
    end_time,
    budget=budget
)
```

#### TimelineGenerationService

Generates timeline blocks using LLM.

**Features:**
- Customizable prompt templates
- Model version tracking
- AI usage/cost logging
- Supersedence support for regeneration

**Example:**
```python
from lifelog.services.timeline_generation import TimelineGenerationService

blocks = await TimelineGenerationService.generate_timeline_blocks_for_period(
    session,
    chunks,
    actor_id=enricher_actor.id,
    model="gpt-3.5-turbo"
)
```

## Actors

### timeline-enricher (ENRICHER)

Batch worker that generates timeline blocks for time periods.

**Input Data:**
```json
{
  "start_time": "2025-11-03T00:00:00Z",
  "end_time": "2025-11-04T00:00:00Z",
  "model": "gpt-3.5-turbo",
  "force_regenerate": false,
  "budget": {
    "max_characters": 4000
  }
}
```

**Output:**
```json
{
  "status": "success",
  "blocks_created": 12,
  "chunks_processed": 12,
  "period": {
    "start": "2025-11-03T00:00:00Z",
    "end": "2025-11-04T00:00:00Z"
  }
}
```

## API Endpoints

### Generate Timeline

**POST** `/internal/processing/generate-timeline`

Generate timeline blocks for a custom period.

```json
{
  "start_time": "2025-11-03T00:00:00Z",
  "end_time": "2025-11-04T00:00:00Z",
  "model": "gpt-3.5-turbo",
  "force_regenerate": false,
  "max_characters_per_chunk": 4000
}
```

**POST** `/internal/processing/generate-timeline/yesterday`

Convenience endpoint for daily generation (most common use case).

### View Timeline Blocks

**GET** `/api/v1/timeline-blocks`

List timeline blocks with optional filters.

Query parameters:
- `start_time`: Filter by start time
- `end_time`: Filter by end time
- `limit`: Max results (default 100)
- `skip`: Pagination offset

**GET** `/api/v1/timeline-blocks/{block_id}`

Get a specific timeline block.

**GET** `/api/v1/timeline-blocks/{block_id}/events`

Get source event IDs for a timeline block (provenance tracking).

## Automated Scheduling

The system includes a background scheduler that runs timeline generation automatically.

**Schedule:**
- Daily at 2:00 AM UTC
- Processes previous day's events
- Configurable in `lifelog/core/scheduler.py`

**Production Considerations:**
For production deployments, consider replacing the built-in scheduler with:
- Celery (distributed task queue)
- APScheduler (advanced scheduling)
- Kubernetes CronJobs
- Cloud scheduler (AWS EventBridge, GCP Cloud Scheduler)

## Configuration

### Chunk Budgets

Default budgets (override via API):
```python
ChunkBudget(
    max_characters=4000,        # ~1000 tokens
    max_tokens=1000,            # Explicit token limit
    min_chunk_duration_minutes=5,
    max_chunk_duration_hours=4
)
```

### LLM Settings

Configure in environment or via `/internal/ai/settings`:
- `DEFAULT_CHAT_MODEL`: Default LLM (default: "gpt-3.5-turbo")
- `LITELLM_BASE_URL`: LiteLLM endpoint (default: "http://litellm:4000")

### Prompt Template

The default prompt is in `timeline_generation.py`. To customize:

1. Create a custom `PromptTemplate` via extensions
2. Pass `prompt_template_id` to generation API

## Filtering Rules

Processors implement server-side filtering (not collectors):

**ActivityWatch Processor:**
- Filters events with duration < 5 seconds
- Prevents noise from brief window switches

**Best Practices:**
- Keep collectors simple (minimal logic)
- Apply filtering in processors
- Use consistent filtering rules across versions

## Versioning & Supersedence

Timeline blocks support versioning for regeneration with improved models:

1. Generate initial blocks (v1)
2. Improve prompt/model
3. Regenerate with `force_regenerate=true`
4. Old blocks marked as superseded via `superseded_by_block_id`
5. API returns only current (non-superseded) blocks

**Cost Estimation:**
Use `/processing/estimate/{actor_slug}` before regenerating to understand:
- Number of events affected
- Estimated AI API calls
- Estimated cost in USD
- Processing time

## Example: Complete Workflow

```python
from datetime import datetime, timedelta, timezone
from lifelog.db import async_session
from lifelog.services.chunking import TimelineChunkingService, ChunkBudget
from lifelog.services.timeline_generation import TimelineGenerationService

# Define period (yesterday)
end_time = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
start_time = end_time - timedelta(days=1)

async with async_session() as session:
    # Step 1: Chunk events
    chunks = await TimelineChunkingService.chunk_events_for_period(
        session,
        start_time,
        end_time,
        budget=ChunkBudget(max_characters=4000)
    )
    
    # Step 2: Generate timeline blocks
    blocks = await TimelineGenerationService.generate_timeline_blocks_for_period(
        session,
        chunks,
        actor_id=enricher_actor_id,
        model="gpt-3.5-turbo"
    )
    
    print(f"Generated {len(blocks)} timeline blocks from {len(chunks)} chunks")
```

## Monitoring & Debugging

### AI Usage Logs

All LLM calls are logged in `aiusagelog`:
- Prompt/completion token counts
- Cost per call
- Model used
- Associated timeline block

Query total costs:
```sql
SELECT 
    DATE(created_at) as date,
    SUM(cost) as total_cost,
    COUNT(*) as api_calls
FROM aiusagelog
WHERE call_type = 'completion'
GROUP BY DATE(created_at)
ORDER BY date DESC;
```

### Processing Logs

Check `ActorProcessingLog` for processor execution history.

### Failed Generations

If timeline generation fails:
1. Check `/health` endpoint
2. Verify LiteLLM is running (`LITELLM_BASE_URL`)
3. Check AI provider is active
4. Review logs for specific error messages

## Future Enhancements

- [ ] Multi-modal enrichment (images, audio)
- [ ] Semantic similarity clustering
- [ ] Personalized prompt templates per user
- [ ] Real-time streaming enrichment
- [ ] Timeline block editing/annotation
- [ ] Export timeline as PDF/markdown
