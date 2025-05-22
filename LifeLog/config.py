# LifeLog/config.py

from pathlib import Path
from typing import List, Dict, Literal, Optional
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    # --- Core Paths ---
    raw_dir: Path = Path("LifeLog/storage/raw/activitywatch")
    curated_dir: Path = Path("LifeLog/storage/curated/timeline")
    summary_dir: Path = Path("LifeLog/storage/summary/daily")
    assets_dir: Path = Path("LifeLog/assets")
    enriched_cache_dir: Path = Path("LifeLog/storage/cache/enrichment_llm_responses")
    # NEW: Cache for summary LLM responses
    summary_llm_cache_dir: Path = Path("LifeLog/storage/cache/summary_llm_responses")


    # --- ActivityWatch Ingestion Specific Settings ---
    afk_app_name_override: str = "SystemActivity"
    min_duration_s_post_afk: Optional[int] = 1
    local_tz: str = "America/Vancouver" 
    min_duration_s: int = 5
    hostname_override: Optional[str] = None
    window_bucket_pattern: str = "aw-watcher-window_{hostname}"
    afk_bucket_pattern: str = "aw-watcher-afk_{hostname}"
    web_bucket_map: Dict[str, str] = {"Arc": "aw-watcher-web-arc_{hostname}"}
    browser_app_names: List[str] = ["Arc"]
    web_title_priority: Literal["web", "window"] = "web"
    merge_tolerance_s: int = 5

    # --- Enrichment (Timeline Generation) Settings ---
    model_name: str = "gemini-1.5-flash-latest" # Default model for enrichment, can be overridden for summary
    enrichment_max_events: int = 300 
    enrichment_prompt_truncate_limit: int = 120 
    enrichment_min_duration_s: int = 10 
    enrichment_force_llm: bool = False 
    enrichment_force_processing_all: bool = False 
    enrichment_llm_temperature: float = 0.3 
    enrichment_llm_retries: int = 3
    enrichment_llm_retry_delay_base_s: int = 2 
    project_aliases: Dict[str, str] = {
        "lifelog": "LifeLog Development",
        "ll": "LifeLog Development",
    }
    enrichment_enable_post_merge: bool = True 
    enrichment_merge_gap_s: int = 90 

    # --- Daily Summary Generation Settings (NEW) ---
    summary_model_name: Optional[str] = None # If None, defaults to main model_name
    summary_llm_temperature: Optional[float] = None # If None, defaults to enrichment_llm_temperature
    summary_llm_retries: Optional[int] = None # If None, defaults to enrichment_llm_retries
    summary_llm_retry_delay_base_s: Optional[int] = None # If None, defaults to enrichment_llm_retry_delay_base_s
    summary_pregroup_gap_s: int = 300 # 5 minutes for pre-grouping timeline entries
    summary_prompt_notes_truncate_limit: int = 80 # Truncate notes in prompt for summary
    summary_force_llm: bool = False # Separate force flag for summary LLM call
    summary_force_processing_all: bool = False # If true, re-run summary even if output file exists (overlaps with CLI --force)


    model_config = SettingsConfigDict(
        env_prefix="LIFELOG_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra='ignore'
    )