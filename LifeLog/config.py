from pathlib import Path
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    raw_dir: Path = Path("LifeLog/storage/raw/activitywatch")
    curated_dir: Path = Path("LifeLog/storage/curated/timeline")
    cache_dir: Path = Path("LifeLog/tmp/gemini_cache")

    model_name: str = "gemini-2.5-flash-preview-04-17"
    max_events: int = 600

    min_duration_ms: int = 5000
    drop_idle: bool = True

    class Config:
        env_prefix = "LIFELOG_"
