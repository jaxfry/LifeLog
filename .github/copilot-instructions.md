# Copilot Instructions for LifeLog

This repo is a FastAPI + SQLModel server (Python 3.11) that powers an extension-first, actor-driven data pipeline. Follow these project-specific conventions to be productive.

## Big picture
- Data flow: raw_logs (immutable) → events (canonical timeline) → enrichment (event_metadata, event_embeddings) → synthesis_reports. Never mutate past records; supersede with new ones.
- API boundaries:
  - Ingestion API: POST /ingest (device key auth via X-Device-Key).
  - Client Data API v1: /api/v1 (JWT auth), e.g., GET /api/v1/timeline.
  - Internal API: /internal (extension mgmt + processing), e.g., /internal/extensions, /internal/event-types, /internal/processing.
- Actors: Server-side, stateless classes registered at startup. Routing from SOURCE → PROCESSOR is resolved via DB (ActorRouting) then config fallback.

## Where things live
- App entry: `server/src/lifelog/main.py` (routers, lifespan, actor loading, extension loading).
- Config: `server/src/lifelog/core/config.py` (pydantic-settings, `DATABASE_URL`, `API_V1_STR`, auth settings, `PROCESSING_ROUTING_MAP`, `EXTENSIONS_PATH`).
- DB engine/session: `server/src/lifelog/db.py` (async engine), `server/src/lifelog/dependencies.py` (AsyncSession dependency).
- Models: `server/src/lifelog/models.py` (SQLModel tables and enums).
- Schemas: `server/src/lifelog/schemas.py` (Pydantic I/O models).
- Service layer: `server/src/lifelog/services.py` (all DB queries; keep APIs thin).
- APIs: `server/src/lifelog/api/*` (auth, ingestion, processing, extensions, event_types, timeline).
- Actors: `server/src/lifelog/core/actors.py` (ActorBase, registry) and implementations in `server/src/lifelog/actors/*.py` (built-in) or `server/extensions/*/` (dynamic).
- Extensions: `server/extensions/*/` (dynamically-loaded extension packages with manifest.json and __init__.py).
- Extension loader: `server/src/lifelog/core/extension_loader.py` (discovers and loads extensions at startup).
- Schema manager: `server/src/lifelog/core/schema_manager.py` (creates managed tables from manifests).

## Patterns to follow (with examples)
- Use AsyncSession from `dependencies.get_session` in all endpoints/services. Example: Timeline filters for non-superseded events in `TimelineService.get_timeline_events`.
- Keep DB access in services; endpoints orchestrate only. Example: `api/ingestion.py` calls `IngestionService` then returns `schemas.IngestResponse`.
- Actor registration is class-based:
  - Define config + subclass ActorBase; register with the global registry.
  - **Built-in actors**: In `actors/processors.py`, use `@actor_registry.register(ActorConfig(...))`.
  - **Extension actors**: In `extensions/my-extension/__init__.py`, use `@actor_registry.register(ActorConfig(...))`.
  - Example in `actors/processors.py`:
    - `@actor_registry.register(ActorConfig(slug="test-processor", actor_type=ActorType.PROCESSOR, version="1.0.0"))`
    - Implement `async def run(self, data: models.RawLog)`; use `session = await anext(get_session())` if needed.
- Processing routing: `ProcessingRoutingService.resolve_processor_slug` prefers `ActorRouting` table; falls back to `settings.PROCESSING_ROUTING_MAP`.
- Extension system:
  - Extensions are Python packages in `server/extensions/*/` with `manifest.json` + `__init__.py`.
  - ExtensionLoader discovers and loads them at startup.
  - Manifest declares actors, event types, managed schemas.
  - SchemaManager creates extension-specific tables with slug prefix (e.g., `my_extension_details`).
  - See `docs/dynamic-extensions.md` and `extensions/README.md` for full details.

## Auth and security
- JWT (single-user) for Client Data API: POST `/api/v1/auth/token` using OAuth2PasswordRequestForm; then `Authorization: Bearer <token>`. See `api/auth.py`.
- Device auth for ingestion: header `X-Device-Key` validated against `Device.encrypted_api_key`. See `auth.device_auth_dependency`.

## Run, migrate, seed
- Dev via Docker Compose (db + server, code mounted with reload):
  ```zsh
  docker compose up -d --build
  ```
- Env: copy `.env.example` to `.env` (or `.env.docker`) and adjust `DATABASE_URL`.
- Alembic uses `core/config.settings.DATABASE_URL` (see `server/migrations/env.py`). Typical flows from `server/package.json`:
  ```zsh
  pnpm --filter @lifelog/server db:migrate    # autogenerate revision
  pnpm --filter @lifelog/server db:upgrade    # apply migrations
  ```
- Quick demo of pipeline (see `server/restart.sh` for a scripted version):
  1) POST `/internal/extensions` to register `test-extension` with `test-source` and `test-processor`.
  2) POST `/ingest` with `{ "source_actor_slug": "test-source", "data": {"message": "hi"} }` and `X-Device-Key`.
  3) POST `/internal/processing/trigger/{raw_log_id}` to run the processor.
  4) GET `/api/v1/timeline` with JWT to view events.

## Non-obvious gotchas
- README mentions bootstrap/seed scripts under `server/scripts`; those paths may not exist. Prefer the explicit curl flow or add scripts if needed.
- `actors/registry.py` is deprecated; use `core/actors.py` registry directly. `actors/__init__.py` loads modules at startup so decorators run.
- Default DB is SQLite for local dev; Docker uses Postgres from `.env`. Ensure `DATABASE_URL` matches your environment when running migrations.

## When adding features
- New API? Put orchestration in `api/*`, data logic in `services.py`, models in `models.py`, I/O schemas in `schemas.py`.
- New actor? 
  - **Built-in**: Add a class in `actors/*.py`, register via `actor_registry`.
  - **Extension**: Create a new extension package in `extensions/my-extension/` with manifest.json and __init__.py.
  - Add mapping in `ActorRouting` table or `settings.PROCESSING_ROUTING_MAP`.
- New tables/fields? 
  - **Core tables**: Update `models.py` then run Alembic migration + upgrade.
  - **Extension tables**: Use `managed_schemas` in manifest.json; SchemaManager creates them automatically.
- New extension? Follow `extensions/README.md` or `docs/dynamic-extensions.md`.
