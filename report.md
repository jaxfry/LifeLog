# LifeLog — Pre-Wipe Continuity Report

**Generated:** 2026-08-28 (mac reset imminent)
**Branch:** `prod-refactor`
**Checkpoint:** *"Pre-wipe checkpoint: full working state of prod-refactor (sources, captures, evidence-backed memory, intelligence, iOS client, web UI)"*. History has been rewritten since the checkpoint, so use the current `prod-refactor` branch instead of a recorded commit hash.
**Remote:** `origin/prod-refactor` (GitHub `jaxfry/LifeLog`) — **pushed and up to date.** Existing clones must re-clone or reset to the rewritten history.
**Test status at checkpoint:** `uv run pytest` → **235 passed, 1 skipped** (SQLite suite).
**Lint:** ruff policy enforced; pre-commit (gitleaks) passes on the committed tree.

---

## 0. TL;DR — what you need to resume

1. Code is safe on GitHub (`origin/prod-refactor`). After reset: `git clone` / `git checkout prod-refactor`.
2. Runtime data is intentionally excluded from Git. Restore persistent data from the deployment backup or storage system you operate; this repository contains application source and safe demo fixtures only.
3. The committed tree is a **green, coherent working state**. The 13-phase production refactor is functionally complete through Phase 13 (safe identity resolution & merging).
4. Environment rebuild: `uv` for Python (`server/`), `npm`/`node` for `web/`, Docker for Postgres+Redis+pgvector. See §6.
5. One file was deliberately **excluded** from the commit: `ios/collected/drafts.jsonl` (sample captured data containing idempotency UUIDs that tripped gitleaks — false positives, but it's throwaway sample data, not source). Added to `.gitignore`.

---

## 1. What was accomplished (refactor scope)

The `prod-refactor` branch is a from-scratch production rewrite of LifeLog as a self-hosted **modular monolith**: FastAPI + SQLModel(async) backend, React/Vite web app, and a Python data-collection client. The canonical design docs are:

- `docs/PRODUCTION_REFACTOR_PLAN.md` — phase-by-phase status (authoritative)
- `docs/architecture.md` — normative system architecture
- `docs/PRODUCT_MODEL.md` — capability/source/life-area product model
- `docs/EXTENSION_CONTRACT.md` — extension ownership boundary
- `docs/INTELLIGENCE_LAYER.md` — assistant & background-intelligence design
- `docs/INTELLIGENCE_UPGRADE_PLAN.md`, `docs/CONNECTOR_SDK.md`, `docs/IOS_CLIENT_UX.md` — supplementary

All 13 planned phases are marked **complete** in the plan doc:

| Phase | Area | Status |
|---|---|---|
| 0–2 | Platform, security (JWT/bcrypt/device keys/rate-limit), ingestion (dedup raw → versioned Events) | ✅ |
| 3–5 | Sessionization (30-min/logical-date), AI timeline + daily summaries via LiteLLM, APIs | ✅ |
| 6–7 | Python client recovery, full services-layer migration (deleted stale `core.*` business logic) | ✅ |
| 8 | Memory kernel: entities/aliases/relations, valid-time, supersession, deterministic extraction | ✅ |
| 9 | Artifact intelligence: content-addressed uploads, OCR/transcription, evidence-grounded proposals | ✅ |
| 10 | Lifetime recall: rebuildable `SearchDocument`, GIN + pgvector HNSW fusion, embedding enrichment | ✅ |
| 11 | Source instances + universal capture + resumable uploads + staged `ProcessingJob` | ✅ |
| 12 | Life Areas (context/privacy), one Inbox, `lifelog_sdk`, connector ergonomics | ✅ |
| 13 | Safe identity resolution & merging (owner-isolated, pair-stable Inbox decisions, reversible) | ✅ |

### Key subsystems present (server/`app`)
- **API** (`app/api/`): admin, ai_chat, analytics, auth, commitments, data, devices, extensions, files, ingest, kernel, search, summaries, timeline, **captures, inbox, life_areas, sources** (new in this checkpoint).
- **Services** (`app/services/`): ingestion, sessionizer, processing, timeline, summarizer, ai, prompts, cache, artifacts, kernel, extension_runtime, source_secrets, jobs, uploads, commitment_reconciliation, extraction, retrieval, commitments, planning, evidence, grounding, claims, ontology, entity_resolution, reconciliation, derivations, dirty_scopes, model_router, query_planning, intelligence, tools, **chat_context, context, inbox, measurements, uploads, sources-related** (new).
- **Models** (`app/models/`): auth, ingest, processing, config, accounting, files, kernel, retrieval, **captures, claims, context, evidence, intelligence, sources** (new).
- **Core** (`app/core/`): config, database, dependencies, security, logger, rate_limit, utils, files, file_processing, ai_files, extension_utils, processing_lock.
- **Workers** (`app/workers/`): ARQ `WorkerSettings`, `task_normalize_log`, `task_process_file_batch`.
- **Migrations** (`server/alembic/versions/`): heads through `017_owned_recall_projection`, plus `d900ecdc` (semantic key) and `f7b2b40c` (refresh tokens). Single head applies cleanly to empty Postgres.

### Frontend (web/)
New pages wired into `App.jsx` routing: **Captures, Inbox, LifeAreas, Sources**, plus refreshed Dashboard/Timeline/DailySummaries/AIInsights. Added `MarkdownMessage.jsx`, date-range utilities, auth-context and api-client updates.

### iOS client (ios/)
Native Swift capture extension scaffold: `APIClient`, `AppModel`, `AppIntents`, `AdditionalCollectors`, `AudioRecorder`, `BackgroundUploadManager`, Xcode project + scheme, and built `.ipa`/`.ipa.zip` (committed). Drives photo/note/audio capture to the universal-capture API.

### Client (lifelog_client/)
ActivityWatch adapter (`com.lifelog.aw`) updated for buffer/sync recovery and processor wiring.

### SDK & scripts
- `server/lifelog_sdk/` — typed connector SDK (stable revisions, paged polling, secret-safe contexts, normalizer validation).
- `server/scripts/` — `demo_story.py`, `seed_realistic_day.py` (demo/seed data under `server/storage/demo/`).

---

## 2. Test coverage (at checkpoint)
- `server` suite: **235 passed, 1 skipped** locally (SQLite default).
- Included: sessionizer, processing pipeline, extraction, kernel API, retrieval, search, captures, sources, intelligence, entity resolution, grounded memory, chat context, context+inbox, iOS extension, auth flow, AI service, tools, AI chat, analytics, daily summary, timeline, timezone flow, extensions.
- PostgreSQL/pgvector suite historically 185 passed + 3 env-skipped (per plan doc); not re-run here but unchanged.

---

## 3. Known gaps / not yet done (explicit, from plan doc)
These are the **next** milestones — none block the current usable state:

**Operational scale**
- Fan-out normalization for high-volume connectors; metrics/alerting (queue age, embedding backlog, retrieval latency, OCR/transcription cost).
- Backup/restore & DR drill against lifetime-sized data; content-storage encryption + KMS rotation for source secrets.

**Retrieval quality**
- Embedding-model/fusion-weight evaluation on a versioned personal-recall benchmark.
- Indexed alias/entity recall (replace substring discovery at scale).
- Cautious embedding-assisted entity-resolution *proposals* (never auto-merge on vector similarity).
- Contradiction review & graph-community summaries (longitudinal data dependent).

**Extension safety / ecosystem**
- Isolation model for third-party extensions (currently managed-trust Python, auditable-but-not-sandboxed).
- Resource budgets + idempotent notification delivery receipts; packaging/signing rules before any marketplace.

**Product validation**
- End-to-end school-domain pilot (recordings, scanned assignments, due-date review, study questions, planning).
- Accessibility, privacy export/deletion, user-facing recovery UX.

---

## 4. Files / state caveats from this checkpoint
- `ios/collected/drafts.jsonl` **excluded** (sample data, gitleaks false-positive UUIDs) and git-ignored.
- `ios/LifeLog.ipa` + `.ipa.zip` **committed** (324K each, build artifacts — fine for now; consider git-lfs later if size grows).
- `server/.env.example` was deleted (config now centralized in root `.env.example`); no real secrets committed.
- 8 commits were already on the remote before this checkpoint; the checkpoint adds the full working tree diff (≈29k lines across 190+ files).

---

## 5. How to resume after the reset

```bash
# 1. Get the code
git clone https://github.com/jaxfry/LifeLog.git
cd LifeLog
git checkout prod-refactor          # or: git pull origin prod-refactor

# 2. Backend (uv required — see AGENTS.md)
cd server
uv pip install -r requirements.txt
cp ../.env.example .env            # set SECRET_KEY and DATABASE_URL
docker compose --profile testing up test_db   # Postgres+Redis+pgvector
uv run alembic upgrade head
uv run uvicorn app.main:app --reload
uv run arq app.workers.main.WorkerSettings --watch /app   # background jobs
uv run pytest                                      # verify green (expect 235 passed)

# 3. Frontend
cd ../web
npm install
npm run dev

# 4. Client (optional)
cd ../lifelog_client
uv pip install -r requirements.txt
```

**Critical post-reset notes**
- Set a real `SECRET_KEY` (app raises `RuntimeError` in prod if default & `DEBUG=false`). Generate: `uv run python -c "import secrets; print(secrets.token_hex(32))"`.
- Restore any deployment-specific storage credentials from your secret store if your deployment uses off-repository storage. The checked-in application currently uses its configured local content-storage path.
- Redis is optional at runtime (ARQ degrades safely when absent), but needed for full background processing.

---

## 6. One-line resume prompt for a fresh session
> "Resume LifeLog `prod-refactor`. The 13-phase production refactor is complete and tests are green (235 passed). Next work is in the 'Remaining production work' section of `docs/PRODUCTION_REFACTOR_PLAN.md` — pick an operational-scale or retrieval-quality milestone. Rebuild the backend with `uv` per `server/` AGENTS.md."

---
*Report written automatically as a pre-wipe checkpoint. The runtime-data purge rewrote history on 2026-08-29; verify the current `prod-refactor` branch after cloning rather than relying on the original checkpoint hash.*
