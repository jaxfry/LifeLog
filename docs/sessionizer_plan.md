# Sessionizer & Synthesis Pipeline Plan

## Overview
The goal is to create a "Smart but Cheap" system to segment the continuous stream of user data (computer usage, GPS, audio, etc.) into coherent "sessions". This segmentation allows for efficient AI processing by keeping context windows manageable while preserving the narrative of the user's day.

## Architecture: Split $\rightarrow$ Process $\rightarrow$ Refine

We will implement a three-stage pipeline:
1.  **Sessionization (Heuristic)**: Group raw events into sessions based on time and overlap.
2.  **Raw Summarization (AI)**: Generate a factual summary for each session.
3.  **Daily Synthesis (AI)**: Combine and refine summaries into a cohesive narrative.

## 1. Data Model Updates

### `Event` Model
- Add `session_id` (Foreign Key to `Session`).
- This links every raw event to a specific session container.

### `Session` Model
- `id`: UUID
- `start_time`: Timestamp
- `end_time`: Timestamp
- `narrative`: Text (Output of Stage 2 - Human readable story)
- `refined_summary`: Text (Optional, for intermediate refinement)
- `status`: Enum (PENDING, PROCESSED, SYNTHESIZED)

## 2. The Pipeline

### Stage 1: The Sessionizer (Heuristic Layer)
**Goal**: Group events logically without using expensive AI calls.

**Logic**:
1.  **Chronological Sort**: Fetch all unassigned events for the day and sort them strictly by `timestamp`. This ensures that late-arriving data (e.g., synced GPS logs) is placed correctly in the timeline, effectively solving the "re-opening sessions" issue.
2.  **Time Gaps**: Iterate through the sorted stream. If `Event_B.start - Event_A.end > THRESHOLD` (e.g., 10 minutes), close the current session and start a new one.
3.  **Overlap Handling**: If events overlap (e.g., a GPS location event spans the entire duration of a coding session), they are treated as a single session. The session duration extends to cover the union of all included events.

### Stage 2: Intelligent Narrative Generation (Processing Layer)
**Goal**: Transform raw data directly into rich, human-readable timeline events.

**Logic**:
- For each identified `Session`:
    - Fetch all associated `Event` records.
    - Send the structured data to the AI (e.g., Gemini Flash).
    - **Prompt**: "Analyze these raw logs and create a human-readable timeline event. Interpret the user's intent and context (e.g., 'Studying Pre-Calculus at Starbucks' instead of 'Opened PDF, GPS at Starbucks'). Focus on the story."
    - **Output**: "Went to Starbucks, bought a sandwich for $8, and studied chapter 5.4 of Pre-Calculus 11."
    - Store this in `Session.narrative`.

### Stage 3: Daily Synthesis (Refinement Layer)
**Goal**: Merge related contexts and polish the narrative.

**Logic**:
- Fetch all `Session.narrative` texts for the day.
- Send them to the AI (e.g., Gemini Pro) in a single batch (or large chunks).
- **Prompt**: "Review these chronological session narratives. Combine related activities and ensure a smooth flow. If multiple sessions describe the same ongoing activity, merge them."
- **Output**: A cohesive, polished timeline of the day's events.

## 3. Scheduling
- The pipeline will run as a scheduled job (e.g., nightly or every X hours).
- Because we sort chronologically in Stage 1, the system is robust to data arriving out of order before the job runs.
