from fastapi import APIRouter, Query
from datetime import date
from pathlib import Path
import json

from LifeLog.config import Settings

router = APIRouter()

@router.get("/summary/day")
def get_summary(day: date = Query(..., description="Date in YYYY-MM-DD")):
    settings = Settings()
    path = settings.summary_dir / f"{day}.json"

    if not path.exists():
        return {"error": "No summary available for this date."}

    return json.loads(path.read_text())
