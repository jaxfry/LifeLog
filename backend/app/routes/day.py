from fastapi import APIRouter, Query
from datetime import date
from pathlib import Path
import json
import polars as pl

from LifeLog.config import Settings

router = APIRouter()

@router.get("/api/day/{day}")
def get_day_data(day: date):
    settings = Settings()
    summary_path = settings.summary_dir / f"{day}.json"
    timeline_path = settings.curated_dir / f"{day}.parquet"

    summary_data = {}
    if summary_path.exists():
        summary_data = json.loads(summary_path.read_text())

    entries_data = []
    if timeline_path.exists():
        df = pl.read_parquet(timeline_path)
        entries_data = df.to_dicts()

    return {
        "summary": summary_data,
        "entries": entries_data,
    }
