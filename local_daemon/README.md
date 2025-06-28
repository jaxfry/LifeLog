# LifeLog Local Daemon

The LifeLog Local Daemon is a Python application responsible for collecting user activity data,
caching it locally, and securely transmitting it to a central LifeLog server.

## Features

- **Data Collection:** Monitors user activity using ActivityWatch, capturing:
    - Active window titles and application names.
    - AFK (Away From Keyboard) status.
    - Web browsing activity (requires compatible ActivityWatch web watcher).
- **Local Caching:** Stores collected events in a local SQLite database (`local_daemon_cache.sqlite`) to:
    - Buffer data during network outages.
    - Batch data for efficient transmission.
- **Secure Data Transmission:** Sends batched JSON payloads to a (currently placeholder) central server endpoint via HTTPS.
    - Includes basic error handling and retry mechanisms for network issues.
- **Minimal Local Processing:**
    - Filters events based on minimum duration.
    - Deduplicates events based on a generated hash before adding to the cache.
- **Configurable:** Settings can be managed via environment variables or by modifying `config.py`.

## Directory Structure

```
local_daemon/
├── __init__.py         # Package initializer
├── daemon.py           # Main daemon script, orchestrates collection and sending
├── collector.py        # Handles data collection (e.g., from ActivityWatch)
├── sender.py           # Handles sending batched data to the central server
├── cache.py            # Manages the local SQLite cache for events
├── config.py           # Configuration settings for the daemon
├── local_daemon.log    # Default log file (if enabled)
└── README.md           # This file
```

## Prerequisites

- Python 3.8+
- ActivityWatch server running and accessible.
  - Ensure `aw-watcher-window` and `aw-watcher-afk` are running.
  - For web activity, ensure a compatible browser watcher (e.g., `aw-watcher-web-firefox`) is installed and configured in ActivityWatch.
- Dependencies listed in `requirements.txt` (see below).

## Setup

1.  **Clone the repository (if applicable) or ensure this `local_daemon` directory is part of your LifeLog project.**

2.  **Install Dependencies:**
    A `requirements.txt` specific to the daemon should be created if it has dependencies not already in the main project's `requirements.txt`. For now, it requires:
    ```bash
    pip install requests apscheduler aw-client~=0.5.6 # Or a more recent compatible version
    ```
    Ensure these are added to your project's overall `requirements.txt` or a dedicated one for the daemon.

3.  **Configure ActivityWatch Buckets (if necessary):**
    The daemon expects specific ActivityWatch bucket IDs. These are configurable in `local_daemon/config.py` or via environment variables:
    - `AW_WINDOW_BUCKET_ID` (default: `aw-watcher-window_{hostname}`)
    - `AW_AFK_BUCKET_ID` (default: `aw-watcher-afk_{hostname}`)
    - `AW_WEB_BROWSER_BUCKET_ID` (default: `aw-watcher-web-firefox`) - *Adjust this to match your browser watcher's bucket ID.*

    You can find your bucket IDs by looking at the ActivityWatch web UI under the "Buckets" tab.

4.  **Configure Server Endpoint:**
    The central server endpoint is configured via the `CENTRAL_SERVER_ENDPOINT` environment variable or in `config.py`.
    (Default placeholder: `https://your-central-server.example.com/api/v1/ingest`)

5.  **Environment Variables (Optional):**
    Key settings can be overridden with environment variables (see `config.py` for a full list). Examples:
    - `CENTRAL_SERVER_ENDPOINT`: URL of the central server's ingestion API.
    - `COLLECTION_INTERVAL_SECONDS`: How often to poll ActivityWatch (default: 60).
    - `BATCH_SEND_INTERVAL_SECONDS`: How often to attempt sending data to the server (default: 300).
    - `LOCAL_CACHE_DB_PATH`: Path to the SQLite cache file (default: `local_daemon_cache.sqlite`).
    - `LOG_LEVEL`: Logging level (e.g., INFO, DEBUG, ERROR; default: INFO).
    - `LOG_FILE`: Path to log file (default: `local_daemon.log`). Set to empty or remove to log to console only.


## Running the Daemon

To run the daemon directly from the `local_daemon` directory (primarily for development/testing):

```bash
python daemon.py
```

For more robust execution, especially if `local_daemon` is part of a larger project structure, run it as a module from the parent directory (e.g., from `/Users/jaxon/Coding/LifeLog`):

```bash
python -m local_daemon.daemon
```

The daemon will start logging its activity to the console and/or `local_daemon.log`.

## How it Works

1.  **Initialization:**
    - Sets up logging.
    - Initializes the local SQLite cache (`local_daemon_cache.sqlite`).
    - Initializes the `ActivityWatchCollector`.
    - Starts a background scheduler (`APScheduler`).

2.  **Scheduled Collection:**
    - Every `COLLECTION_INTERVAL_SECONDS`, the `ActivityWatchCollector` fetches new events from the configured ActivityWatch buckets since its last run.
    - Fetched events are minimally processed (basic filtering, hash generation).
    - New, unique events are added to the local SQLite cache.

3.  **Scheduled Sending:**
    - Every `BATCH_SEND_INTERVAL_SECONDS`, the `sender` module:
        - Retrieves a batch of the oldest events from the cache (up to `MAX_BATCH_SIZE`).
        - Marks these events as "attempted" in the cache.
        - Constructs a JSON payload.
        - Sends the payload to the `CENTRAL_SERVER_ENDPOINT` via HTTPS POST.
        - If the send is successful (HTTP 2xx), the sent events are deleted from the local cache.
        - If the send fails, events remain in the cache and will be retried. Basic retry logic (max attempts, delay) is implemented.

## Stopping the Daemon

Press `Ctrl+C` in the terminal where the daemon is running. The daemon will attempt a graceful shutdown of the scheduler.

## Future Considerations / TODO

-   More robust error handling and dead-letter queue for persistently failing events.
-   Configuration management via a central server (currently placeholder).
-   More sophisticated local processing/filtering if needed.
-   Packaging for easier distribution/installation.
-   Health check endpoint for the daemon itself.
-   Encryption of data at rest in the local cache (if highly sensitive data is stored).