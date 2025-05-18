from pathlib import Path
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    raw_dir: Path = Path("LifeLog/storage/raw/activitywatch")
    curated_dir: Path = Path("LifeLog/storage/curated/timeline")
    cache_dir: Path = Path("LifeLog/tmp/gemini_cache")
    summary_dir: Path = Path("LifeLog/storage/summary/daily")
    assets_dir: Path = Path("LifeLog/assets")  # ← add this!

    model_name: str = "gemini-2.5-flash-preview-04-17"
    max_events: int = 600
    max_prompt_tokens: int = 24000

    min_duration_ms: int = 5000
    drop_idle: bool = True
    temperature: float = 0.0  # Default temperature setting
    retries:        int   = 5

    class Config:
        env_prefix = "LIFELOG_"
