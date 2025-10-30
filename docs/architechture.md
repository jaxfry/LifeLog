---

## LifeLog System Architecture: A Definitive Guide (v3.3)

> **Implementation Status (Updated Oct 2025)**: The core server-side data pipeline is ~70% implemented.
> - ✅ **Fully Implemented**: Raw logs → Events → Enrichment pipeline, Actor system, Extension registration, Manifest schema, Managed schemas (Tier 3), Dynamic extension code loading, AI integration, Event embeddings
> - ⚠️ **Partially Implemented**: Extension code is dynamically loaded from `extensions/` directory; Extensions declare actors/schemas via manifest but client-side components not yet implemented
> - ❌ **Not Yet Implemented**: Client applications, automatic reprocessing on version change (manual trigger only), WebSocket/SSE streaming API, batch worker orchestration, agent scheduler
>
> See `server/extensions/README.md` for how to create extensions with dynamic code loading and managed schemas.

### 1. Core Philosophy & Architectural Principles

The LifeLog system is an **extension-first, modular platform** for personal data aggregation and AI-driven insight. It follows a secure, distributed architecture composed of a central server and one or more clients.

- **Client-Server Architecture:** The system is split into a central **server** (the single source of truth for data and heavy processing) and one or more **clients** (responsible for data collection and user interface rendering). Extensions can contain code for both environments.
- **Managed API, Not Direct Access:** Extensions **never** interact with the database directly. They use a high-level, secure API provided by the core system.
- **Immutable Raw Layer:** The original data from any source is treated as a sacred, immutable ledger. It is never altered, allowing for perfect auditing and reprocessing.
- **Versioning and Atomic Reprocessing:** Data is versioned, not replaced. When an actor's logic is updated (indicated by a version bump in its manifest), the system can reprocess old data. The new output is created alongside the old, and the old data is atomically marked as `superseded` only upon successful completion. This provides a zero-downtime, zero-risk path for upgrades and corrections. The canonical timeline is always composed of the latest, non-superseded data.
- **Decoupled & Stateless Actors:** All server-side processing logic is encapsulated in stateless "actors." These actors operate on data queues, making the system resilient and scalable.
- **Centralized AI as a Core Service:** AI is a core server-side utility. A central AI service manages models, credentials, and prompts, providing a unified interface for all extensions.
- **Asynchronous-First AI Processing:** The system prioritizes the use of asynchronous, batch-processing APIs for all non-interactive AI workloads to dramatically reduce operational costs.
- **Security Through Sandboxing:** Extensions operate in a "zero-trust" sandbox on both the client and server. They have no default network or filesystem access and must declaratively request specific permissions.

---

### 2. The Layered Data Model (Server-Side)

The entire server-side data pipeline is structured in four distinct layers, bridged by a dedicated state management system.

- **Layer 1: The Raw Ledger (`raw_logs`)**
    - **Purpose:** The universal, unfiltered inbox for all incoming data from any source.
    - **Characteristics:** Immutable, chronologically ordered, contains the original `JSONB` payload. This is the single source of truth.
- **Layer 2: The Canonical Timeline (`events`)**
    - **Purpose:** To provide a clean, unified, and queryable timeline. This is the primary data structure for most queries.
    - **Characteristics:** Composed of a lean, generic `events` table with data common to all events. Queries for the timeline always filter for records that have not been superseded (`WHERE superseded_by_event_id IS NULL`).
- **Layer 3: The Enrichment & Details Layer**
    - **Purpose:** To store all additive knowledge, context, and specific structured data about an event.
    - **Characteristics:** This layer has two components:
        1. **`event_metadata` & `event_embeddings`:** Flexible tables for storing AI classifications, user tags, and vector data. This is the "Tier 2" approach, suitable for 90% of extensions.
        2. **Managed `_details` Tables:** Optional, custom-structured tables that extensions can request for complex or performance-critical data. This is the "Tier 3" approach.
- **Layer 4: The Synthesis Layer (`synthesis_reports`)**
    - **Purpose:** To store the high-level, AI-generated outputs of holistic analysis (e.g., a "daily timeline summary").
    - **Characteristics:** This layer does not represent raw events, but rather a meta-analysis *of* many events over a period of time. It provides the data for high-level UI views and is also versioned via the `superseded_by` pattern.

