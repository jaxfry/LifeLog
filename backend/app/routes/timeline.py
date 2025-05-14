from fastapi import APIRouter, Query
from datetime import date
from pathlib import Path
import polars as pl

from LifeLog.config import Settings

router = APIRouter()

@router.get("/timeline/day")
def get_timeline(day: date = Query(..., description="Date in YYYY-MM-DD")):
    settings = Settings()
    path = settings.curated_dir / f"{day}.parquet"

    if not path.exists():
        return {"error": "No data for this day."}

    df = pl.read_parquet(path)
    return df.to_dicts()
