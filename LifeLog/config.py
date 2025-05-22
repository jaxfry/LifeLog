from pathlib import Path
from typing import List, Dict, Literal, Optional # Add Dict
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    # --- Core Paths ---
    raw_dir: Path = Path("LifeLog/storage/raw/activitywatch")
    curated_dir: Path = Path("LifeLog/storage/curated/timeline") # For enriched output
    summary_dir: Path = Path("LifeLog/storage/summary/daily")
    assets_dir: Path = Path("LifeLog/assets")
    enriched_cache_dir: Path = Path("LifeLog/storage/cache/enrichment_llm_responses") # Cache for LLM JSON

    # --- ActivityWatch Ingestion Specific Settings (from ingest script) ---
    afk_app_name_override: str = "SystemActivity"
    min_duration_s_post_afk: Optional[int] = 1
    local_tz: str = "America/Vancouver" # Example, user should set
    min_duration_s: int = 5
    hostname_override: Optional[str] = None
    window_bucket_pattern: str = "aw-watcher-window_{hostname}"
    afk_bucket_pattern: str = "aw-watcher-afk_{hostname}"
    web_bucket_map: Dict[str, str] = {"Arc": "aw-watcher-web-arc_{hostname}"}
    browser_app_names: List[str] = ["Arc"]
    web_title_priority: Literal["web", "window"] = "web"
    merge_tolerance_s: int = 5

    # --- Enrichment (Timeline Generation) Settings ---
    model_name: str = "gemini-2.5-flash-preview-05-20"
    enrichment_max_events: int = 300 # Max raw events to include in a single LLM prompt
    enrichment_prompt_truncate_limit: int = 120 # Max char length for title/url in prompt
    enrichment_min_duration_s: int = 10 # Min duration (seconds) of raw events to consider for enrichment
    
    enrichment_force_llm: bool = False # If true, ignore cached LLM responses and re-query
    enrichment_force_processing_all: bool = False # If true, re-run full enrichment even if output file exists
    
    enrichment_llm_temperature: float = 0.3 # LLM Temperature for more deterministic output
    enrichment_llm_retries: int = 3
    enrichment_llm_retry_delay_base_s: int = 2 # Base for exponential backoff (2s, 4s, 8s)

    project_aliases: Dict[str, str] = { # For ProjectResolver
        "lifelog": "LifeLog Development",
        "ll": "LifeLog Development",
        # Add user's aliases from old script or new ones
    }
    enrichment_enable_post_merge: bool = True # Enable the secondary merging step after LLM
    enrichment_merge_gap_s: int = 90 # Max gap in seconds to merge post-LLM entries

    model_config = SettingsConfigDict(
        env_prefix="LIFELOG_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra='ignore'
    )