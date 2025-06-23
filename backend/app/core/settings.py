# backend/app/core/settings.py

import os
from pathlib import Path
from typing import List, Dict
from pydantic_settings import BaseSettings, SettingsConfigDict
import socket

# Define project root to build paths consistently
PROJECT_ROOT = Path(__file__).parent.parent.parent.parent

class Settings(BaseSettings):
    # THIS IS THE LINE TO CHANGE/ADD
    model_config = SettingsConfigDict(
        env_file=PROJECT_ROOT / '.env', 
        env_file_encoding='utf-8',
        extra='ignore'  # <-- ADD THIS LINE
    )

    # --- Gemini API ---
    GEMINI_API_KEY: str = "YOUR_API_KEY_HERE"

    # --- File Paths ---
    DATA_DIR: Path = PROJECT_ROOT / "backend/app/data"
    DB_FILE: Path = DATA_DIR / "lifelog.db"
    SCHEMA_FILE: Path = DATA_DIR / "schema.sql"
    BACKUP_DIR: Path = DATA_DIR / "backups"
    
    # --- Caching (Testing Mode Only) ---
    ENABLE_LLM_CACHE: bool = True  # Set to True for testing/development
    CACHE_DIR: Path = DATA_DIR / "cache"
    CACHE_TTL_HOURS: int = 24  # Cache expires after 24 hours

    # --- Timezone ---
    LOCAL_TZ: str = "America/Vancouver"

    # --- ActivityWatch Ingestion ---
    AW_HOSTNAME: str = socket.gethostname()  # <-- This will be the computer's host name
    AW_WINDOW_BUCKET: str = f"aw-watcher-window_{AW_HOSTNAME}"
    AW_AFK_BUCKET: str = f"aw-watcher-afk_{AW_HOSTNAME}"
    AW_WEB_BUCKET: str = f"aw-watcher-web-arc_{AW_HOSTNAME}"
    AW_MERGE_TOLERANCE_S: int = 5
    AW_MIN_DURATION_S: int = 2 # Filter out very short, noisy events early

    # --- Timeline Enrichment ---
    ENRICHMENT_MODEL_NAME: str = "gemini-2.5-flash"
    ENRICHMENT_CHUNK_MINUTES: int = 15 # Bin events into 15-minute chunks first
    ENRICHMENT_TOKEN_LIMIT: int = 4096 # Max tokens for the prompt context

    ENRICHMENT_PROMPT_TRUNCATE_LIMIT: int = 40
    ENRICHMENT_MIN_DURATION_S: int = 5
    AFK_APP_NAME: str = "afk"
 
    # --- Project Resolution ---
    PROJECT_EMBEDDING_SIZE: int = 128
    PROJECT_SIMILARITY_THRESHOLD: float = 0.75 # Required similarity to auto-assign project
 
# Instantiate a single settings object for the whole app
settings = Settings()