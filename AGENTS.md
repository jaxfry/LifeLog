# LifeLog — Project Rules

## Project Overview

LifeLog is a self-hosted, Python-native platform for personal data aggregation, timeline generation, and AI-driven insights. Architecture is a **modular monolith** with clear layer separation: `api/` → `services/` → `models/`.

- **Server**: FastAPI backend (Python 3.12) under `server/app/`
- **Web**: React + Vite frontend under `web/`
- **Client**: Python data collector under `lifelog_client/`

**Tech stack**: Python 3.12, FastAPI, SQLModel + asyncpg, Alembic, ARQ + Redis, APScheduler, LiteLLM, bcrypt + python-jose, pytest-asyncio, slowapi

---

## Commands

All commands run from `server/` unless noted. Always use `uv` — never `pip` or bare `python`.

| Action | Command |
|---|---|
| Install deps | `uv pip install -r requirements.txt` |
| Run server | `uv run uvicorn app.main:app --reload` |
| Run worker | `uv run arq app.workers.main.WorkerSettings --watch /app` |
| Run tests | `uv run pytest` |
| Run one test | `uv run pytest tests/test_file.py -k test_name -v` |
| Run lint | `uv run ruff check .` |
| Run typecheck | N/A (no mypy/pyright configured yet) |
| Alembic migrate | `uv run alembic upgrade head` |
| Alembic new migration | `uv run alembic revision --autogenerate -m "description"` |
| Seed test data | `uv run scripts/seed_data.py` |
| Reset DB | `uv run scripts/reset_db.py` |
| Docker compose up | `docker compose up --build` (from `server/`) |
| Docker test DB only | `docker compose --profile testing up test_db` |

---

## Code Standards

### Python Conventions
- Type hints required on all function signatures
- Async throughout — all route handlers, service methods, and DB operations are async
- Imports: standard library, then third-party, then app modules (one blank line between groups)
- Use `X | None` in all annotations (function signatures and variables alike) — ruff `UP045` enforces this; `Optional[X]` is rejected.
- `_utcnow()` helper for timestamps (see models)

### FastAPI Patterns
```python
router = APIRouter()

@router.get("/resource")
async def list_resources(
    pagination: Pagination = Depends(),
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    statement = select(Resource).offset(pagination.offset).limit(pagination.limit)
    result = await session.execute(statement)
    return result.scalars().all()
```
- Always use `get_session` for DB sessions (from `app.core.database`)
- Use `get_current_user` for protected endpoints, `verify_device` for device-auth
- Rate limit with `@limiter.limit("N/minute")` — requires `request: Request` param
- Exceptions: `raise HTTPException(status_code=status.HTTP_4XX, detail="message")`

### SQLModel Conventions
```python
def _utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)

class Model(SQLModel, table=True):
    __tablename__ = "table_name"
    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    name: str = Field(index=True, nullable=False)
    data: Dict[str, Any] = Field(default=None, sa_column=Column(JSONB))
    created_at: datetime = Field(default_factory=_utcnow, nullable=False)
    updated_at: datetime = Field(default_factory=_utcnow, nullable=False)
```
- UUID PKs with `default_factory=uuid.uuid4`
- JSONB columns use `sa_column=Column(JSONB)` (import from `sqlalchemy.dialects.postgresql`)
- Foreign keys use `foreign_key="table.column"` string form
- Relationships use `Relationship(back_populates="attr")` with `TYPE_CHECKING` guard
- All datetime fields store naive UTC (strip tzinfo after generation)

### Test Patterns
- Uses `pytest-asyncio` with `asyncio_mode = auto` in pytest.ini
- Tests marked `@pytest.mark.asyncio`, `@pytest.mark.unit` or `@pytest.mark.integration`
- Fixtures in `tests/conftest.py`:
  - `session` — fresh DB session per test (SQLite file-based by default)
  - `async_client` — HTTPX async client with DI overrides
  - `mock_user` — overrides `get_current_user` (regular user)
  - `mock_superuser` — overrides `get_current_superuser`
  - `mock_device_auth` — overrides `verify_device`
- Tests auto-cleanup tables between runs
- All test files run by default (no pytest.ini ignores). The full suite must stay green.

---

## Architecture

### Layer Structure
```
api/        → Thin route handlers, validation (Pydantic models inline)
services/   → Business logic, orchestration
core/       → Infrastructure: config, DB, DI, security, rate limit, logger, utils, file storage & metadata, extension utils, processing lock
models/     → SQLModel table definitions (one file per domain)
workers/    → ARQ background worker tasks
loader/     → Extension loading/running
```

### Dependency Injection
- DB: `session: AsyncSession = Depends(get_session)` — uses `async_session_factory` from `app.core.database`
- Auth: `current_user: User = Depends(get_current_user)` — decodes JWT, fetches user
- Device auth: `device: Device = Depends(verify_device)` — hashes API key, looks up device
- Pagination: `pagination: Pagination = Depends()` — provides `limit`/`offset` query params
- Tests override deps via `app.dependency_overrides[key] = mock_fn`

### Models (app/models/)
| File | Tables |
|---|---|
| `auth.py` | User, Device |
| `ingest.py` | RawLog, Event |
| `processing.py` | Session, TimelineEntry, DailySummary |
| `config.py` | Extension, SystemConfig, Prompt |
| `accounting.py` | AIUsage |
| `files.py` | FileAttachment |