---

### 3. The Dual-Sided Extension Model & Manifest

An extension is a self-contained package that adds functionality to LifeLog. It formally separates server-side and client-side concerns.

### 3.1. The `manifest.json` Contract

Every extension has a `manifest.json` file at its root. This is the declarative contract that tells the core system everything it needs to know, including its components, permissions, and required schemas.

```json
{
  "slug": "activitywatch-connector",
  "name": "ActivityWatch Connector",
  "version": "1.1.0",
  "server_side": {
    "actors": [
      {
        "slug": "aw-processor",
        "type": "PROCESSOR",
        "version": "1.1.0",
        "description": "Processes raw AW data into computer activity events."
      }
    ],
    "managed_schemas": {
      "schema_version": 1,
      "tables": {
        "aw_computer_activity_details": {
          "columns": [
            { "name": "app_name", "type": "TEXT" },
            { "name": "window_title", "type": "TEXT" }
          ]
        }
      }
    }
  },
  "client_side": {
    "platforms": {
      "macos": {
        "collectors": [
          { "slug": "mac-collector", "entrypoint": "collector.js" }
        ],
        "ui_components": [
          {
            "slug": "weekly-summary-widget",
            "type": "dashboard-widget",
            "name": "Weekly Activity Summary",
            "component": "widgets/WeeklySummary.html",
            "permissions": {
              "data_read": [
                "self.events",
                "self.synthesis_reports"
              ]
            }
          }
        ]
      }
    }
  }
}

```

### 3.2. Server-Side Components (`Actors`)

These run on the central server and perform all heavy lifting. Their `version` in the manifest is critical for triggering reprocessing.

- **`SOURCE`:** Handles the initial processing of an incoming `raw_log`.
- **`PROCESSOR`:** Transforms `raw_logs` into canonical `events`.
- **`ENRICHER`:** Adds data to the Enrichment Layer for a single event.
- **`BATCH_WORKER`:** Manages asynchronous, multi-stage jobs like daily synthesis.
- **`AGENT`:** A proactive actor that runs on a schedule to check conditions and trigger actions.

### 3.3. Client-Side Components

These run on the user's device (e.g., a Mac desktop app).

- **`COLLECTOR`:** A background process responsible for gathering data.
- **`UI_COMPONENT`:** A piece of the user interface (e.g., a widget).

---

### 4. The Core AI Service (Server-Side)

This central, built-in service abstracts all AI functionality.

- **Provider Management:** Manages credentials for remote (`litellm`) and local models in `ai_providers`.
- **Prompt Management:** Manages versioned templates in `prompt_templates`.
- **Unified API:** Exposes a simple API that supports both immediate, interactive calls and the multi-stage lifecycle of asynchronous jobs. All AI calls log their usage to a central `ai_usage_log` table for comprehensive cost tracking.

---

### 5. State Management: The Processing Log (Server-Side)

A dedicated ledger table tracks the processing state for every actor and data item.

- **`actor_processing_log` Table:** The single source of truth for processing state.
- **Non-destructive:** Entries are never deleted to facilitate reprocessing. The log tracks every version of an actor that has processed a given data item, providing a complete audit trail.
- **Expanded Statuses:** The `status` field is crucial and includes states for the batch lifecycle: `SUCCESS`, `FAILURE`, `SKIPPED`, `BATCH_SUBMITTED`, `BATCH_PROCESSING`.

---

### 6. The Complete Database Schema (Server-Side)

This is the definitive schema for the LifeLog core server system, updated to support versioning and non-destructive reprocessing.

