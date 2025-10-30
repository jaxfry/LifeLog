# Dynamic Extension Loading & Managed Schemas

## Overview

LifeLog now supports **dynamic extension loading** and **managed schemas**, allowing extensions to provide their own Python code and database tables without modifying the core server codebase.

## Architecture

### Components

1. **ExtensionLoader** (`core/extension_loader.py`)
   - Discovers extension packages in `extensions/` directory
   - Validates manifest.json files
   - Dynamically imports Python modules
   - Verifies actor registration

2. **SchemaManager** (`core/schema_manager.py`)
   - Parses managed_schemas from manifests
   - Generates safe SQL DDL statements
   - Creates/drops extension tables with proper prefixing
   - Validates column types and names

3. **Extension Packages** (`extensions/*/`)
   - Self-contained Python packages
   - Each has manifest.json + __init__.py
   - Actors registered via @actor_registry.register decorators

### Data Flow

```
Server Startup
    │
    ├─> Load built-in actors (actors/*.py)
    │
    └─> ExtensionLoader.load_all_extensions()
           │
           ├─> Discover extensions/*/manifest.json
           │
           ├─> For each extension:
           │      ├─> Validate manifest schema
           │      ├─> Import __init__.py (registers actors)
           │      └─> Verify actor slugs match manifest
           │
           └─> Log loaded extensions

Extension Installation via API
    │
    POST /internal/extensions/from-manifest
    │
    └─> ExtensionService.create_extension_from_manifest()
           │
           ├─> Create/update Extension record in DB
           ├─> Create/update Actor records
           ├─> Create EventType records
           ├─> Create PromptTemplate records
           │
           └─> SchemaManager.apply_managed_schemas()
                  │
                  └─> For each table in manifest:
                         ├─> Generate CREATE TABLE DDL
                         ├─> Prefix with extension slug
                         ├─> Execute DDL
                         └─> Log success/failure
```

## Extension Structure

### Minimal Extension

```
extensions/my-extension/
├── __init__.py
└── manifest.json
```

### Full Extension

```
extensions/my-extension/
├── __init__.py          # Entry point, registers actors
├── manifest.json        # Metadata, schemas, event types
├── actors.py           # (optional) Additional actor implementations
├── utils.py            # (optional) Helper functions
└── README.md           # (optional) Documentation
```

## Creating an Extension

### 1. Create Extension Directory

```bash
mkdir server/extensions/my-extension
```

### 2. Write manifest.json

```json
{
  "slug": "my-extension",
  "name": "My Extension",
  "version": "1.0.0",
  "description": "What it does",
  "author": "Your Name",
  "server_side": {
    "actors": [
      {
        "slug": "my-processor",
        "type": "PROCESSOR",
        "version": "1.0.0",
        "description": "Processes my data"
      }
    ],
    "event_types": [
      {
        "slug": "my-event",
        "description": "My event type"
      }
    ],
    "managed_schemas": {
      "schema_version": 1,
      "tables": {
        "details": {
          "columns": [
            {"name": "event_id", "type": "BIGINT", "nullable": false},
            {"name": "custom_field", "type": "TEXT"}
          ]
        }
      }
    }
  }
}
```

### 3. Implement Actors in __init__.py

```python
"""My Extension"""

import logging
from typing import Any
from lifelog.core.actors import ActorBase, ActorConfig, actor_registry
from lifelog import models
from lifelog.db import async_session
from lifelog.constants import ProcessingStatus
from sqlmodel import select

logger = logging.getLogger(__name__)


@actor_registry.register(
    ActorConfig(
        slug="my-processor",
        actor_type=models.ActorType.PROCESSOR,
        version="1.0.0",
    )
)
class MyProcessor(ActorBase):
    async def run(self, data: models.RawLog) -> Any:
        raw_log = data
        
        async with async_session() as session:
            # Reload in session
            raw_log = await session.get(models.RawLog, raw_log.id)
            
            # Get actor
            actor_stmt = select(models.Actor).where(
                models.Actor.slug == "my-processor"
            )
            actor = (await session.exec(actor_stmt)).one_or_none()
            
            # Get event type
            et_stmt = select(models.EventType).where(
                models.EventType.slug == "my-event"
            )
            event_type = (await session.exec(et_stmt)).one_or_none()
            
            # Create event
            new_event = models.Event(
                processor_actor_id=actor.id,
                start_time=raw_log.ingested_at,
                event_type_id=event_type.id,
                summary=raw_log.raw_data.get("summary", "No summary"),
            )
            new_event.raw_logs.append(raw_log)
            session.add(new_event)
            
            await session.flush()
            event_id = new_event.id
            
            # Write to managed table
            from sqlalchemy import text
            await session.execute(
                text("""
                    INSERT INTO my_extension_details 
                    (event_id, custom_field)
                    VALUES (:event_id, :custom_field)
                """),
                {
                    "event_id": event_id,
                    "custom_field": raw_log.raw_data.get("custom"),
                }
            )
            
            # Log success
            session.add(
                models.ActorProcessingLog(
                    actor_id=actor.id,
                    actor_version_at_processing=actor.version,
                    raw_log_id=raw_log.id,
                    event_id=event_id,
                    status=ProcessingStatus.SUCCESS,
                )
            )
            
            await session.commit()


logger.info("My extension loaded")
```

