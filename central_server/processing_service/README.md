# Data Processing Service

This service is responsible for consuming events from the RabbitMQ queue `lifelog_events_queue`, processing them using advanced logic (including LLM-based analysis), and storing the structured results (timeline entries, project data) into the central PostgreSQL database.

## Core Functionality

*   **Event Consumption:** Listens to the `lifelog_events_queue` for incoming raw event data.
*   **Data Transformation:** Converts raw log events into a structured format suitable for processing.
*   **Timeline Generation:** Utilizes a Large Language Model (LLM) via the Gemini API to analyze sequences of events and generate coherent, summarized timeline entries. This includes identifying activities, assigning start/end times, and creating descriptive notes.
*   **Project Resolution:** Attempts to associate timeline activities with relevant projects. If a project doesn't exist in the database, it's created.
*   **Database Storage:** Stores the processed timeline entries and associated project information into the PostgreSQL database.
*   **Output Logging:** Logs key processing steps and summaries to the console.

## Installation

1.  Navigate to the `central_server/processing_service` directory.
2.  Create a virtual environment (recommended):
    ```bash
    python -m venv venv
    source venv/bin/activate  # On Windows use `venv\Scripts\activate`
    ```
3.  Install the required Python dependencies:
    ```bash
    pip install -r requirements.txt
    ```
    The `requirements.txt` file includes new dependencies for PostgreSQL integration, such as `SQLAlchemy`, `psycopg2-binary`, and `pgvector`.

## Configuration

The service requires configuration for RabbitMQ connection, the Gemini API, and the PostgreSQL database.

*   **Required Services:**
    *   **RabbitMQ:** Must be running and accessible for message queuing.
    *   **PostgreSQL:** Must be running and accessible. The schema defined in `postgres/init/02_schema.sql` should be applied. Ensure the `pgvector` extension is enabled in PostgreSQL if using vector embeddings.

*   **Environment Variables:**
    *   Create a `.env` file in the `central_server/processing_service` directory.
    *   Refer to `.env.example` in the project root or the `settings.py` file for a full list of environment variables.
    *   **Essential variables to set in `.env`:**
        ```env
        # --- Gemini API ---
        GEMINI_API_KEY="YOUR_GEMINI_API_KEY"

        # --- RabbitMQ (if not using defaults) ---
        # RABBITMQ_HOST="localhost"
        # RABBITMQ_PORT="5672"
        # RABBITMQ_QUEUE="lifelog_events_queue"

        # --- PostgreSQL Database ---
        POSTGRES_HOST="localhost" # Or your DB host
        POSTGRES_PORT="5432"    # Or your DB port
        POSTGRES_USER="lifelog_user"
        POSTGRES_PASSWORD="lifelog_pass"
        POSTGRES_DB="lifelog_db"
        
        # --- Optional: LLM Cache settings ---
        # ENABLE_LLM_CACHE="True" # or "False"
        # CACHE_DIR_NAME="cache" # Relative to service root
        # CACHE_TTL_HOURS="24"

        # --- Optional: Timezone ---
        # LOCAL_TZ="America/New_York" # Default is America/Vancouver
        ```
    *   See `central_server/processing_service/logic/settings.py` for all configurable variables and their defaults.

*   **LLM Caching:**
    *   By default, LLM responses are cached in a `cache` subdirectory. This can be controlled via `ENABLE_LLM_CACHE`.

## Running the Service

This service is designed to be run as part of the `docker-compose.yml` setup in the project root.

1.  **Using Docker Compose (Recommended):**
    *   Navigate to the project root directory.
    *   Ensure Docker and Docker Compose are installed.
    *   Run `docker-compose up --build`.
    *   The service will be built from its Dockerfile and started by Docker Compose.
    *   Environment variables for connecting to RabbitMQ and PostgreSQL will be automatically configured by Docker Compose to point to the respective services (`rabbitmq`, `postgres`).
    *   Ensure `GEMINI_API_KEY` is set in the `.env` file in the project root, as this will be passed to the service.

2.  **Running Standalone (for development/testing outside Docker Compose):**
    *   Navigate to the `central_server/processing_service` directory.
    *   Create and activate a virtual environment (see "Installation" section).
    *   Install dependencies: `pip install -r requirements.txt`.
    *   Ensure RabbitMQ and PostgreSQL are running and accessible.
    *   Create a `.env` file in this directory (or ensure environment variables are set globally) with the necessary configurations (see "Configuration" section, especially for `GEMINI_API_KEY`, `RABBITMQ_HOST`, `POSTGRES_HOST`, etc., pointing to your standalone services).
    *   To start the worker, run the following command from the `central_server/processing_service` directory:
        ```bash
        python worker.py
        ```

The worker will connect to RabbitMQ and start consuming messages from the `lifelog_events_queue`. Raw messages will be deserialized, transformed, processed by the timeline generation logic (using the Gemini API), and the resulting timeline entries will be stored in the PostgreSQL database. Key operations are logged to the console.