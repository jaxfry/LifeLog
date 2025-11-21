***

# LifeLog System Architecture v4.0

## 1. Executive Summary
**LifeLog** is a self-hosted, Python-native platform for personal data aggregation, timeline generation, and AI-driven insight.
*   **Philosophy:** "Rebuild the Present from the Past." The system prioritizes infinite reprocessing capabilities.
*   **Architecture:** Secure Central Server (Python) with Distributed Clients.
*   **Extension Model:** "Managed Trust." Extensions are Python packages executed by the Core, capable of full data analysis and network I/O.

---

## 2. Tech Stack
*   **Language:** Python 3.11+
*   **API:** FastAPI (Async).
*   **ORM:** SQLModel (Pydantic + SQLAlchemy).
*   **Database:** PostgreSQL 16+ (`JSONB` for Logs, `pgvector` for Embeddings).
*   **Task Queue:** Redis + ARQ.
*   **Scheduler:** APScheduler (Cron management).
*   **AI Client:** LiteLLM.

---

## 3. The 4-Domain Database Schema

The database is organized into four logical domains.

### Domain A: The Data Pipeline (Lineage & Versioning)
| Table | Key Columns | Purpose |
| :--- | :--- | :--- |
| **`raw_logs`** (L1) | `id`, `device_id`, `extension_id`, `payload`, `received_at`, **`payload_hash`** | **Immutable Inbox.** `payload_hash` enforces idempotency (prevents duplicates). |
| **`events`** (L2) | `id`, **`source_log_id`**, `type`, `data`, **`processing_version`**, **`is_superseded`** | **Normalized Stream.** Linked to L1. `is_superseded` flags old versions of reprocessed data. |
| **`sessions`** (L3-A) | `id`, `start_time`, `end_time`, **`needs_rebuild`** | **Time Chunks.** Groups L2 events. Flag triggers AI regeneration. |
| **`timeline`** (L3-B) | `id`, `session_id`, `summary`, `embedding`, `prompt_version_id` | **The Narrative.** The AI output, strictly linked to a specific prompt version. |

### Domain B: Administration & Config
| Table | Key Columns | Purpose |
| :--- | :--- | :--- |
| `devices` | `id`, `api_key_hash`, **`last_cursor`** | Tracks the last synced timestamp per extension to optimize bandwidth. |
| `extensions` | `id`, `version`, `config` (Encrypted), **`scheduler_cron`** | Registry. `scheduler_cron` defines server-side polling tasks. |
| **`prompts`** | `id`, `name`, `template`, `version`, `is_active` | **Prompt Registry.** Stores System Prompts and Templates, allowing versioned updates without code changes. |

### Domain C: Accounting
| Table | Key Columns | Purpose |
| :--- | :--- | :--- |
| `ai_usage` | `id`, `timeline_entry_id`, `provider`, `model`, `input_tokens`, `output_tokens`, `cost`, `latency` | Granular financial audit trail. |

### Domain D: Infrastructure
| Table | Key Columns | Purpose |
| :--- | :--- | :--- |
| `blobs` | `id`, `hash`, `path` | Binary storage metadata. |
| `failures` | `id`, `traceback`, `context` | Dead Letter Queue. |

---

## 4. Core Logic Flows

### 4.1 Smart Ingestion (Deduplication)
1.  **Client Side:**
    *   Calculates `hash = sha256(payload)`.
    *   Sends `POST /ingest` with Header `X-Payload-Hash: <hash>`.
2.  **Server Side:**
    *   Checks `raw_logs` for existing `(device_id, payload_hash)`.
    *   **If Exists:** Returns `200 OK (Skipped)`. No data written.
    *   **If New:** Saves to `raw_logs`. Returns `201 Created`.

### 4.2 The Processing Pipeline (L1 $\to$ L2)
1.  **Trigger:** New L1 Log created.
2.  **Worker:**
    *   Imports the Extension's Python module (`extensions.{id}.processor`).
    *   Executes `processor.normalize(payload)`.
    *   Writes output to `events`.
    *   **Lineage:** Sets `events.source_log_id = raw_logs.id`.

### 4.3 Cascading Rebuilds (L2 $\to$ L3)
The system guarantees consistency when logic changes.
1.  **Scenario:** Normalizer logic updates or User requests reprocessing.
2.  **L2 Update:**
    *   System marks old `events` as `is_superseded = True`.
    *   Writes new `events` with current `processing_version`.
3.  **L3 Invalidation:**
    *   System identifies all `sessions` linked to the superseded events.
    *   Sets `sessions.needs_rebuild = True`.
4.  **Scheduler:**
    *   Detects "Dirty" sessions.
    *   Re-runs AI summarization using the current System Prompt.
    *   Updates `timeline` entries.

---

## 5. The Extension Ecosystem

Extensions are **Python Packages** managed by the Core.

### 5.1 Structure
*   `manifest.json`: Permissions (`network`, `filesystem`), Dependencies, Cron Schedule.
*   `processor.py`: Contains `normalize(payload)` function.
*   `poller.py`: (Optional) Contains `run()` function for scheduled tasks.
*   `prompts.yaml`: (Optional) Defines extension-specific prompt templates.

### 5.2 Capabilities
*   **Analysis:** Full access to Python ecosystem (`pandas`, `numpy`) for data cleaning.
*   **Network:** Can poll external APIs (Spotify, Weather) if permission granted.
*   **Scheduling:** Server uses `APScheduler` to run `poller.py` based on the Manifest's Cron expression.

---

## 6. AI & Prompt Management

### 6.1 Prompt Versioning
*   Prompts are **Data**, not Code.
*   Stored in `prompts` table.
*   When AI generates a Timeline entry, it links to the specific `prompt_id` used.
*   **Update Flow:**
    1.  User updates System Prompt in UI.
    2.  New row created in `prompts` (Version N+1).
    3.  New AI jobs use Version N+1.
    4.  Old Timeline entries remain linked to Version N (Historical fidelity).

### 6.2 Accounting
*   Every call to the LLM is wrapped by the **AIBroker**.
*   Logs specific Token counts (Input/Output) and Cost to `ai_usage`.
*   Allows querying: *"How much did the 'Sarcastic Robot' persona cost me last month?"*

---

## 7. Directory Structure

```text
/lifelog_core
├── /app
│   ├── /models             # SQLModel Classes
│   │   ├── data.py         # Logs, Events, Sessions, Timeline
│   │   ├── config.py       # Devices, Extensions, Prompts
│   │   └── audit.py        # AI Usage, Blobs, Failures
│   ├── /core               # System Engines
│   │   ├── ingestion.py    # Dedup & Hash Logic
│   │   ├── rebuilder.py    # Cascading Update Logic
│   │   └── scheduler.py    # APScheduler Setup
│   ├── /loader             # Extension Import Logic
│   │   └── runner.py       # Safe execution wrapper
│   └── /api                # FastAPI Routes
├── /extensions             # Installed Python Packages
│   ├── /com.lifelog.gps
│   │   ├── manifest.json
│   │   └── processor.py
│   └── /com.lifelog.aw
├── /storage
│   └── /blobs              # Binary files
└── docker-compose.yml
```