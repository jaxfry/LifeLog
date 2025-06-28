"""
Configuration for the Local Daemon.
"""
import os
import socket

# Placeholder for the central server's data ingestion endpoint
CENTRAL_SERVER_ENDPOINT = os.getenv("CENTRAL_SERVER_ENDPOINT", "http://localhost:8001/api/v1/ingest")

# Interval for collecting data from sources (e.g., ActivityWatch) in seconds
COLLECTION_INTERVAL_SECONDS = int(os.getenv("COLLECTION_INTERVAL_SECONDS", 60)) # 1 minute

# Interval for attempting to send batched data to the server in seconds
BATCH_SEND_INTERVAL_SECONDS = int(os.getenv("BATCH_SEND_INTERVAL_SECONDS", 300)) # 5 minutes

# Maximum number of events to include in a single batch sent to the server
MAX_BATCH_SIZE = int(os.getenv("MAX_BATCH_SIZE", 500))

# Path to the local SQLite database for caching events
LOCAL_CACHE_DB_PATH = os.getenv("LOCAL_CACHE_DB_PATH", "local_daemon_cache.sqlite")

# ActivityWatch specific settings
try:
    hostname = socket.gethostname()
except Exception:
    hostname = "localhost" # Fallback

AW_HOSTNAME = os.getenv("AW_HOSTNAME", hostname)
AW_PORT = int(os.getenv("AW_PORT", 5600))
AW_CLIENT_NAME = "lifelog_local_daemon"
AW_WINDOW_BUCKET_ID = f"aw-watcher-window_{AW_HOSTNAME}"
AW_AFK_BUCKET_ID = f"aw-watcher-afk_{AW_HOSTNAME}"
AW_WEB_BROWSER_BUCKET_ID = f"aw-watcher-web-arc_{AW_HOSTNAME}" # Or another browser
AW_MIN_DURATION_SECONDS = int(os.getenv("AW_MIN_DURATION_SECONDS", 5)) # Minimum duration for an event to be considered significant

# Logging configuration
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()
LOG_FILE = os.getenv("LOG_FILE", "local_daemon.log") # Set to None to log to console only

# Placeholder for device ID (should be unique per device)
# In a real scenario, this might be generated and stored, or derived from system info.
DEVICE_ID = os.getenv("DEVICE_ID", "default-device-01")

# Retry mechanism for sending data
MAX_SEND_RETRIES = int(os.getenv("MAX_SEND_RETRIES", 3))
RETRY_DELAY_SECONDS = int(os.getenv("RETRY_DELAY_SECONDS", 60)) # Delay before retrying a failed send
