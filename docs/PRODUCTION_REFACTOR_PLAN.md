# LifeLog Production Refactor Plan

## Vision

Production-ready, self-hosted personal data aggregation platform. Modular monolith backend (FastAPI + Redis + PostgreSQL) with a Python desktop client. No frontend in this scope — a TypeScript SPA will come later.

## Design Principles

- **Modular monolith** — single deployable FastAPI server with clean internal domain boundaries, splittable into microservices later if needed
- **Fresh schema** — clean baseline with UUID v7, no pgvector initially, no legacy cruft
- **Core-first** — ingestion → processing → AI enrichment → API, deferring file management and vector search
- **Security by default** — auth on every endpoint, rate limiting, proper password hashing, no hardcoded secrets
- **Resilience** — graceful degradation, proper shutdown, health checks, no hard external dependencies
- **Test reality** — tests run against real PostgreSQL, not monkeypatched SQLite

---

## Architecture

```
┌─────────────┐     ┌──────────────────────────────────────┐
│ Python Client│────▶│          LifeLog Server              │
│ (desktop     │HTTP │  (FastAPI + ARQ + APScheduler)       │
│  tray app)   │     │                                      │
└─────────────┘     │  ┌─────────┐  ┌──────────┐           │
                    │  │ API     │  │ Services │           │
                    │  │ (routes)│──│(business)│           │
                    │  └─────────┘  │  logic)  │           │
                    │               └────┬─────┘           │
                    │               ┌────▼─────┐           │
                    │               │ Workers  │           │
                    │               │  (ARQ)   │           │
                    │               └──────────┘           │
                    └──────────┬───────────────────────────┘
                               │
                    ┌──────────▼───────────┐     ┌─────────┐
                    │   PostgreSQL 17      │     │  Redis 7 │
                    │   (pgvector-ready)   │     │ (ARQ)   │
                    └──────────────────────┘     └─────────┘
```

### Project Structure

```
lifelog/
├── server/
│   ├── app/
│   │   ├── api/              # Route handlers (thin, no business logic)
│   │   │   ├── auth.py         # POST /token, GET /me
│   │   │   ├── devices.py      # Device CRUD (admin)
│   │   │   ├── ingest.py       # POST /ingest (API key auth)
│   │   │   ├── timeline.py     # Timeline entry CRUD + list
│   │   │   ├── summaries.py    # Daily summary retrieval
│   │   │   ├── admin.py        # Admin operations, reprocessing
│   │   │   └── health.py       # Health + readiness endpoints
│   │   ├── core/             # Shared infrastructure
│   │   │   ├── config.py       # Pydantic Settings (env-based)
│   │   │   ├── database.py     # Async engine + session lifecycle
│   │   │   ├── security.py     # JWT, bcrypt, API key hashing
│   │   │   ├── dependencies.py # FastAPI Depends (auth, pagination)
│   │   │   ├── logger.py       # Structured logging
│   │   │   └── rate_limit.py   # SlowAPI config
│   │   ├── models/           # SQLModel definitions (the schema)
│   │   │   ├── auth.py         # User, Device
│   │   │   ├── ingest.py       # RawLog, Event
│   │   │   ├── processing.py   # Session, TimelineEntry, DailySummary
│   │   │   ├── config.py       # SystemConfig, Prompt
│   │   │   └── accounting.py   # AIUsage
│   │   ├── services/         # Domain services (business logic)
│   │   │   ├── ingestion.py    # Dedup, hash, write pipeline
│   │   │   ├── sessionizer.py  # Time-group events into sessions
│   │   │   ├── enrichment.py   # LiteLLM timeline generation
│   │   │   ├── summarizer.py   # Daily summary generation
│   │   │   └── processing.py   # Orchestrator (cascading rebuilds)
│   │   └── workers/          # ARQ background workers
│   │       ├── config.py       # WorkerSettings
│   │       ├── process.py      # Event normalization worker
│   │       ├── enrich.py       # AI enrichment worker
│   │       └── summarize.py    # Daily summary worker
│   ├── alembic/
│   │   ├── versions/         # Migration 001 = fresh baseline
│   │   └── env.py
│   ├── tests/
│   │   ├── conftest.py         # Fixtures, DB guard, test DB lifecycle
│   │   ├── test_auth.py
│   │   ├── test_ingestion.py
│   │   ├── test_sessionizer.py
│   │   ├── test_enrichment.py
│   │   ├── test_api_timeline.py
│   │   └── test_integration.py # Full pipeline E2E
│   ├── Dockerfile
│   ├── requirements.txt
│   └── pytest.ini
├── client/
│   ├── core/
│   │   ├── config.py
│   │   ├── sync_engine.py
│   │   └── extension_manager.py
│   ├── extensions/
│   │   └── com.lifelog.aw/     # ActivityWatch collector
│   ├── tests/
│   ├── main.py
│   └── requirements.txt
├── docker-compose.yml          # PostgreSQL + Redis + Server + optional client
└── .env.example
```

