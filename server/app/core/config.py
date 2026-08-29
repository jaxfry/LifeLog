from pathlib import Path

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT_ENV_FILE = Path(__file__).resolve().parents[3] / ".env"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=ROOT_ENV_FILE,
        env_file_encoding="utf-8",
        case_sensitive=False,
    )

    # App
    APP_NAME: str = "LifeLog"
    APP_VERSION: str = "5.0"
    DEBUG: bool = False
    LOG_LEVEL: str = "INFO"
    LOG_FILE: str | None = None

    # Database
    DATABASE_URL: str = "postgresql+asyncpg://lifelog:lifelogpassword@localhost:5432/lifelog_db"
    DATABASE_POOL_SIZE: int = 10
    DATABASE_MAX_OVERFLOW: int = 20
    DATABASE_ECHO: bool = False

    # Redis
    REDIS_URL: str = "redis://localhost:6379"

    # Security
    SECRET_KEY: str
    JWT_ALGORITHM: str = "HS256"
    JWT_EXPIRE_MINUTES: int = 30
    REFRESH_TOKEN_EXPIRE_DAYS: int = 90
    SOURCE_SECRET_KEY: str | None = None

    # CORS
    ALLOWED_HOSTS: str = "localhost,127.0.0.1"
    BACKEND_CORS_ORIGINS: str = "http://localhost:3000,http://localhost:5173"

    # Rate Limiting
    RATE_LIMIT_LOGIN: str = "5/minute"
    RATE_LIMIT_INGEST: str = "60/minute"
    RATE_LIMIT_DEFAULT: str = "100/minute"

    # AI
    OPENCODE_ZEN_API_KEY: str | None = None
    OPENCODE_ZEN_BASE_URL: str = "https://opencode.ai/zen/v1"
    OPENCODE_ZEN_MODEL: str = "deepseek-v4-flash-free"
    OPENROUTER_API_KEY: str | None = None
    OPENROUTER_BASE_URL: str = "https://openrouter.ai/api/v1"
    HACK_CLUB_AI_API_KEY: str | None = None
    GEMINI_API_KEY: str | None = None
    LITELLM_MODEL: str = "gemini/gemini-flash-latest"
    ASSISTANT_MODEL: str = "deepseek/deepseek-v4-flash"
    GENERAL_MODEL: str | None = None
    VISION_MODEL: str | None = None
    EXTRACTION_MODEL: str | None = None
    RESOLUTION_MODEL: str | None = None
    SUMMARY_MODEL: str | None = None
    EMBEDDING_MODEL: str = "qwen/qwen3-embedding-8b"
    EMBEDDING_DIMENSIONS: int = 768
    RERANK_MODEL: str | None = None
    TRANSCRIPTION_MODEL: str = "whisper-1"
    HACK_CLUB_AI_BASE_URL: str = "https://ai.hackclub.com/proxy/v1"
    ASSISTANT_MAX_REQUESTS: int = 12
    ASSISTANT_MAX_TOOL_CALLS: int = 8
    ASSISTANT_MAX_OUTPUT_TOKENS: int = 2_048
    ASSISTANT_MAX_TOTAL_TOKENS: int = 32_000
    AI_REQUEST_TIMEOUT_SECONDS: float = 90.0
    AI_DAILY_BUDGET_USD: float | None = None

    @field_validator(
        "ASSISTANT_MAX_REQUESTS",
        "ASSISTANT_MAX_TOOL_CALLS",
        "ASSISTANT_MAX_OUTPUT_TOKENS",
        "ASSISTANT_MAX_TOTAL_TOKENS",
        mode="before",
    )
    @classmethod
    def parse_human_integer(cls, value: object) -> object:
        """Allow readable environment values such as ``32,000``."""
        return value.replace(",", "").replace("_", "") if isinstance(value, str) else value

    # Ingestion
    MAX_PAYLOAD_SIZE_MB: int = 10
    INGEST_BATCH_SIZE: int = 500

    # Processing
    SESSION_GAP_MINUTES: int = 30
    # Safety valve only; evidence aggregation, elapsed time, and AFK boundaries
    # are the meaningful episode limits for high-frequency collectors.
    SESSION_MAX_EVENTS: int = 2000
    SESSION_MAX_MINUTES: int = 180
    SESSION_AFK_GAP_MINUTES: int = 10
    SESSIONIZER_INTERVAL_MINUTES: int = 30
    SUMMARY_CRON_HOUR: int = 1
    SUMMARY_CRON_MINUTE: int = 0

    # LLM Caching
    LLM_CACHE_ENABLED: bool = True
    LLM_CACHE_TTL_HOURS: int = 24
    LLM_CACHE_DIR: str = "storage/cache"

    # Artifact intelligence
    ARTIFACT_CHUNK_CHARS: int = 6000
    ARTIFACT_CHUNK_OVERLAP_CHARS: int = 500
    MEMORY_AUTO_ACCEPT_CONFIDENCE: float = 0.9
    MAX_ARTIFACT_SIZE_MB: int = 1024
    UPLOAD_SESSION_TTL_HOURS: int = 24
    DEFAULT_REMINDER_LEAD_MINUTES: int = 1440


settings = Settings()