```sql
-- ========= CORE SYSTEM & EXTENSION MANAGEMENT =========

CREATE TABLE extensions (
    id SERIAL PRIMARY KEY,
    slug TEXT NOT NULL UNIQUE,
    name TEXT NOT NULL,
    version TEXT NOT NULL,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    config JSONB
);

CREATE TABLE actors (
    id SERIAL PRIMARY KEY,
    extension_id INT NOT NULL REFERENCES extensions(id) ON DELETE CASCADE,
    slug TEXT NOT NULL,
    actor_type TEXT NOT NULL, -- 'SOURCE', 'PROCESSOR', etc.
    version TEXT NOT NULL, -- The current version from the manifest
    UNIQUE(extension_id, slug)
);

CREATE TABLE devices (
    id SERIAL PRIMARY KEY,
    name TEXT NOT NULL UNIQUE,
    type TEXT,
    encrypted_api_key TEXT NOT NULL UNIQUE,
    last_seen TIMESTAMPTZ,
    metadata JSONB -- For storing client version, OS, etc.
);

-- ========= CORE DATA FLOW & ENRICHMENT (WITH VERSIONING) =========

CREATE TABLE raw_logs (
    id BIGSERIAL PRIMARY KEY,
    source_actor_id INT NOT NULL REFERENCES actors(id),
    device_id INT REFERENCES devices(id),
    raw_data JSONB NOT NULL,
    ingested_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE event_types (
    id SERIAL PRIMARY KEY,
    owner_extension_id INT NOT NULL REFERENCES extensions(id) ON DELETE CASCADE,
    slug TEXT NOT NULL,
    description TEXT,
    UNIQUE(owner_extension_id, slug)
);

CREATE TABLE events (
    id BIGSERIAL PRIMARY KEY,
    processor_actor_id INT NOT NULL REFERENCES actors(id),
    start_time TIMESTAMPTZ NOT NULL,
    end_time TIMESTAMPTZ,
    event_type_id INT NOT NULL REFERENCES event_types(id),
    summary TEXT,
    -- Link to the superseding event for non-destructive reprocessing
    superseded_by_event_id BIGINT REFERENCES events(id) ON DELETE SET NULL,
    INDEX (superseded_by_event_id)
);

CREATE TABLE event_raw_log_links (
    event_id BIGINT NOT NULL REFERENCES events(id) ON DELETE CASCADE,
    raw_log_id BIGINT NOT NULL REFERENCES raw_logs(id) ON DELETE CASCADE,
    PRIMARY KEY (event_id, raw_log_id)
);

CREATE TABLE event_embeddings (
    id BIGSERIAL PRIMARY KEY,
    event_id BIGINT NOT NULL REFERENCES events(id) ON DELETE CASCADE,
    actor_id INT NOT NULL REFERENCES actors(id),
    embedding VECTOR(1536) NOT NULL, -- Dimension is configurable
    ai_usage_log_id BIGINT REFERENCES ai_usage_log(id) UNIQUE,
    UNIQUE(event_id, actor_id)
);

CREATE TABLE event_metadata (
    id BIGSERIAL PRIMARY KEY,
    event_id BIGINT NOT NULL REFERENCES events(id) ON DELETE CASCADE,
    actor_id INT REFERENCES actors(id), -- Can be NULL if added by user
    type TEXT NOT NULL,
    data JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ========= CORE AI & USAGE TRACKING =========

CREATE TABLE ai_providers (
    id SERIAL PRIMARY KEY,
    name TEXT NOT NULL,
    provider_slug TEXT NOT NULL UNIQUE,
    model_type TEXT NOT NULL, -- 'LLM', 'EMBEDDING', etc.
    provider_type TEXT NOT NULL, -- 'REMOTE_API', 'LOCAL_MANAGED'
    encrypted_credentials TEXT,
    model_path_or_uri TEXT,
    config JSONB,
    is_active BOOLEAN NOT NULL DEFAULT TRUE
);

CREATE TABLE prompt_templates (
    id SERIAL PRIMARY KEY,
    owner_extension_id INT REFERENCES extensions(id) ON DELETE CASCADE,
    slug TEXT NOT NULL,
    description TEXT,
    template_text TEXT NOT NULL,
    version INT NOT NULL DEFAULT 1,
    UNIQUE(owner_extension_id, slug)
);

CREATE TABLE ai_usage_log (
    id BIGSERIAL PRIMARY KEY,
    actor_id INT REFERENCES actors(id),
    ai_provider_id INT NOT NULL REFERENCES ai_providers(id),
    event_id BIGINT REFERENCES events(id) ON DELETE SET NULL,
    call_type TEXT NOT NULL, -- 'synthesis', 'embedding', etc.
    model_used TEXT NOT NULL,
    prompt_tokens INT,
    completion_tokens INT,
    cost DECIMAL(10, 6),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ========= SYNTHESIS LAYER (WITH VERSIONING) =========

CREATE TABLE synthesis_reports (
    id BIGSERIAL PRIMARY KEY,
    actor_id INT NOT NULL REFERENCES actors(id),
    start_time TIMESTAMPTZ NOT NULL,
    end_time TIMESTAMPTZ NOT NULL,
    report_type TEXT NOT NULL,
    report_data JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    ai_usage_log_id BIGINT REFERENCES ai_usage_log(id) UNIQUE,
    -- Link to the superseding report
    superseded_by_report_id BIGINT REFERENCES synthesis_reports(id) ON DELETE SET NULL,
    -- NOTE: Uniqueness for the LATEST report is now handled by application logic
    -- using a partial index or checks before insert.
    INDEX (superseded_by_report_id)
);

CREATE TABLE synthesis_event_links (
    report_id BIGINT NOT NULL REFERENCES synthesis_reports(id) ON DELETE CASCADE,
    event_id BIGINT NOT NULL REFERENCES events(id) ON DELETE CASCADE,
    PRIMARY KEY (report_id, event_id)
);

-- ========= STATE MANAGEMENT (UPDATED FOR REPROCESSING) =========

CREATE TABLE actor_processing_log (
    id BIGSERIAL PRIMARY KEY,
    actor_id INT NOT NULL REFERENCES actors(id) ON DELETE CASCADE,
    actor_version_at_processing TEXT NOT NULL, -- Record of the actor version used
    raw_log_id BIGINT REFERENCES raw_logs(id) ON DELETE CASCADE,
    event_id BIGINT REFERENCES events(id) ON DELETE CASCADE,
    status TEXT NOT NULL,
    processed_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    details JSONB,
    -- NOTE: Uniqueness constraints are removed to allow different actor versions
    -- to process the same source data item. The application logic is now
    -- responsible for queuing reprocessing jobs appropriately.
    CONSTRAINT chk_data_source CHECK (raw_log_id IS NOT NULL OR event_id IS NOT NULL)
);

```