---

## Fresh Schema Design (Migration 001)

### Tables

```sql
-- users
CREATE TABLE users (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),  -- v7 later
    username        TEXT NOT NULL UNIQUE,
    hashed_password TEXT NOT NULL,
    is_active       BOOLEAN NOT NULL DEFAULT TRUE,
    is_superuser    BOOLEAN NOT NULL DEFAULT FALSE,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- devices
CREATE TABLE devices (
    id              TEXT PRIMARY KEY,  -- e.g. "macbook-pro-jaxon"
    name            TEXT,
    device_type     TEXT,
    api_key_hash    TEXT NOT NULL,
    last_cursor     TIMESTAMPTZ,
    is_active       BOOLEAN NOT NULL DEFAULT TRUE,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- raw_logs (L1 — immutable inbox)
CREATE TABLE raw_logs (
    id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    device_id         TEXT NOT NULL REFERENCES devices(id),
    extension_id      TEXT NOT NULL,
    payload           JSONB NOT NULL,
    client_timestamp  TIMESTAMPTZ,
    client_timezone   TEXT,             -- IANA, e.g. "America/Vancouver"
    logical_date      TEXT,             -- YYYY-MM-DD, indexed
    payload_hash      TEXT NOT NULL UNIQUE,  -- SHA-256
    received_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    processing_status TEXT NOT NULL DEFAULT 'pending'
        CHECK (processing_status IN ('pending', 'processing', 'done', 'failed'))
);
CREATE INDEX idx_raw_logs_device ON raw_logs(device_id);
CREATE INDEX idx_raw_logs_extension ON raw_logs(extension_id);
CREATE INDEX idx_raw_logs_logical_date ON raw_logs(logical_date);

-- events (L2 — normalized event stream)
CREATE TABLE events (
    id                 UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    source_log_id      UUID NOT NULL REFERENCES raw_logs(id),
    session_id         UUID REFERENCES sessions(id),
    event_type         TEXT NOT NULL,
    start_time         TIMESTAMPTZ NOT NULL,
    end_time           TIMESTAMPTZ,
    data               JSONB NOT NULL DEFAULT '{}',
    processing_version INT NOT NULL DEFAULT 1,
    is_superseded      BOOLEAN NOT NULL DEFAULT FALSE,
    logical_date       TEXT,
    created_at         TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX idx_events_session ON events(session_id);
CREATE INDEX idx_events_type ON events(event_type);
CREATE INDEX idx_events_start_time ON events(start_time);
CREATE INDEX idx_events_logical_date ON events(logical_date);

-- sessions (L3-A — time-grouped events)
CREATE TABLE sessions (
    id                 UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    start_time         TIMESTAMPTZ NOT NULL,
    end_time           TIMESTAMPTZ NOT NULL,
    status             TEXT NOT NULL DEFAULT 'pending'
        CHECK (status IN ('pending', 'processing', 'completed', 'failed')),
    retry_count        INT NOT NULL DEFAULT 0,
    logical_date       TEXT,
    processing_status  TEXT NOT NULL DEFAULT 'ready'
        CHECK (processing_status IN ('ready', 'processing', 'error')),
    last_touched_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    created_at         TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at         TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX idx_sessions_start_time ON sessions(start_time);
CREATE INDEX idx_sessions_status ON sessions(status);
CREATE INDEX idx_sessions_logical_date ON sessions(logical_date);

-- timeline_entries (L3-B — AI-generated narrative)
CREATE TABLE timeline_entries (
    id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    session_id    UUID REFERENCES sessions(id),
    start_time    TIMESTAMPTZ NOT NULL,
    end_time      TIMESTAMPTZ NOT NULL,
    activity      TEXT NOT NULL,
    notes         TEXT,
    category      TEXT,
    tags          JSONB NOT NULL DEFAULT '[]',
    prompt_id     UUID REFERENCES prompts(id),
    is_summarized BOOLEAN NOT NULL DEFAULT FALSE,
    logical_date  TEXT,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at    TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX idx_timeline_session ON timeline_entries(session_id);
CREATE INDEX idx_timeline_start_time ON timeline_entries(start_time);
CREATE INDEX idx_timeline_category ON timeline_entries(category);
CREATE INDEX idx_timeline_logical_date ON timeline_entries(logical_date);

-- daily_summaries
CREATE TABLE daily_summaries (
    logical_date        TEXT PRIMARY KEY,  -- YYYY-MM-DD
    summary_text        TEXT NOT NULL,
    key_activities      JSONB NOT NULL DEFAULT '[]',
    productivity_score  INT CHECK (productivity_score BETWEEN 1 AND 10),
    mood                TEXT,
    status              TEXT NOT NULL DEFAULT 'ready'
        CHECK (status IN ('ready', 'dirty')),
    last_touched_at     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- prompts (versioned prompt templates)
CREATE TABLE prompts (
    id         UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name       TEXT NOT NULL,
    template   TEXT NOT NULL,
    version    INT NOT NULL DEFAULT 1,
    is_active  BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX idx_prompts_name ON prompts(name);

-- system_config
CREATE TABLE system_config (
    key         TEXT PRIMARY KEY,
    value       TEXT NOT NULL,
    description TEXT,
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ai_usage (accounting)
CREATE TABLE ai_usage (
    id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    timeline_entry_id UUID REFERENCES timeline_entries(id),
    provider          TEXT NOT NULL,
    model             TEXT NOT NULL,
    input_tokens      INT NOT NULL DEFAULT 0,
    output_tokens     INT NOT NULL DEFAULT 0,
    cost              DOUBLE PRECISION NOT NULL DEFAULT 0,
    latency_ms        INT NOT NULL DEFAULT 0,
    created_at        TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX idx_ai_usage_created ON ai_usage(created_at);
```

