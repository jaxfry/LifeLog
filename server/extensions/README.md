````markdown
# LifeLog Extensions Directory

This directory contains **development extensions** - Python packages that are directly loaded at server startup.

## Extensions vs Extensions Store

**Two extension directories exist for different purposes:**

- **`extensions/`** (this directory): Development/local extensions
  - Directly imported Python packages
  - Hot-reloaded on server restart
  - No signature verification required
  - Use for development and trusted first-party extensions

- **`extensions_store/`**: Production/uploaded extensions
  - Versioned packages uploaded via API
  - Signature-verified in production (Ed25519)
  - Stored as `<slug>-<version>/` subdirectories
  - Use for third-party or distributed extensions

**When to use which:**
- Local development → Use `extensions/`
- Production deployment → Upload to `extensions_store/` via API
- System owner's trusted extensions → Either location works

## Extension Structure

Each extension is a Python package (directory) with at minimum:

```
my-extension/
├── __init__.py          # Entry point, registers actors
├── manifest.json        # Metadata and schema definitions
└── (optional files)     # Additional modules, utilities, etc.
```

## Creating an Extension

### 1. Create the directory structure

```bash
mkdir extensions/my-extension
```

### 2. Create `manifest.json`

The manifest declares your extension's metadata, actors, event types, and schemas:

```json
{
  "slug": "my-extension",
  "name": "My Extension",
  "version": "1.0.0",
  "description": "What your extension does",
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
        "slug": "my-event-type",
        "description": "Events this extension creates"
      }
    ],
    "managed_schemas": {
      "schema_version": 1,
      "tables": {
        "my_details": {
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

### 3. Create `__init__.py` with actor implementations

```python
"""
My Extension for LifeLog
"""

import logging
from typing import Any
from lifelog.core.actors import ActorBase, ActorConfig, actor_registry
from lifelog import models
from lifelog.db import async_session
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
    """Your processor implementation"""

    async def run(self, data: models.RawLog) -> Any:
        raw_log = data
        logger.info(f"Processing raw_log_id: {raw_log.id}")

        async with async_session() as session:
            # Your processing logic here
            # 1. Get actor and event type from DB
            # 2. Create Event from RawLog
            # 3. Optionally write to managed schema tables
            # 4. Log processing status
            pass


logger.info("My extension loaded successfully")
```

## Managed Schemas (Custom Tables)

If your extension needs custom structured tables (the "Tier 3" approach), declare them in `managed_schemas`:

- Tables are automatically created with the prefix `{extension-slug}_`
- Example: `my-extension` creates table `my_extension_my_details`
- All tables get automatic `id`, `created_at`, and `updated_at` columns
- Use raw SQL to interact with these tables in your actors

### Allowed Column Types

- Text: `TEXT`, `VARCHAR`, `CHAR`
- Numbers: `INT`, `INTEGER`, `BIGINT`, `SMALLINT`, `DECIMAL`, `NUMERIC`, `REAL`, `DOUBLE PRECISION`
- Boolean: `BOOLEAN`, `BOOL`
- Date/Time: `DATE`, `TIME`, `TIMESTAMP`, `TIMESTAMPTZ`
- JSON: `JSONB`, `JSON`
- Binary: `BYTEA`

## Actor Types

- **SOURCE**: Handles initial processing of raw data (rarely needed for extensions)
- **PROCESSOR**: Transforms raw_logs into canonical events ⭐ Most common
- **ENRICHER**: Adds metadata/embeddings to existing events
- **BATCH_WORKER**: Multi-stage async jobs (e.g., daily synthesis)
- **AGENT**: Scheduled tasks that run periodically

## Loading Extensions

Extensions are automatically loaded at server startup. The server:

1. Scans this directory for subdirectories with `manifest.json`
2. Validates the manifest schema
3. Imports the `__init__.py` module
4. Registers actors via the `@actor_registry.register` decorators
5. Creates managed schema tables if defined

## Installing Extensions (recommended flows)

There are two supported installation flows, depending on your environment:

1) Local development (fastest)
- Drop your extension folder under `server/extensions/<your-slug>/`.
- Restart the server to let the loader discover and import it.
- Register the manifest in the DB using the internal API (stores actors/event types and client-side metadata):
  - POST `/internal/extensions/from-manifest` with the extension `manifest.json`.

2) Production (signed package upload)
- Package your extension as a zip archive containing at least `manifest.json` and `__init__.py` at the archive root.
- Sign the archive with an Ed25519 private key whose public key is present in `trusted_keys/*.pub` on the server.
- Upload via internal API:
  - POST `/internal/extensions/upload` with form fields:
    - `package` = the zip file
    - `signature` = detached signature bytes (Ed25519)
    - `approve` (optional, default true) to activate immediately, or set false to require a follow-up approval.
    - `update_if_exists` (optional, default true) to upgrade the extension if it already exists.
- The server verifies the signature, stores the extracted version under `EXTENSIONS_STORE_PATH` (versioned as `<slug>-<version>/`),
  and registers/updates the manifest in the database. You can later:
  - Approve/disable: POST `/internal/extensions/{slug}/approve`.
  - Roll back: POST `/internal/extensions/{slug}/rollback?version=<previous-version>` (requires that version to exist in the store).

Notes
- In production (`APP_ENV=production`), signatures are required for uploads.
- The store path and key directory are configurable (`EXTENSIONS_STORE_PATH`, `TRUSTED_PUBLIC_KEYS_DIR`). See `core/config.py`.
- Uploaded extensions run with `config.execution_mode = "external"` and `config.store_path` pointing to the extracted assets directory.

## Development Workflow

1. Create your extension package in this directory
2. Restart the server to load it
3. Register the extension in the database via API or manifest:
   ```bash
   curl -X POST "http://localhost:8000/internal/extensions/from-manifest" \
     -H "Content-Type: application/json" \
     -d @extensions/my-extension/manifest.json
   ```
4. Test data ingestion and processing

## Example Extensions

- **example-extension/**: A complete reference implementation showing all features

## Notes

- Extensions run in the same Python process (no true sandboxing)
- Trust model: Extensions are installed by the system owner
- Actor slugs must be globally unique across all extensions
- Extension slugs become SQL table prefixes (use lowercase with hyphens)
