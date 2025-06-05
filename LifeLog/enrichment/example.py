import json
import os
from datetime import date
from pathlib import Path
from typing import Any, List

import polars as pl


def _extract_json(text: str) -> Any:
    """Extract JSON array from plain text or fenced code block."""
    text = text.strip()
    if text.startswith("```"):
        # remove opening fence and optional language
        end = text.find('\n')
        if end != -1:
            text = text[end + 1 :]
        if text.endswith("```"):
            text = text[:-3]
    text = text.strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return []


def _flatten(events: List[dict]) -> pl.DataFrame:
    """Flatten sample ActivityWatch event list into a DataFrame."""
    rows = []
    for e in events:
        data = e.get("data", {})
        rows.append({
            "timestamp": e.get("timestamp"),
            "duration": e.get("duration"),
            "app": data.get("app"),
            "title": data.get("title"),
            "url": data.get("url"),
        })
    return pl.from_dicts(rows)


def _load_events(day: date) -> pl.DataFrame:
    """Load events from a parquet file and apply simple filtering."""
    raw_dir = Path(os.getenv("LIFELOG_RAW_DIR", "LifeLog/storage/raw"))
    path = raw_dir / f"{day}.parquet"
    if not path.exists():
        return pl.DataFrame()
    df = pl.read_parquet(path)

    min_ms = int(os.getenv("LIFELOG_MIN_MS", "0"))
    if min_ms:
        df = df.filter(pl.col("duration") >= min_ms)

    if os.getenv("LIFELOG_DROP_IDLE") == "1":
        df = df.filter(~pl.col("app").str.to_lowercase().str.contains("idle"))

    return df
