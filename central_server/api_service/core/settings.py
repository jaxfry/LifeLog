import os
import logging
from typing import List
from pathlib import Path
from pydantic_settings import BaseSettings
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

logger = logging.getLogger(__name__)

class Settings(BaseSettings):
    """Manages application-wide settings and configurations for the API service."""
    # API Configuration
    API_V1_STR: str = "/api/v1"
    PROJECT_NAME: str = "LifeLog API"
    VERSION: str = "1.0.0"
    
    # Database Configuration
    POSTGRES_HOST: str = os.getenv("POSTGRES_HOST", "localhost")
    POSTGRES_PORT: int = int(os.getenv("POSTGRES_PORT", "5432"))
    POSTGRES_USER: str = os.getenv("POSTGRES_USER", "lifelog")
    POSTGRES_PASSWORD: str = os.getenv("POSTGRES_PASSWORD", "")
    POSTGRES_DB: str = os.getenv("POSTGRES_DB", "lifelog")
    
    @property
    def SQLALCHEMY_DATABASE_URL(self) -> str:
        return f"postgresql+asyncpg://{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD}@{self.POSTGRES_HOST}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"
    
    # RabbitMQ Configuration
    RABBITMQ_HOST: str = os.getenv("RABBITMQ_HOST", "localhost")
    RABBITMQ_PORT: int = int(os.getenv("RABBITMQ_PORT", "5672"))
    RABBITMQ_USER: str = os.getenv("RABBITMQ_USER", "user")
    RABBITMQ_PASS: str = os.getenv("RABBITMQ_PASS", "")
    RABBITMQ_QUEUE: str = os.getenv("RABBITMQ_QUEUE", "lifelog_events_queue")
    
    # JWT Configuration
    SECRET_KEY: str = os.getenv("SECRET_KEY", "")
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    
    # AI Configuration
    GEMINI_API_KEY: str = os.getenv("GEMINI_API_KEY", "")
    
    # CORS Configuration
    ALLOWED_ORIGINS_STR: str = os.getenv(
        "ALLOWED_ORIGINS",
        "http://localhost:3000,http://localhost:5173,http://127.0.0.1:3000,http://127.0.0.1:5173,http://localhost:8080,http://127.0.0.1:8080",
    )

    @property
    def ALLOWED_ORIGINS(self) -> List[str]:
        """
        Returns a list of allowed origins for CORS.
        Reads from the ALLOWED_ORIGINS_STR environment variable.
        """
        if not self.ALLOWED_ORIGINS_STR:
            return []
        return [origin.strip() for origin in self.ALLOWED_ORIGINS_STR.split(",")]
    
    # Development settings
    DEBUG: bool = os.getenv("DEBUG", "False").lower() == "true"
    
    # Single user configuration (this is a single-user system)
    LIFELOG_USERNAME: str = os.getenv("LIFELOG_USERNAME", "admin")
    LIFELOG_PASSWORD: str = os.getenv("LIFELOG_PASSWORD", "admin123")
    
    class Config:
        case_sensitive = True

settings = Settings()
