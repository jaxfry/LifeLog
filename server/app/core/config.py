
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
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
    HACK_CLUB_AI_API_KEY: str | None = None
    GEMINI_API_KEY: str | None = None
    LITELLM_MODEL: str = "gemini/gemini-flash-latest"
    TRANSCRIPTION_MODEL: str = "whisper-1"
    HACK_CLUB_AI_BASE_URL: str = "https://ai.hackclub.com/"

    # Ingestion
    MAX_PAYLOAD_SIZE_MB: int = 10
    INGEST_BATCH_SIZE: int = 500

    # Processing
    SESSION_GAP_MINUTES: int = 30
    SESSION_MAX_EVENTS: int = 300
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
    DEFAULT_REMINDER_LEAD_MINUTES: int = 1440


settings = Settings()
