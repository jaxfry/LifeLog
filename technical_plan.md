# Technical Plan: Direct Project Suggestion Engine (Final, with Deduplication & API)

This plan details a robust system for generating, deduplicating, and managing project suggestions.

## 1. Core Principle & Workflow

The core principle remains the same: the LLM suggests projects, and the backend acts as a gatekeeper. The workflow is enhanced to prevent creating duplicate suggestions for the same underlying concept.

## 2. Database Schema

### 2.1. `projects` Table
No changes needed.

### 2.2. `project_suggestions` Table (Updated)
To enable semantic deduplication, we must store an embedding for each suggestion.

**Updated SQL Schema:**
```sql
CREATE TYPE suggestion_status AS ENUM ('pending', 'accepted', 'rejected');

CREATE TABLE project_suggestions (
    id               UUID PRIMARY KEY,
    suggested_name   CITEXT NOT NULL,
    embedding        VECTOR(128), -- NEW: For semantic comparison
    confidence_score FLOAT NOT NULL,
    rationale        JSONB,
    status           suggestion_status NOT NULL DEFAULT 'pending',
    created_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at       TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Index for finding pending suggestions quickly
CREATE INDEX project_suggestions_pending_idx ON project_suggestions(status) WHERE (status = 'pending');

-- Vector index for similarity search on pending suggestions
CREATE INDEX project_suggestions_embedding_idx
  ON project_suggestions USING hnsw (embedding vector_cosine_ops)
  WHERE (status = 'pending');
```
*   **Key Change:** Added an `embedding` column and a corresponding vector index. This is crucial for efficiently finding semantically similar pending suggestions.

## 3. Prompt Engineering
The prompt defined in the previous plan remains correct. It encourages the LLM to suggest new, focused project names when an activity doesn't fit an existing project.

## 4. Core Processing Logic (with Deduplication)

### 4.1. `ProjectResolver`'s Enhanced Role

The `ProjectResolver` is now responsible for the full suggestion lifecycle: checking against approved projects and pending suggestions.

*   `async def get_project_by_name(...)`: No change.
*   `async def handle_new_project_name(self, name: str, timeline_entries: List[TimelineEntry])`: This is the main new method.
    1.  **Check Approved Projects:** First, it calls `get_project_by_name(name)`. If a project exists, it returns the `project_id` and stops.
    2.  **Generate Embedding:** If no approved project is found, it generates a vector embedding for the new `name`.
    3.  **Check Pending Suggestions:** It then performs a vector similarity search against all suggestions with `status = 'pending'`.
    4.  **Decision Logic:**
        *   **If a similar pending suggestion is found** (e.g., similarity > 0.90): It will **update the existing suggestion** instead of creating a new one. For example, it could append the new `timeline_entries` to the `rationale` of the existing suggestion, making it stronger. It returns `None`.
        *   **If no similar suggestion is found:** It creates a **new suggestion** in the `project_suggestions` table, storing the `name`, the new `embedding`, a calculated `confidence_score`, and the `rationale`. It returns `None`.

### 4.2. Worker's Gatekeeper Logic (Updated)

The worker's logic is now simpler, as the complexity is encapsulated in the `ProjectResolver`.

```python
# Pseudocode for the worker's logic
project_resolver = ProjectResolver(session)

for entry in timeline_entries_from_llm:
    if entry.project_name:
        # The resolver handles all logic: checking approved projects AND handling suggestions.
        project_id = await project_resolver.handle_new_project_name(
            name=entry.project_name,
            timeline_entries=[entry]
        )
        save_timeline_entry(entry, project_id=project_id) # project_id will be None if it's a new or updated suggestion
    else:
        save_timeline_entry(entry, project_id=None)
```

## 5. API Endpoints for Suggestion Management

These endpoints will be added to `central_server/api_service/api_v1/endpoints/projects.py`.

### `GET /api/v1/projects/suggestions`
*   **Action:** Retrieves a list of all project suggestions with a `status` of `'pending'`.
*   **Response:** An array of suggestion objects.
    ```json
    [
      {
        "id": "uuid-goes-here",
        "suggested_name": "LifeLog API Refactor",
        "confidence_score": 0.98,
        "rationale": { "source_entries": [...] },
        "created_at": "timestamp"
      }
    ]
    ```

### `POST /api/v1/projects/suggestions/{suggestion_id}/accept`
*   **Action:** Accepts a suggestion and converts it into a real project.
*   **Workflow:**
    1.  Find the suggestion by `suggestion_id`.
    2.  Create a new `Project` in the `projects` table using the `suggested_name` and `embedding`.
    3.  Update the suggestion's `status` to `'accepted'`.
    4.  (Optional, as a background task) Re-process the timeline entries in the suggestion's `rationale` to assign them to the new project ID.
*   **Response:** `200 OK` with the newly created project object.

### `POST /api/v1/projects/suggestions/{suggestion_id}/reject`
*   **Action:** Rejects a suggestion.
*   **Workflow:**
    1.  Find the suggestion by `suggestion_id`.
    2.  Update its `status` to `'rejected'`.
*   **Response:** `204 No Content`.

## 6. Final Workflow Diagram (with Deduplication)

```mermaid
graph TD
    A[Start: LLM proposes a project name] --> B{Is name in approved projects?};
    B -- Yes --> C[Assign Project ID];
    B -- No --> D{Generate Embedding for name};
    D --> E{Is there a similar PENDING suggestion?};
    E -- Yes --> F[Update existing suggestion's rationale];
    E -- No --> G[Create NEW suggestion in DB];
    F --> H[Timeline entry has NULL Project ID];
    G --> H;
    C --> I[End];
    H --> I;