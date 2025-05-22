from pathlib import Path
from typing import List, Dict, Literal, Optional
from pydantic_settings import BaseSettings, SettingsConfigDict # Import SettingsConfigDict

class Settings(BaseSettings):
    # --- Core Paths ---
    raw_dir: Path = Path("LifeLog/storage/raw/activitywatch")
    curated_dir: Path = Path("LifeLog/storage/curated/timeline")
    summary_dir: Path = Path("LifeLog/storage/summary/daily")
    assets_dir: Path = Path("LifeLog/assets")

    # --- ActivityWatch Ingestion Specific Settings ---
    local_tz: str = "America/Vancouver"
    min_duration_s: int = 5

    hostname_override: Optional[str] = None

    window_bucket_pattern: str = "aw-watcher-window_{hostname}"
    afk_bucket_pattern: str = "aw-watcher-afk_{hostname}"
    
    # **NEW: Provide sensible defaults here**
    web_bucket_map: Dict[str, str] = {
        "Arc": "aw-watcher-web-arc_{hostname}",
        # "Google Chrome": "aw-watcher-web-chrome_{hostname}",
        # "Firefox": "aw-watcher-web-firefox_{hostname}",
        # "Microsoft Edge": "aw-watcher-web-edge_{hostname}", # Or msedge
        # "Safari": "aw-watcher-web-safari_{hostname}", # If a safari extension exists & you use it
    }

    # **NEW: Provide sensible defaults here**
    browser_app_names: List[str] = [
        "Arc", 
        # "Google Chrome", 
        # "Firefox", 
        # "Microsoft Edge", # Check actual app name on your system
        # "Safari"
    ]

    web_title_priority: Literal["web", "window"] = "web"
    merge_tolerance_s: int = 5

    # --- Enrichment Settings ---
    model_name: str = "gemini-2.5-flash-preview-04-17" # If used by other parts

    # Pydantic V2 way to define model_config
    model_config = SettingsConfigDict(
        env_prefix="LIFELOG_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra='ignore' # Ignores extra fields from .env rather than erroring
    )