---

### 7. System & API Boundaries

The system has four distinct, purpose-built APIs.

- **1. The Ingestion API (Client -> Server):**
    - **Purpose:** To receive raw data from client-side `Collectors`.
    - **Endpoint:** A single, secure `POST /ingest` endpoint.
    - **Authentication:** Requires a device-specific API key.
    - **Workflow:** Authenticates, validates, then immediately queues the raw data for processing, ensuring the API is fast and resilient.
- **2. The Client Data API (Client <-> Server):**
    - **Purpose:** To power the user interface on client applications by fetching processed data.
    - **Endpoints:** A set of read-only REST or GraphQL endpoints like `GET /api/v1/timeline`, `GET /api/v1/synthesis_reports`.
    - **Authentication:** Requires user-level authentication (e.g., OAuth, JWT).
    - **Workflow:** The client requests clean data for display. The server queries its canonical data layers (`events`, `synthesis_reports`) and returns it.
- **3. The Internal Actor API (Server-Side Only):**
    - **Purpose:** The managed API used by server-side `Actors` to do their work.
    - **Interface:** A Python (or other language) library.
    - **Workflow:** This is the internal `lifelog.api.*` contract, with functions like `get_unprocessed_events`, `log_processing_status`, and access to the `ai_service`.
- **4. The Push/Streaming API (Server -> Client):**
    - **Purpose:** To provide real-time updates to connected clients, avoiding the need for constant polling.
    - **Technology:** Implemented via WebSockets or Server-Sent Events (SSE).
    - **Workflow:** When a significant change occurs on the server (e.g., a new `event` is created), the server pushes a notification to authenticated clients. The client can then fetch the full data via the Client Data API, leading to a much more responsive UI.

---

### 8. Security Model for UI Components

To safely run third-party `UI_COMPONENT`s, the system employs a multi-layered "defense in depth" strategy based on the principle of Zero Trust.

### Layer 1: The Execution Sandbox (Containment)

The component's code is executed in a tightly restricted `<iframe>` to isolate it from the host application.

