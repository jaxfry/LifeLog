# Timeline Generation Integration Example

This document provides practical examples of using the timeline generation system.

## Prerequisites

1. LifeLog server running with database
2. LiteLLM service running (for LLM calls)
3. At least one day of event data in the system
4. Timeline enricher actor registered

## Example 1: Manual Timeline Generation

Generate timeline blocks for a specific date range using the API.

### Via cURL

```bash
# Authenticate first
TOKEN=$(curl -X POST http://localhost:8000/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username": "admin", "password": "admin123"}' | jq -r .access_token)

# Generate timeline for yesterday
curl -X POST http://localhost:8000/internal/processing/generate-timeline/yesterday \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json"

# Response:
# {
#   "status": "queued",
#   "message": "Timeline generation queued for 2025-11-03 to 2025-11-04",
#   "blocks_created": 0,
#   "chunks_processed": 0,
#   "period": {
#     "start": "2025-11-03T00:00:00+00:00",
#     "end": "2025-11-04T00:00:00+00:00"
#   }
# }
```

### Via Python

```python
import httpx
from datetime import datetime, timedelta, timezone

BASE_URL = "http://localhost:8000"

# Login
response = httpx.post(
    f"{BASE_URL}/api/v1/auth/login",
    json={"username": "admin", "password": "admin123"}
)
token = response.json()["access_token"]
headers = {"Authorization": f"Bearer {token}"}

# Generate timeline for yesterday
end_time = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
start_time = end_time - timedelta(days=1)

response = httpx.post(
    f"{BASE_URL}/internal/processing/generate-timeline",
    headers=headers,
    json={
        "start_time": start_time.isoformat(),
        "end_time": end_time.isoformat(),
        "model": "gpt-3.5-turbo",
        "force_regenerate": False,
        "max_characters_per_chunk": 4000
    }
)

print(response.json())
```

## Example 2: View Generated Timeline Blocks

Retrieve and display timeline blocks.

### Via cURL

```bash
# Get timeline blocks for a date range
curl http://localhost:8000/api/v1/timeline-blocks \
  -H "Authorization: Bearer $TOKEN" \
  -G \
  --data-urlencode "start_time=2025-11-03T00:00:00Z" \
  --data-urlencode "end_time=2025-11-04T00:00:00Z" \
  --data-urlencode "limit=20"

# Get a specific timeline block
curl http://localhost:8000/api/v1/timeline-blocks/123 \
  -H "Authorization: Bearer $TOKEN"

# Get source events for a timeline block
curl http://localhost:8000/api/v1/timeline-blocks/123/events \
  -H "Authorization: Bearer $TOKEN"
```

### Via Python

```python
# Get timeline blocks
response = httpx.get(
    f"{BASE_URL}/api/v1/timeline-blocks",
    headers=headers,
    params={
        "start_time": start_time.isoformat(),
        "end_time": end_time.isoformat(),
        "limit": 20
    }
)

blocks = response.json()
for block in blocks:
    print(f"\n{block['title']}")
    print(f"  Time: {block['start_time']} - {block['end_time']}")
    print(f"  Summary: {block['summary']}")
    print(f"  Tags: {', '.join(block['tags'] or [])}")
    print(f"  Model: {block['model_version']}")
    print(f"  Source Events: {block['source_event_count']}")
```

## Example 3: Direct Actor Usage

Use the enricher actor directly from Python code.

```python
from datetime import datetime, timedelta, timezone
from lifelog.db import async_session
from lifelog.core.actors import actor_registry

async def generate_timeline():
    # Get the enricher actor class
    ActorClass = actor_registry.get_actor_class("timeline-enricher")
    if not ActorClass:
        raise RuntimeError("timeline-enricher not registered")
    
    # Define period
    end_time = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    start_time = end_time - timedelta(days=1)
    
    # Prepare actor data
    actor_data = {
        "start_time": start_time,
        "end_time": end_time,
        "model": "gpt-3.5-turbo",
        "force_regenerate": False,
        "budget": {
            "max_characters": 4000
        }
    }
    
    # Run the actor
    actor_instance = ActorClass()
    result = await actor_instance.run(actor_data)
    
    print(f"Timeline generation result: {result}")
    return result

# Run it
import asyncio
asyncio.run(generate_timeline())
```

## Example 4: Custom Chunking Configuration

Use the chunking service directly with custom budgets.

```python
from datetime import datetime, timedelta, timezone
from lifelog.db import async_session
from lifelog.services.chunking import TimelineChunkingService, ChunkBudget

async def custom_chunking():
    # Define custom budget
    budget = ChunkBudget(
        max_characters=2000,  # Smaller chunks for faster processing
        min_chunk_duration_minutes=10,  # Longer minimum duration
        max_chunk_duration_hours=2  # Shorter maximum duration
    )
    
    # Define period
    end_time = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    start_time = end_time - timedelta(days=1)
    
    async with async_session() as session:
        # Chunk events
        chunks = await TimelineChunkingService.chunk_events_for_period(
            session,
            start_time,
            end_time,
            budget=budget
        )
        
        print(f"Created {len(chunks)} chunks:")
        for i, chunk in enumerate(chunks):
            print(f"\nChunk {i+1}:")
            print(f"  Events: {len(chunk.events)}")
            print(f"  Duration: {chunk.duration()}")
            print(f"  Characters: {chunk.character_count}")
            print(f"  Preview: {chunk.to_text()[:100]}...")

asyncio.run(custom_chunking())
```

## Example 5: Regenerate Timeline with New Model

Regenerate timeline blocks with an improved model or prompt.