### Key Schema Changes from prototypefinal

| Change | Reason |
|---|---|
| UUID v7 (time-ordered) instead of v4 | Better B-tree index performance at scale |
| Single `logical_date` string | Eliminates dual `date`/`logical_date` confusion |
| Single `client_timezone` (IANA) | No duplicated `timezone`/`iana_timezone` columns |
| Clean session statuses | Remove `DIRTY`, `SYNTHESIZED` — just pending/processing/completed/failed |
| Remove `file_attachments` table | Deferred to later scope |
| Remove `daily_chapters` table | Deferred to later scope (AI can regenerate from timeline) |
| Remove `blobs`, `failures` tables | Never used; errors go to logs, blobs handled separately later |
| No pgvector columns | Deferred; no embeddings until vector search is needed |
| Consistent `created_at`/`updated_at` | Every mutable table gets both |
| Proper FK constraints | Referential integrity enforced at DB level |
| CHECK constraints | Status values validated at DB level, not just in app |

---

## API Endpoints

### Auth (no auth required)
| Method | Path | Description |
|---|---|---|
| POST | `/api/v1/token` | Login, returns JWT (rate limited: 5/min) |

### Auth (JWT required)
| Method | Path | Description |
|---|---|---|
| GET | `/api/v1/me` | Current user info |

### Health (no auth)
| Method | Path | Description |
|---|---|---|
| GET | `/api/v1/health` | Basic health |
| GET | `/api/v1/health/live` | Liveness probe |
| GET | `/api/v1/health/ready` | Readiness probe (checks DB + Redis) |

### Ingestion (API key auth, rate limited: 60/min)
| Method | Path | Description |
|---|---|---|
| POST | `/api/v1/ingest` | Ingest raw log payload |

### Data (JWT required)
| Method | Path | Description |
|---|---|---|
| GET | `/api/v1/timeline` | List timeline entries (paginated, filterable) |
| GET | `/api/v1/timeline/{id}` | Get single timeline entry |
| PUT | `/api/v1/timeline/{id}` | Update timeline entry |
| GET | `/api/v1/summaries` | List daily summaries |
| GET | `/api/v1/summaries/{date}` | Get single daily summary |