- **Implementation:** An `<iframe>` with a strict `sandbox` attribute and a Content Security Policy (CSP).
- **Example:**
    
    ```html
    <iframe
      src="lifelog-extension://<extension-slug>/path/to/component.html"
      sandbox="allow-scripts allow-same-origin"
      csp="default-src 'self'; connect-src 'self' <https://api.lifelog.app>; style-src 'self' 'unsafe-inline';">
    </iframe>
    
    ```
    
- **Security Benefit:** This prevents the component from accessing the host's DOM, cookies, local storage, or performing unauthorized actions like popups or navigation. The CSP further restricts it to only load resources and make network calls to approved domains.

### Layer 2: Mediated API Access (The Data Proxy)

The component never handles raw authentication tokens. The host application acts as a secure proxy for all data requests using `window.postMessage`.

- **Workflow:**
    1. The component sends an `API_REQUEST` message to the host parent window.
    2. The host receives the message, validates its origin, and makes the API call using its secure credentials.
    3. The host sends an `API_RESPONSE` message containing only the necessary data back to the component.
- **Security Benefit:** Credentials are never exposed to the extension's code. The host can audit, filter, and rate-limit all requests made on behalf of the component.

### Layer 3: Declarative Permissions (The Contract)

The extension must declare the specific data it needs to access in its `manifest.json`, which is presented to the user for consent.

- **Implementation:** A `permissions` block within the `ui_components` definition in the manifest.
    
    ```json
    "permissions": {
      "data_read": ["self.events", "self.synthesis_reports"],
      "network_access": ["<https://api.github.com>"]
    }
    
    ```
    
- **Security Benefit:** This enforces the Principle of Least Privilege. The API Proxy (Layer 2) rejects any request for data not declared in the manifest. The Sandbox (Layer 1) dynamically constructs the CSP to only allow network access to declared domains.

### Layer 4: Visual Trust & UI Guardrails

The user must always be able to distinguish between the core application's UI and an extension's UI to prevent phishing or UI spoofing.

- **Implementation:** The host application renders a mandatory, non-removable "chrome" or wrapper around every UI component.
- **Features:** This wrapper will clearly display the extension's name and icon and may provide consistent controls (e.g., a "..." menu for permissions).
- **Security Benefit:** It provides a clear visual distinction, preventing an extension from impersonating the core application's UI to trick the user.

---

### 9. End-to-End Example: "ActivityWatch Connector"

This example demonstrates the full client-server extension lifecycle, including an upgrade.

1. **Installation:**
    - User installs the "ActivityWatch Connector" (v1.0.0) from the LifeLog web UI.
    - The **server** reads the manifest, registers the `aw-processor` actor with its `version` ("1.0.0"), creates the `computer-activity` type in `event_types`, and runs migrations.
    - The **client app** syncs, sees the `client_side` component, and starts the `aw-mac-collector`.
2. **Data Collection & Ingestion (Client -> Server):**
    - The `aw-mac-collector` gathers data and sends it to `POST /ingest`.
3. **Processing & Enrichment (Server-Side):**
    - The scheduler queues jobs for the `aw-processor` (v1.0.0).
    - The actor transforms raw logs into canonical `events`. The system creates entries in `actor_processing_log` with `actor_version_at_processing: "1.0.0"`.
4. **Displaying Data (Server -> Client):**
    - The client UI fetches data from the Client Data API. The API automatically queries for `events` `WHERE superseded_by_event_id IS NULL` to show the correct timeline.
5. **Upgrade & Reprocessing:**
    - The extension developer releases "ActivityWatch Connector" v1.1.0, which improves how it categorizes application usage.
    - The user updates the extension. The server sees the `version` for the `aw-processor` actor is now "1.1.0".
    - The core system identifies all `raw_logs` that were previously processed by an older version of this actor. It queues them for reprocessing by `aw-processor` v1.1.0.
    - For each `raw_log`, the new actor runs, creating a new `event` (e.g., ID `456`). Upon successful creation, the system updates the original, old `event` (e.g., ID `123`) to set its `superseded_by_event_id` to `456`.
    - The user's timeline instantly and atomically reflects the more accurate data, with no downtime or data loss.