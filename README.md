# LifeLog

LifeLog is a personal activity tracking and analysis application designed to help you understand how you spend your time. It ingests data from various sources, enriches it using AI, and provides visualizations and summaries of your daily activities.

## Core Features

*   **Data Ingestion:** Automatically imports data from personal activity trackers. Currently supports [ActivityWatch](https://activitywatch.net/) for window titles, application usage, and AFK (away-from-keyboard) status.
*   **Timeline Enrichment:** Leverages Large Language Models (LLMs) to process raw event data into a structured, human-readable timeline. This includes identifying distinct activities, assigning them to projects, and generating concise notes.
*   **Daily Summaries:** Utilizes LLMs to generate insightful summaries of your day's activities based on the enriched timeline.
*   **Web Interface:** Provides a user-friendly web application (built with React and FastAPI) to browse your daily timelines and view summaries.

## Project Structure

The project is organized into the following main directories:

*   **`LifeLog/`**: Contains the core Python-based command-line interface (CLI) tool and data processing logic. This includes modules for:
    *   `ingestion/`: Fetching data from sources like ActivityWatch.
    *   `enrichment/`: Processing raw data into an enriched timeline using LLMs.
    *   `summary/`: Generating daily summaries from the timeline data using LLMs.
    *   `cli.py`: The main entry point for the CLI.
    *   `config.py`: Handles application settings.
    *   `models.py`: Pydantic models for data structures.
*   **`backend/`**: A Python FastAPI web server that provides an API to access the processed LifeLog data (timelines, summaries).
*   **`frontend/`**: A React/TypeScript application (built with Vite) that consumes the backend API to display your LifeLog data in a user-friendly interface.
*   **`tests/`**: Contains unit and integration tests for the Python components.

## The `LifeLog` CLI Tool

The `LifeLog/` directory houses a powerful command-line interface (CLI) for managing your LifeLog data. It's the primary way to ingest raw data, perform AI-driven enrichment, and generate summaries.

Key commands are executed via `python -m LifeLog.cli <command> <subcommand>`:

*   **Ingest Data:**
    *   `python -m LifeLog.cli ingest activitywatch --day YYYY-MM-DD`: Fetches ActivityWatch data for the specified day.
    *   `python -m LifeLog.cli ingest activitywatch --days-ago N`: Fetches ActivityWatch data for N days ago.
*   **Enrich Timeline:**
    *   `python -m LifeLog.cli enrich timeline --day YYYY-MM-DD`: Processes the raw data for the specified day to create an enriched timeline using an LLM.
    *   `python -m LifeLog.cli enrich timeline --days-ago N`: Enriches the timeline for N days ago.
    *   Add `--force-llm` to re-query the LLM even if cached results exist.
    *   Add `--force-processing` to re-process the day even if an output file already exists.
*   **Generate Daily Summary:**
    *   `python -m LifeLog.cli summarize daily --day YYYY-MM-DD`: Generates an LLM-based summary for the specified day's activities.
    *   `python -m LifeLog.cli summarize daily --days-ago N`: Summarizes activities for N days ago.
    *   Add `--force` to force regeneration of the summary, ignoring existing output.
    *   Add `--force-summary-llm` to specifically re-query the LLM for the summary.
*   **Process Day (All Steps):**
    *   `python -m LifeLog.cli process-day --day YYYY-MM-DD`: Runs the full pipeline (ingest, enrich, summarize) for the specified day.
    *   `python -m LifeLog.cli process-day --days-ago N`: Runs the full pipeline for N days ago.
    *   `--force-all`: Forces reprocessing for all steps and re-queries LLMs.
    *   `--force-enrich-llm`, `--force-summary-llm`: Force LLM re-queries for specific steps if `--force-all` is not used.

Configuration for the CLI (like API keys, model names, paths, etc.) is managed through a `.env` file in the project root and loaded by `LifeLog/config.py`. Refer to `LifeLog/config.py` for available settings.

## Backend API

The `backend/` directory contains a FastAPI application that serves the processed LifeLog data over a REST API. This allows the frontend application (or any other client) to fetch timeline entries and daily summaries.

Key aspects:

*   **Framework:** Built with [FastAPI](https://fastapi.tiangolo.com/).
*   **Purpose:** To provide access to the data generated and stored by the `LifeLog` CLI tools (e.g., curated timelines from `LifeLog/storage/curated/timeline/` and summaries from `LifeLog/storage/summary/daily/`).
*   **Main Endpoints** (actual routes are defined in `backend/app/routes/`):
    *   `/api/v1/day/{date_str}/timeline`: Retrieves the enriched timeline for a specific date.
    *   `/api/v1/day/{date_str}/summary`: Retrieves the daily summary for a specific date.
    *   Other endpoints may be available for different data views or aggregations.

The API is typically run locally using a Uvicorn server.

## Frontend Application

The `frontend/` directory hosts a modern web application for visualizing your LifeLog data.

Key features:

*   **Technology Stack:** Built with [React](https://react.dev/), [TypeScript](https://www.typescriptlang.org/), and [Vite](https://vitejs.dev/).
*   **Purpose:** To provide a user-friendly interface for browsing daily enriched timelines and viewing generated summaries.
*   **Components:** Includes views for individual day timelines and summary panels.
*   **Data Source:** Fetches data from the `backend` FastAPI application.

The frontend includes its own `README.md` with more details on its setup and development, which is largely the standard Vite template information.

## Getting Started

To get LifeLog up and running, follow these general steps:

1.  **Clone the Repository:**
    ```bash
    git clone <repository_url> # Replace <repository_url> with the actual URL
    cd <repository_directory>
    ```

2.  **Run the Setup Script (optional):**
    ```bash
    ./tools/setup_env.sh
    ```
    This installs Python and Node dependencies, creates `.venv`, and populates the sample test data.

3.  **Set up Python Environment (for `LifeLog/` CLI and `backend/` API):**
    *   It's recommended to use a virtual environment (e.g., `venv` or `conda`).
    *   Create and activate a virtual environment:
        ```bash
        python -m venv .venv
        source .venv/bin/activate # On Windows: .venv\Scripts\activate
        ```
    *   Install Python dependencies. Assuming a `requirements.txt` exists or will be created for both the LifeLog CLI and the backend:
        ```bash
        pip install -r requirements.txt # Run in the root, or separate for LifeLog/ and backend/ if they have their own
        # Or, if using Poetry or another manager, follow its install instructions.
        ```
        *(Note: You might need separate `requirements.txt` files for `LifeLog/` and `backend/` or a combined one in the root.)*

4.  **Set up Node.js Environment (for `frontend/`):**
    *   Navigate to the `frontend` directory:
        ```bash
        cd frontend
        ```
    *   Install Node.js dependencies:
        ```bash
        npm install
        # Or yarn install if using Yarn
        ```
    *   Return to the root directory:
        ```bash
        cd ..
        ```

5.  **Configure Environment Variables:**
    *   Create a `.env` file in the project root directory by copying the example if one is provided (e.g., `cp .env.example .env`).
    *   Edit the `.env` file to include necessary configurations:
        *   `LIFELOG_OPENAI_API_KEY` or `LIFELOG_GEMINI_API_KEY`: Your API key for the LLM provider. (The specific variable name might depend on `config.py`)
        *   Paths for data storage (if you want to override defaults from `LifeLog/config.py`).
        *   Any other settings required by `LifeLog/config.py`.

6.  **Prepare ActivityWatch (Data Source):**
    *   Ensure ActivityWatch is installed and running.
    *   Configure `aw-watcher-window`, `aw-watcher-afk`, and potentially `aw-watcher-web-*` if you use supported browsers (like Arc).

7.  **Use the Sample Test Day (Optional):**
    *   If you want to run the API and UI without ActivityWatch, populate the storage directories with the included test data:
        ```bash
        lifelog setup-test-data
        ```
    *   This copies `tests/testdata/2025-05-22.parquet` and a small summary file into `LifeLog/storage/curated/timeline/` and `LifeLog/storage/summary/daily/`.
    *   The customizable dashboard includes a quick link to this date so you can explore the interface immediately. You can toggle widgets such as Quick Links, Daily Summary, AI Insights, Stats, and more.

8.  **Run Backend Server:**
    *   Navigate to the `backend` directory (if not already there for pip install).
    *   Start the FastAPI server (typically using Uvicorn):
        ```bash
        # From the backend/ directory, if main.py is in backend/app/
        cd backend 
        uvicorn app.main:app --reload 
        # Or from the root directory:
        # uvicorn backend.app.main:app --reload
        ```
    *   The server usually runs on `http://127.0.0.1:8000`.

7.  **Run Frontend Development Server:**
    *   Navigate to the `frontend` directory:
        ```bash
        cd frontend
        ```
    *   Start the Vite development server:
        ```bash
        npm run dev
        ```
    *   The frontend is usually accessible at `http://localhost:5173`.

## Usage Workflow

Here's a typical workflow for using LifeLog:

1.  **Ensure Setup is Complete:**
    *   Verify that ActivityWatch is running and collecting data.
    *   Confirm your `.env` file is correctly configured with API keys and any desired path overrides.

2.  **Process Data for a Day:**
    *   Open your terminal and navigate to the project's root directory.
    *   Activate your Python virtual environment (`source .venv/bin/activate`).
    *   Use the `LifeLog.cli` to ingest and process data for the desired day. For example, to process yesterday's data:
        ```bash
        python -m LifeLog.cli process-day --days-ago 1
        ```
        Or for a specific date:
        ```bash
        python -m LifeLog.cli process-day --day YYYY-MM-DD
        ```
    *   This command will:
        *   Fetch raw data from ActivityWatch.
        *   Enrich the data to create a detailed timeline.
        *   Generate a daily summary.
        *   Store the results in the configured `LifeLog/storage` directories.

3.  **Start the Backend and Frontend Servers:**
    *   **Backend:**
        *   In a new terminal window/tab, navigate to the project root (or `backend/` directory).
        *   Activate the virtual environment.
        *   Start the FastAPI server:
            ```bash
            # From project root
            uvicorn backend.app.main:app --reload 
            ```
    *   **Frontend:**
        *   In another terminal window/tab, navigate to the `frontend/` directory.
        *   Start the Vite development server:
            ```bash
            npm run dev
            ```

4.  **View Your LifeLog:**
    *   Open your web browser and go to the frontend URL (usually `http://localhost:5173`).
    *   You should be able to see the interface, select dates, and view your enriched timeline and daily summary for the processed days.

**Tip:** You can run the `process-day` command daily (e.g., via a scheduled task) to keep your LifeLog data up-to-date.

## Key Technologies

LifeLog is built using a combination of modern tools and technologies:

*   **Backend & CLI:**
    *   Python 3.x
    *   FastAPI (for the web API)
    *   Pydantic (for data validation and settings management)
    *   Pandas & DuckDB (likely for data manipulation, inferred from typical Python data stacks)
    *   Interacts with LLM APIs (e.g., Gemini)
*   **Frontend:**
    *   React
    *   TypeScript
    *   Vite (build tool and dev server)
*   **Data Sources:**
    *   ActivityWatch
*   **Data Storage:**
    *   Parquet files (for structured data)
    *   JSON files (for LLM outputs, caches, and API responses)
*   **Environment Management:**
    *   `venv` (or Conda) for Python
    *   `npm` (or Yarn) for Node.js