### Admin (JWT + superuser required)
| Method | Path | Description |
|---|---|---|
| POST | `/api/v1/users` | Create user |
| POST | `/api/v1/devices` | Register device |
| GET | `/api/v1/devices` | List devices |
| PATCH | `/api/v1/devices/{id}` | Update device |
| DELETE | `/api/v1/devices/{id}` | Delete device |
| POST | `/api/v1/devices/{id}/rotate-key` | Rotate API key |
| POST | `/api/v1/admin/reprocess/{date}` | Trigger reprocessing for a date |
| GET | `/api/v1/admin/status` | System status (pending, dirty counts) |
| GET | `/api/v1/config` | List config |
| PUT | `/api/v1/config/{key}` | Set config |

---

## Implementation Phases

### Phase 0 — Project Scaffold

Files to create:
- `server/app/__init__.py`
- `server/app/core/__init__.py`, `config.py`, `database.py`, `logger.py`
- `server/requirements.txt`
- `server/Dockerfile`
- `server/pytest.ini`
- `server/app/models/__init__.py`
- `.env.example`
- `docker-compose.yml` (PostgreSQL 17 + Redis 7 + server)
- Alembic init + migration 001

Key decisions:
- Pydantic Settings `Config` class reading from environment
- SQLAlchemy async engine with `asyncpg`
- Alembic configured for async
- Docker Compose with health checks on DB + Redis
- Test DB guard (refuse to run against production DB URL)

### Phase 1 — Auth & Security

Files to create:
- `server/app/models/auth.py` — User, Device models
- `server/app/core/security.py` — password hashing, JWT, API key hashing
- `server/app/core/dependencies.py` — get_current_user, get_current_superuser, verify_device_api_key, Pagination
- `server/app/core/rate_limit.py` — SlowAPI limiter
- `server/app/api/auth.py` — POST /token, GET /me
- `server/app/api/devices.py` — admin device CRUD
- `server/app/api/health.py` — health endpoints

Key decisions:
- JWT HS256, 30-min expiry, configurable via env
- bcrypt for password hashing
- SHA-256 for API key hashing (one-way, stored hash only)
- API key on ingest, JWT on data/admin endpoints
- Rate limit: 5/min on login, 60/min on ingest
- CORS with configurable origins
- TrustedHost middleware

### Phase 2 — Ingestion Pipeline

Files to create:
- `server/app/models/ingest.py` — RawLog, Event models
- `server/app/services/ingestion.py` — hash, dedup, write, enqueue
- `server/app/api/ingest.py` — POST /ingest
- `server/app/workers/config.py` — ARQ WorkerSettings
- `server/app/workers/process.py` — normalize raw log → events

Key decisions:
- `payload_hash = SHA-256(JSON.dumps(payload, sort_keys=True))`
- UNIQUE constraint on `(device_id, payload_hash)` for dedup at DB level
- IntegrityError catch for race condition handling
- ARQ job enqueued on each successful ingest
- No hard Redis dependency — worker is optional (ingest still succeeds without Redis, logs marked `pending`)
- Payload size limit (configurable, default 10MB)

### Phase 3 — Processing Pipeline

Files to create:
- `server/app/models/processing.py` — Session, TimelineEntry, DailySummary models
- `server/app/services/sessionizer.py` — group events into sessions
- `server/app/services/processing.py` — orchestrator, cascade rebuilds

Key decisions:
- Session gap threshold: 30 minutes
- Session size limit: 500k tokens worth of events (chunk if exceeded)
- Logical date boundary enforcement (events crossing midnight split)
- Processing status tracking: `ready → processing → error`
- Scheduled via APScheduler every 30 min
- Manual trigger via admin endpoint

### Phase 4 — AI Enrichment

Files to create:
- `server/app/services/enrichment.py` — LiteLLM timeline generation
- `server/app/services/summarizer.py` — daily summary generation
- `server/app/models/config.py` — Prompt, SystemConfig models
- `server/app/models/accounting.py` — AIUsage model
- `server/app/workers/enrich.py` — AI enrichment worker
- `server/app/workers/summarize.py` — daily summary worker

Key decisions:
- LiteLLM with multi-provider fallback: Hack Club AI (primary) → Google Gemini (fallback)
- Prompt versioning — prompts stored in DB, linked to timeline entries
- No embeddings or vector search initially (deferred)
- LLM response caching (MD5 cache key, file-based, 24h TTL)
- Chunked processing for large sessions (batches of 300 events)
- Token accounting written to `ai_usage` table
- Default prompts bootstrapped on first server start

