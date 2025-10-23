from pydantic_settings import BaseSettings
from typing import Optional

class Settings(BaseSettings):
    # Database Configuration
    DATABASE_URL: str = "sqlite+aiosqlite:///./lifelog.db"
    
    # Security Configuration
    SECRET_KEY: str
    
    # Application Configuration
    APP_ENV: str = "development"
    API_V1_STR: str = "/api/v1"
    
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

    class Config:
        env_file = ".env"

settings = Settings()