from fastapi import APIRouter
from fastapi.responses import JSONResponse
from datetime import date
from pathlib import Path
import json
import polars as pl

from LifeLog.config import Settings
from LifeLog.models import TimelineEntry

router = APIRouter()

@router.get("/api/day/{day}")
def get_day_data(day: date):
    settings = Settings()
    summary_path = settings.summary_dir / f"{day}.json"
    timeline_path = settings.curated_dir / f"{day}.parquet"

    # Load the daily summary
    summary_data = {}
    if summary_path.exists():
        summary_data = json.loads(summary_path.read_text())

    # Load & serialize timeline entries with proper "Z" suffix
    entries: list[dict] = []
    if timeline_path.exists():
        df = pl.read_parquet(timeline_path)
        for row in df.to_dicts():
            entry = TimelineEntry(**row)
            # model_dump_json() -> JSON string with "Z"; json.loads -> dict
            entries.append(json.loads(entry.model_dump_json()))

    # Return everything as JSONResponse so timestamps remain intact
    return JSONResponse(content={
        "summary": summary_data,
        "entries": entries,
    })