### Phase 5 — API Layer

Files to create:
- `server/app/api/timeline.py` — timeline CRUD + list
- `server/app/api/summaries.py` — summary retrieval
- `server/app/api/admin.py` — reprocessing, config, device management

Key decisions:
- Pagination via offset/limit with configurable max (1000)
- Date range filtering on all list endpoints
- All data endpoints require JWT auth
- OpenAPI tags, descriptions, response models
- Consistent error response format

### Phase 6 — Client Refactor

Files to create/refactor:
- `client/core/config.py` — load from .env
- `client/core/sync_engine.py` — local SQLite buffer, batched sync, retry
- `client/core/extension_manager.py` — download + manage collectors
- `client/extensions/com.lifelog.aw/` — ActivityWatch collector
- `client/main.py` — system tray app

Key decisions:
- Local SQLite cache for offline resilience
- Batched upload (up to 500 events) with 3 retries
- API key stored in local .env, configured once at install
- Extensions downloaded from server on startup
- Periodic sync (every 5 min) + manual trigger

### Phase 7 — Testing & Hardening

Files to create:
- `server/tests/conftest.py` — fixtures, test DB lifecycle, mock LLM
- `server/tests/test_auth.py` — login, token expiry, API key, permissions
- `server/tests/test_ingestion.py` — dedup, validation, auth
- `server/tests/test_sessionizer.py` — grouping, boundaries, edge cases
- `server/tests/test_enrichment.py` — mocked LLM, prompt assembly, caching
- `server/tests/test_api_timeline.py` — all endpoint variations
- `server/tests/test_integration.py` — full pipeline E2E

Key decisions:
- Separate test database (auto-created, cleaned between runs)
- Mock LLM responses for deterministic tests
- Test DB guard: refuse to run against production database URL
- PostgreSQL for tests (not monkeypatched SQLite)
- Docker Compose profile for test DB
- Aim for >80% coverage on services, >90% on API routes

---

## Key Technical Decisions

| Decision | Choice | Rationale |
|---|---|---|
| Architecture | Modular monolith | Simple deploy, clean boundaries, splittable later |
| API framework | FastAPI (async) | Proven, performant, great DX |
| ORM | SQLModel | Pydantic + SQLAlchemy, already used |
| Database | PostgreSQL 17 | JSONB, reliable, pgvector-ready |
| Task queue | Redis + ARQ | Simple, proven in prototypefinal |
| Scheduler | APScheduler (in-process) | Simpler than Ofelia/cron |
| Migration | Alembic (async) | Already used, no reason to change |
| Auth (users) | JWT + bcrypt | Stateless, secure |
| Auth (devices) | API key + SHA-256 hash | Simple, one-way storage |
| AI client | LiteLLM | Multi-provider fallback, already used |
| Rate limiting | SlowAPI | Already used in prototypefinal |
| Client DB | SQLite (local buffer) | Offline resilience, already used |
| Testing DB | Real PostgreSQL | No monkeypatching, real behavior |
| Schema versioning | Fresh migration 001 | Clean break from legacy cruft |

---

## What We're Keeping from prototypefinal

- Auth system (JWT + bcrypt + API keys with SHA-256 hashing)
- LiteLLM integration with multi-provider fallback (Hack Club → Gemini)
- ARQ workers + APScheduler
- Ingestion dedup via payload_hash
- Sessionization logic (30-min gap threshold, logical date boundaries)
- Prompt versioning (prompts as data in DB)
- SQLModel models (reshaped and cleaned)
- Alembic migrations (fresh start)
- SlowAPI rate limiting
- Client sync engine + ActivityWatch extension
- Test infrastructure patterns (fixtures, DB guard)

## What's Replaced from `main`

- RabbitMQ → Redis + ARQ (simpler, already in prototypefinal)
- Microservices → modular monolith (simpler deploy)
- Ofelia scheduler → APScheduler (in-process, no extra container)
- SQL init scripts → Alembic migrations (versioned, repeatable)
- Basic auth → full JWT + bcrypt + API key auth

## What's Deferred (not in scope)

- File upload / management system
- AI file analysis (image OCR, PDF parsing)
- Daily chapters (can be reconstructed from timeline)
- Extension marketplace / ZIP upload
- Vector search / pgvector embeddings
- AI chat endpoint
- Web frontend (TypeScript SPA later)
