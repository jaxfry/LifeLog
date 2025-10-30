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
    EXTENSIONS_PATH: str = "./extensions"  # Path to extensions directory
    
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
    }

    # Embedding defaults
    DEFAULT_EMBEDDING_PROVIDER_SLUG: str = "local-bge"
    DEFAULT_EMBEDDING_MODEL: str = "BAAI/bge-large-en-v1.5"
    DEFAULT_EMBEDDING_DIM: int = 1536

    # Chat defaults
    DEFAULT_CHAT_PROVIDER_SLUG: str = "openai-chat"
    DEFAULT_CHAT_MODEL: str = "gpt-4-turbo"

    class Config:
        env_file = ".env"

settings = Settings()