### 4. Restart Server

The extension will be automatically discovered and loaded.

### 5. Register Extension in Database

```bash
curl -X POST "http://localhost:8000/internal/extensions/from-manifest" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d @server/extensions/my-extension/manifest.json
```

This will:
- Create Extension record in DB
- Create Actor records
- Create EventType records
- Create managed schema tables

### 6. Configure Actor Routing

```bash
curl -X POST "http://localhost:8000/internal/actor-routing" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "source_actor_slug": "some-source",
    "processor_actor_slug": "my-processor"
  }'
```

## Managed Schemas

### Table Naming

Tables are automatically prefixed with the extension slug:
- Extension: `my-extension`
- Manifest table: `details`
- **Actual table**: `my_extension_details`

### Automatic Columns

Every managed table gets:
- `id BIGSERIAL PRIMARY KEY` (auto-incrementing ID)
- `created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()`
- `updated_at TIMESTAMPTZ`

### Allowed Types

| Category | Types |
|----------|-------|
| Text | TEXT, VARCHAR, CHAR |
| Numbers | INT, INTEGER, BIGINT, SMALLINT, DECIMAL, NUMERIC, REAL, DOUBLE PRECISION |
| Boolean | BOOLEAN, BOOL |
| Date/Time | DATE, TIME, TIMESTAMP, TIMESTAMPTZ |
| JSON | JSONB, JSON |
| Binary | BYTEA |

### Accessing Managed Tables

Use raw SQL in your actors:

```python
from sqlalchemy import text

# Insert
await session.execute(
    text("INSERT INTO my_extension_details (event_id, field) VALUES (:eid, :val)"),
    {"eid": event_id, "val": "value"}
)

# Query
result = await session.execute(
    text("SELECT * FROM my_extension_details WHERE event_id = :eid"),
    {"eid": event_id}
)
row = result.first()
```

## Security Considerations

### Current Model

- Extensions run in the same Python process as the server
- No process isolation or true sandboxing
- Trust model: Extensions are installed by the system owner
- Extensions have full access to the database and file system

### Validation

- Table/column names validated (alphanumeric + underscores)
- SQL types whitelisted
- Extension slug used as table prefix to avoid collisions
- SQL injection prevented via parameterized queries

### Future Enhancements

- Subprocess isolation for actor execution
- Container-based sandboxing
- Permission system for file system/network access
- Resource limits (CPU, memory, execution time)

## Testing

Run the test script:

```bash
./server/scripts/test_dynamic_extensions.sh
```

This will:
1. Register the example extension
2. Create managed schema tables
3. Ingest test data
4. Trigger processing
5. Verify event creation

## Troubleshooting

### Extension Not Loading

Check server logs for:
```
Failed to load extension at extensions/my-extension: <error>
```

Common issues:
- Invalid manifest.json syntax
- Missing __init__.py
- Import errors in extension code
- Actor slug mismatch between manifest and code

### Table Not Created

Check logs for:
```
Failed to create table 'my_extension_details': <error>
```

Common issues:
- Invalid column type
- Invalid table/column name
- Database connection issues
- Permissions

### Actor Not Found

If ingestion fails with "Actor not found":
1. Check extension was loaded: Look for "Loaded N dynamic extensions" in logs
2. Check actor was registered: Look for "Registered actor 'slug'" in logs
3. Verify manifest slug matches @actor_registry.register slug
4. Restart server if you made changes

## Example Extensions

See `server/extensions/example-extension/` for a complete working example.

## Migration from Built-in Actors

To convert a built-in actor to an extension:

1. Create extension directory
2. Move actor code to extension's __init__.py
3. Create manifest.json
4. Remove actor from server/src/lifelog/actors/
5. Restart server

The extension system is backward compatible - built-in actors in `actors/` still work.
