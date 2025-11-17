from pydantic_settings import BaseSettings
from typing import Optional
from pathlib import Path

class Settings(BaseSettings):
    # Database Configuration
    DATABASE_URL: str = "sqlite+aiosqlite:///./lifelog.db"
    
    # Security Configuration
    # Default to a development key; MUST be overridden in production
    SECRET_KEY: str = "your-secret-key-change-in-production"
    
    # Application Configuration
    APP_ENV: str = "development"
    API_V1_STR: str = "/api/v1"
    
    # Extension Configuration
    EXTENSIONS_PATH: str = "./extensions"  # Path to development extensions (mounted)
    EXTENSIONS_STORE_PATH: str = "./extensions_store"  # Path where uploaded, verified extensions are stored (versioned)
    TRUSTED_PUBLIC_KEYS_DIR: str = "./trusted_keys"  # Directory containing trusted Ed25519 public keys (one .pub per signer)
    EXT_ACTOR_MAX_CPU_SECONDS: int = 10  # Soft CPU time limit for isolated actors
    EXT_ACTOR_MAX_MEMORY_MB: int = 512  # Address space limit for isolated actors
    
    # Authentication Configuration
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    ALGORITHM: str = "HS256"
    
    # Single-user configuration (for simplicity)
    LIFELOG_USERNAME: str = "admin"
    # Plaintext dev password (used only when LIFELOG_PASSWORD_HASH is not set)
    LIFELOG_PASSWORD: str = "admin123"
    # Optional: bcrypt hash of the admin password; if set, it will be used instead of LIFELOG_PASSWORD
    LIFELOG_PASSWORD_HASH: Optional[str] = None

    # Processing routing configuration (temporary until dynamic routing is implemented)
    PROCESSING_ROUTING_MAP: dict[str, str] = {
        "test-source": "test-processor",
        "activitywatch-source": "aw-processor",
    }

    # Embedding defaults (choose small, widely available local model for dev)
    DEFAULT_EMBEDDING_PROVIDER_SLUG: str = "local-bge"
    DEFAULT_EMBEDDING_MODEL: str = "sentence-transformers/all-MiniLM-L6-v2"
    DEFAULT_EMBEDDING_DIM: int = 1536

    # Chat defaults
    DEFAULT_CHAT_PROVIDER_SLUG: str = "openai-chat"
    DEFAULT_CHAT_MODEL: str = "gemini-2.5-flash"
    
    # LiteLLM Configuration
    LITELLM_BASE_URL: str = "http://litellm:4000"
    LITELLM_MASTER_KEY: str = "sk-1234"  # Must match litellm-config.yaml

    class Config:
        env_file = ".env"

settings = Settings()