```python
import httpx

# First, estimate the cost
estimate_response = httpx.post(
    f"{BASE_URL}/internal/processing/estimate/timeline-enricher",
    headers=headers,
    json={
        "date_range": {
            "start": start_time.isoformat(),
            "end": end_time.isoformat()
        }
    }
)

estimate = estimate_response.json()
print(f"Estimated cost: ${estimate['estimated_cost_usd']}")
print(f"Events affected: {estimate['raw_logs_affected']}")

# If acceptable, regenerate
if estimate['estimated_cost_usd'] < 1.00:  # Budget check
    regenerate_response = httpx.post(
        f"{BASE_URL}/internal/processing/generate-timeline",
        headers=headers,
        json={
            "start_time": start_time.isoformat(),
            "end_time": end_time.isoformat(),
            "model": "gpt-4",  # Upgraded model
            "force_regenerate": True,  # Supersede old blocks
            "max_characters_per_chunk": 6000  # Larger chunks for GPT-4
        }
    )
    print(regenerate_response.json())
```

## Example 6: Query AI Usage Logs

Track costs and usage for timeline generation.

```python
from lifelog.db import async_session
from sqlmodel import select, func
from lifelog.models import AIUsageLog, Actor

async def get_timeline_costs():
    async with async_session() as session:
        # Get timeline-enricher actor
        actor_stmt = select(Actor).where(Actor.slug == "timeline-enricher")
        actor = (await session.exec(actor_stmt)).first()
        
        if not actor:
            print("Actor not found")
            return
        
        # Query total costs
        cost_stmt = (
            select(
                func.date(AIUsageLog.created_at).label('date'),
                func.sum(AIUsageLog.cost).label('total_cost'),
                func.count(AIUsageLog.id).label('api_calls'),
                func.sum(AIUsageLog.prompt_tokens).label('prompt_tokens'),
                func.sum(AIUsageLog.completion_tokens).label('completion_tokens')
            )
            .where(AIUsageLog.actor_id == actor.id)
            .where(AIUsageLog.call_type == 'completion')
            .group_by(func.date(AIUsageLog.created_at))
            .order_by(func.date(AIUsageLog.created_at).desc())
        )
        
        result = await session.exec(cost_stmt)
        rows = result.all()
        
        print("\nTimeline Generation Costs:")
        print("-" * 80)
        print(f"{'Date':<12} {'API Calls':<12} {'Tokens':<15} {'Cost':<10}")
        print("-" * 80)
        
        total_cost = 0
        for row in rows:
            date, cost, calls, prompt_tok, completion_tok = row
            total_tokens = (prompt_tok or 0) + (completion_tok or 0)
            total_cost += cost or 0
            print(f"{date!s:<12} {calls:<12} {total_tokens:<15} ${cost:.4f}")
        
        print("-" * 80)
        print(f"Total Cost: ${total_cost:.2f}")

asyncio.run(get_timeline_costs())
```

## Example 7: Search Timeline Blocks by Tag

Search for timeline blocks with specific tags.

```python
from lifelog.db import async_session
from sqlmodel import select
from lifelog.models import TimelineBlock

async def search_by_tag(tag: str):
    async with async_session() as session:
        # Search for blocks with the tag
        # Note: JSON array search syntax varies by database
        # PostgreSQL example:
        stmt = (
            select(TimelineBlock)
            .where(TimelineBlock.superseded_by_block_id.is_(None))
            .where(TimelineBlock.tags.contains([tag]))  # PostgreSQL JSONB contains
            .order_by(TimelineBlock.start_time.desc())
            .limit(10)
        )
        
        result = await session.exec(stmt)
        blocks = result.all()
        
        print(f"\nTimeline blocks tagged '{tag}':")
        for block in blocks:
            print(f"\n{block.title}")
            print(f"  {block.start_time.date()} at {block.start_time.time()}")
            print(f"  {block.summary[:100]}...")

asyncio.run(search_by_tag("work"))
```

## Example 8: Automated Daily Schedule

The system automatically generates timelines at 2 AM UTC daily.

To change the schedule, edit `lifelog/core/scheduler.py`:

```python
async def _check_and_run_tasks(self):
    """Check if any scheduled tasks should run."""
    now = datetime.now(timezone.utc)
    
    # Change schedule time here
    if await self._should_run_daily_task(
        "timeline_generation", 
        now, 
        time(hour=3, minute=30)  # Changed to 3:30 AM UTC
    ):
        logger.info("Running scheduled daily timeline generation")
        await self._run_daily_timeline_generation()
```

## Troubleshooting

### Timeline Generation Fails

**Check LiteLLM:**
```bash
curl http://litellm:4000/health
```

**Check AI Provider:**
```python
from lifelog.db import async_session
from sqlmodel import select
from lifelog.models import AIProvider

async with async_session() as session:
    stmt = select(AIProvider).where(AIProvider.is_active == True)
    providers = (await session.exec(stmt)).all()
    for p in providers:
        print(f"{p.provider_slug}: {p.model_type} ({p.provider_type})")
```

### No Events to Process

**Verify events exist:**
```python
from lifelog.db import async_session
from sqlmodel import select, func
from lifelog.models import Event

async with async_session() as session:
    count_stmt = select(func.count(Event.id)).where(
        Event.superseded_by_event_id.is_(None)
    )
    count = (await session.exec(count_stmt)).one()
    print(f"Total non-superseded events: {count}")
```

### Costs Too High

**Reduce chunk size:**
```json
{
  "max_characters_per_chunk": 2000
}
```

**Use cheaper model:**
```json
{
  "model": "gpt-3.5-turbo"
}
```

**Limit time period:**
Only generate for recent periods, not entire history.
