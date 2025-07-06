import os
import logging
from pathlib import Path
from dotenv import load_dotenv

# Configure logger
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Define project root and .env path
SERVICE_ROOT = Path(__file__).parent.parent
DOTENV_PATH = SERVICE_ROOT / '.env'

if DOTENV_PATH.exists():
    load_dotenv(DOTENV_PATH)
    logger.info(f"Loaded .env file from {DOTENV_PATH}")
else:
    logger.info(f".env file not found at {DOTENV_PATH}. Relying on environment variables.")

class Settings:
    """Manages application-wide settings and configurations for the processing service."""
    
    # --- Gemini API ---
    GEMINI_API_KEY: str = os.getenv("GEMINI_API_KEY", "")

    # --- Caching ---
    CACHE_DIR: Path = SERVICE_ROOT / "cache"
    ENABLE_LLM_CACHE: bool = os.getenv("ENABLE_LLM_CACHE", "True").lower() == "true"
    CACHE_TTL_HOURS: int = int(os.getenv("CACHE_TTL_HOURS", "24"))

    # --- Timezone ---
    LOCAL_TZ: str = os.getenv("LOCAL_TZ", "America/Vancouver")

    # --- Timeline Enrichment ---
    ENRICHMENT_MODEL_NAME: str = os.getenv("ENRICHMENT_MODEL_NAME", "gemini-2.5-flash")
    ENRICHMENT_PROMPT_TRUNCATE_LIMIT: int = int(os.getenv("ENRICHMENT_PROMPT_TRUNCATE_LIMIT", "40"))
    ENRICHMENT_MIN_DURATION_S: int = int(os.getenv("ENRICHMENT_MIN_DURATION_S", "0"))
    AFK_APP_NAME: str = os.getenv("AFK_APP_NAME", "afk")

    # --- Daily Processing Time ---
    DAILY_PROCESSING_TIME: str = os.getenv("DAILY_PROCESSING_TIME", "03:00")

    # --- Processing Optimization ---
    MIN_EVENTS_FOR_LLM_PROCESSING: int = int(os.getenv("MIN_EVENTS_FOR_LLM_PROCESSING", "20"))

    # --- Gap Filling ---
    MIN_GAP_FILL_DURATION_S: int = int(os.getenv("MIN_GAP_FILL_DURATION_S", "900"))

    # --- Project Resolution ---
    PROJECT_EMBEDDING_SIZE: int = int(os.getenv("PROJECT_EMBEDDING_SIZE", "128"))
    PROJECT_SIMILARITY_THRESHOLD: float = float(os.getenv("PROJECT_SIMILARITY_THRESHOLD", "0.85"))

    # --- PostgreSQL Database ---
    POSTGRES_HOST: str = os.getenv("POSTGRES_HOST", "localhost")
    POSTGRES_PORT: int = int(os.getenv("POSTGRES_PORT", "5432"))
    POSTGRES_USER: str = os.getenv("POSTGRES_USER", "lifelog_user")
    POSTGRES_PASSWORD: str = os.getenv("POSTGRES_PASSWORD", "")
    POSTGRES_DB: str = os.getenv("POSTGRES_DB", "lifelog_db")

    @property
    def SQLALCHEMY_DATABASE_URL(self) -> str:
        return f"postgresql://{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD}@{self.POSTGRES_HOST}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"

    @property
    def SQLALCHEMY_DATABASE_URL_ASYNC(self) -> str:
        return f"postgresql+asyncpg://{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD}@{self.POSTGRES_HOST}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"

    def __init__(self):
        if self.GEMINI_API_KEY == "YOUR_API_KEY_HERE":
            logger.warning("GEMINI_API_KEY is not set in environment. LLM calls will likely fail.")
        
        if self.ENABLE_LLM_CACHE:
            self.CACHE_DIR.mkdir(parents=True, exist_ok=True)
            logger.info(f"LLM Caching is ON. Cache directory: {self.CACHE_DIR}")
        else:
            logger.info("LLM Caching is OFF.")

settings = Settings()

if __name__ == "__main__":
    logger.info(f"Gemini API Key: {'*' * 5}{settings.GEMINI_API_KEY[-5:]}" if settings.GEMINI_API_KEY != "YOUR_API_KEY_HERE" else "Not Set")
    logger.info(f"Local TZ: {settings.LOCAL_TZ}")
    logger.info(f"Cache Enabled: {settings.ENABLE_LLM_CACHE}")
    logger.info(f"Cache Dir: {settings.CACHE_DIR}")
    logger.info(f"Database URL: {settings.SQLALCHEMY_DATABASE_URL}")
