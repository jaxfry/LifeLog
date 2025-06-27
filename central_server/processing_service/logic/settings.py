# central_server/processing_service/logic/settings.py
import os
import logging
from pathlib import Path
from dotenv import load_dotenv

# Configure logger
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Define project root for this service if needed, or rely on env vars
# For simplicity, we assume .env is in central_server/processing_service/
SERVICE_ROOT = Path(__file__).parent.parent
DOTENV_PATH = SERVICE_ROOT / '.env'

if DOTENV_PATH.exists():
    load_dotenv(DOTENV_PATH)
    logger.info(f"Loaded .env file from {DOTENV_PATH}")
else:
    logger.info(f".env file not found at {DOTENV_PATH}. Relying on environment variables.")

class Settings:
    # --- Gemini API ---
    GEMINI_API_KEY: str = os.getenv("GEMINI_API_KEY", "YOUR_API_KEY_HERE")

    # --- Caching ---
    # Cache dir relative to this service's root
    CACHE_DIR_NAME: str = "cache"
    # Construct absolute path for CACHE_DIR
    CACHE_DIR: Path = SERVICE_ROOT / CACHE_DIR_NAME
    ENABLE_LLM_CACHE: bool = os.getenv("ENABLE_LLM_CACHE", "True").lower() == "true"
    CACHE_TTL_HOURS: int = int(os.getenv("CACHE_TTL_HOURS", "24"))

    # --- Timezone ---
    LOCAL_TZ: str = os.getenv("LOCAL_TZ", "America/Vancouver")

    # --- Timeline Enrichment ---
    ENRICHMENT_MODEL_NAME: str = os.getenv("ENRICHMENT_MODEL_NAME", "gemini-2.5-flash") # Changed to 1.5 flash
    ENRICHMENT_PROMPT_TRUNCATE_LIMIT: int = int(os.getenv("ENRICHMENT_PROMPT_TRUNCATE_LIMIT", "40"))
    ENRICHMENT_MIN_DURATION_S: int = int(os.getenv("ENRICHMENT_MIN_DURATION_S", "0")) # Allow all durations
    AFK_APP_NAME: str = os.getenv("AFK_APP_NAME", "afk") # Ensure this matches event data if AFK events are sent

    # --- Daily Processing Time ---
    DAILY_PROCESSING_TIME: str = os.getenv("DAILY_PROCESSING_TIME", "03:00")

    # --- Processing Optimization ---
    # Minimum number of events to warrant LLM processing for a full day
    MIN_EVENTS_FOR_LLM_PROCESSING: int = int(os.getenv("MIN_EVENTS_FOR_LLM_PROCESSING", "20"))

    # Chunk size for LLM processing - DEPRECATED. We will process the whole day at once.
    # LLM_PROCESSING_CHUNK_SIZE: int = int(os.getenv("LLM_PROCESSING_CHUNK_SIZE", "100"))

    # --- Gap Filling ---
    # Minimum gap duration (in seconds) to create an "Idle / Away" entry
    # 15 minutes is a good starting point.
    MIN_GAP_FILL_DURATION_S: int = int(os.getenv("MIN_GAP_FILL_DURATION_S", "900"))

    # --- Project Resolution ---
    PROJECT_EMBEDDING_SIZE: int = int(os.getenv("PROJECT_EMBEDDING_SIZE", "128"))
    PROJECT_SIMILARITY_THRESHOLD: float = float(os.getenv("PROJECT_SIMILARITY_THRESHOLD", "0.85")) # Increased for higher confidence

    # DEPRECATED: This should be fetched from the database, not hard-coded.
    # It can be kept as a bootstrap list for a completely empty system if desired.
    # KNOWN_PROJECT_NAMES: list[str] = [
    #     "LifeLog",
    #     "LifeLog Core", 
    #     "LifeLog Development",
    #     "LifeLog Backend",
    #     "LifeLog Frontend",
    #     "Personal Project",
    #     "Work Project",
    #     "Research",
    #     "Study",
    #     "Learning"
    # ]

    # --- PostgreSQL Database ---
    POSTGRES_HOST: str = os.getenv("POSTGRES_HOST", "localhost")
    POSTGRES_PORT: int = int(os.getenv("POSTGRES_PORT", "5432"))
    POSTGRES_USER: str = os.getenv("POSTGRES_USER", "lifelog_user")
    POSTGRES_PASSWORD: str = os.getenv("POSTGRES_PASSWORD", "lifelog_pass")
    POSTGRES_DB: str = os.getenv("POSTGRES_DB", "lifelog_db")
    
    #SQLALCHEMY_DATABASE_URL: str = f"postgresql://{POSTGRES_USER}:{POSTGRES_PASSWORD}@{POSTGRES_HOST}:{POSTGRES_PORT}/{POSTGRES_DB}"
    # Example for async: SQLALCHEMY_DATABASE_URL_ASYNC: str = f"postgresql+asyncpg://{POSTGRES_USER}:{POSTGRES_PASSWORD}@{POSTGRES_HOST}:{POSTGRES_PORT}/{POSTGRES_DB}"
    
    @property
    def SQLALCHEMY_DATABASE_URL(self) -> str:
        return f"postgresql://{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD}@{self.POSTGRES_HOST}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"

    @property
    def SQLALCHEMY_DATABASE_URL_ASYNC(self) -> str: # If async is needed later
        return f"postgresql+asyncpg://{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD}@{self.POSTGRES_HOST}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"

    def __init__(self):
        if self.GEMINI_API_KEY == "YOUR_API_KEY_HERE":
            print("Warning: GEMINI_API_KEY is not set in environment. LLM calls will likely fail.")
        
        # Ensure cache directory exists if enabled
        if self.ENABLE_LLM_CACHE:
            self.CACHE_DIR.mkdir(parents=True, exist_ok=True)
            print(f"LLM Caching is ON. Cache directory: {self.CACHE_DIR}")
        else:
            print("LLM Caching is OFF.")

settings = Settings()

# Example of how to use:
if __name__ == "__main__":
    print(f"Gemini API Key: {'*' * 5}{settings.GEMINI_API_KEY[-5:]}" if settings.GEMINI_API_KEY != "YOUR_API_KEY_HERE" else "Not Set")
    print(f"Local TZ: {settings.LOCAL_TZ}")
    print(f"Cache Enabled: {settings.ENABLE_LLM_CACHE}")
    print(f"Cache Dir: {settings.CACHE_DIR}")
    print(f"Database URL: {settings.SQLALCHEMY_DATABASE_URL}")