DO NOT import from `app.models.data` — that file is deleted.

### Services (app/services/)
| File | Responsibility |
|---|---|
| `ingestion.py` | Deduplicate & insert raw logs |
| `sessionizer.py` | Group un-sessioned events into sessions |
| `processing.py` | Orchestrate pipeline, mark dirty sessions |
| `timeline.py` | AI timeline generation per session |
| `summarizer.py` | Daily summary generation |
| `ai.py` | LiteLLM wrapper, caching, token counting |
| `prompts.py` | Prompt template management |
| `cache.py` | LLM response cache |

### Core (app/core/)
| File | Responsibility |
|---|---|
| `config.py` | `Settings` class via pydantic-settings |
| `database.py` | Engine, `async_session_factory`, `get_session`, `init_db`/`close_db` |
| `dependencies.py` | `get_current_user`, `get_current_superuser`, `verify_device`, `Pagination` |
| `security.py` | Password hashing, JWT create/decode, API key hashing |
| `logger.py` | `setup_logging()` / `get_logger()` |
| `rate_limit.py` | `limiter` (slowapi) |
| `utils/time.py` | Timezone-aware date utilities |
| `files.py` | Content-addressed upload storage (`UPLOAD_DIR`, `save_file`, `create_attachment`) |
| `file_processing.py` | EXIF/PDF metadata extraction |
| `ai_files.py` | AI file content analysis (uses `app.services.ai.call_llm`) |
| `extension_utils.py` | Extension manifest sync (`sync_extensions_db`) |
| `processing_lock.py` | Redis distributed lock for reprocessing jobs |

### Workers (app/workers/)
| File | Responsibility |
|---|---|
| `main.py` | `WorkerSettings` for ARQ CLI; `task_normalize_log`, `task_process_file_batch` |
| `process.py` | `process_log` — loads a RawLog, runs the extension `normalize()`, creates Events |
| `files.py` | `task_process_file_batch` — AI file analysis batches |

### Loader (app/loader/)
| File | Responsibility |
|---|---|
| `runner.py` | `run_normalization(extension_id, payload)` — dynamically imports `extensions/{id}/processor.py` and calls `normalize()` |

---

## Cleanup Rules

### Removing Dead Code
1. `grep` for all imports of the module/function you plan to remove
2. Check test files, migration files, and `__init__.py` exports
3. Run `uv run pytest` to verify nothing breaks
4. Run `uv run ruff check .` for import warnings
5. If removing a model, ensure alembic migrations reference the correct table name

### Stale Imports
- Run `ruff check .` — it catches unused imports
- Check for `# noqa: F401` comments that may be hiding legit unused imports

### Alembic Conventions
- Always generate migrations with `--autogenerate` after model changes
- Manually verify the generated migration before applying
- Never edit a migration that has already been applied to a shared DB
- Use sequential revision IDs (e.g., `001`, `002`) or timestamps
- Set `down_revision` correctly when chaining migrations

### Verifying Cleanups
```bash
cd server
uv run pytest                                          # Full test suite
uv run pytest -k "test_name"                           # Targeted test
uv run pytest tests/integration/test_full_pipeline.py  # Integration test
uv run ruff check . --fix                              # Auto-fix lint issues
```

---

## Critical Conventions

- **SECRET_KEY must be set in production**. The app raises `RuntimeError` if SECRET_KEY is the default and DEBUG is false. Generate with: `uv run python -c "import secrets; print(secrets.token_hex(32))"`
- **All datetime fields store naive UTC**. Use the `_utcnow()` helper pattern: `datetime.now(timezone.utc).replace(tzinfo=None)`. Never store aware datetimes.
- **Session gap threshold: 30 minutes** (config: `SESSION_GAP_MINUTES = 30`). Events within 30min of each other are grouped into the same session. Events across logical date boundaries always split sessions.
- **Use `uv` not `pip` or `python`**. For package installs: `uv pip install ...`. For running: `uv run foo`.
- **Don't import from `app.models.data`** — it was deleted. Import from `app.models.auth`, `app.models.ingest`, `app.models.processing`, `app.models.config`, `app.models.files`, or `app.models.accounting`.
- **Don't import from `app.core.db`** — it was deleted. Use `app.core.database` (which provides `get_session`, `async_session_factory`, `init_db`, `close_db`).
- **Don't import from `app.core.ingestion`, `app.core.sessionizer`, `app.core.prompts`, `app.core.timeline_processor`, `app.core.ai_config`, `app.core.rebuilder`, `app.core.scheduler`, `app.core.processing`** — all deleted during the services migration. Business logic lives in `app.services.*`; worker tasks live in `app.workers.*`.
- **Tests never run against production DB**. `conftest.py` blocks execution if `DATABASE_URL` looks like production. Uses SQLite file-based by default.
- **Mark tests appropriately**: `@pytest.mark.unit` for isolated tests, `@pytest.mark.integration` for tests needing DB/Redis.
- **Ruff config**: `server/ruff.toml` codifies conventions (FastAPI `Depends()` idiom, naive-UTC datetimes, resilience excepts). Run `uv run ruff check .` from `server/`.
