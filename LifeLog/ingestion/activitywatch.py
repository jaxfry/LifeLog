# LifeLog/ingestion/activitywatch.py

from __future__ import annotations

import logging
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List

import polars as pl
from aw_client import ActivityWatchClient

from LifeLog.config import Settings

# ---------- constants -------------------------------------------------------
REQUIRED_COLS = ["timestamp", "duration", "app", "title", "url"]

# ---------- logging ---------------------------------------------------------
log = logging.getLogger(__name__)

# ---------- helpers ---------------------------------------------------------

def _iso_bounds(day: date) -> tuple[datetime, datetime]:
    """Return UTC start & end datetimes for a calendar day."""
    start = datetime.combine(day, datetime.min.time(), tzinfo=timezone.utc)
    end   = datetime.combine(day, datetime.max.time(), tzinfo=timezone.utc)
    return start, end

def _flatten(events: List[Dict[str, Any]]) -> pl.DataFrame:
    """
    Flatten AW event dicts to the canonical schema.
    Compatible with Polars ≤ 1.x via map_elements.
    """
    if not events:
        return pl.DataFrame(schema=REQUIRED_COLS)

    df = pl.DataFrame(events).with_columns([
        pl.col("data")
          .map_elements(lambda d: d.get("app"), return_dtype=pl.Utf8)
          .alias("app"),
        pl.col("data")
          .map_elements(lambda d: d.get("title"), return_dtype=pl.Utf8)
          .alias("title"),
        pl.col("data")
          .map_elements(lambda d: d.get("url"), return_dtype=pl.Utf8)
          .alias("url"),
    ])

    # pad any missing columns
    for col in REQUIRED_COLS:
        if col not in df.columns:
            df = df.with_columns(pl.lit(None).alias(col))

    return df.select(REQUIRED_COLS)

# ---------- public API ------------------------------------------------------

def fetch_day(day: date) -> pl.DataFrame:
    """
    Pull *all* AW watcher buckets for `day`, flatten, filter (Layer 1),
    and return a tidy DataFrame.
    """
    settings = Settings()
    start, end = _iso_bounds(day)
    client = ActivityWatchClient()
    buckets = client.get_buckets()  # dict[bucket_id → meta]

    dfs: List[pl.DataFrame] = []
    for bucket_id in buckets:
        if not bucket_id.startswith("aw-watcher-"):
            continue
        events = client.get_events(bucket_id=bucket_id, start=start, end=end)
        dfs.append(_flatten(events))

    df = pl.concat(dfs) if dfs else pl.DataFrame(schema=REQUIRED_COLS)

    # ---------- Layer 1 filtering --------------------------------------------
    df = df.filter(pl.col("duration") >= settings.min_duration_ms)
    if settings.drop_idle:
        df = df.filter(
            ~pl.col("app")
                .str.to_lowercase()
                .str.contains("idle|afk")
        )

    total_rows = sum(d.height for d in dfs)
    log.info(
        "🔍 Fetched & flattened rows: %d → after filter: %d",
        total_rows,
        df.height,
    )
    return df

def ingest(day: date | None = None) -> Path:
    """
    Ingest raw events for `day` (default: yesterday), write Parquet,
    and return the output path.
    """
    settings = Settings()
    raw_dir = settings.raw_dir

    if day is None:
        day = date.today() - timedelta(days=1)

    df = fetch_day(day)
    out_path = raw_dir / f"{day}.parquet"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    df.write_parquet(out_path)

    log.info("✅ Saved %d raw rows to %s", df.height, out_path)
    return out_path

# ---------- stand-alone usage ---------------------------------------------

if __name__ == "__main__":
    import argparse
    p = argparse.ArgumentParser(description="Ingest AW raw events")
    p.add_argument(
        "--day",
        type=lambda s: date.fromisoformat(s),
        help="YYYY-MM-DD (default: yesterday)"
    )
    args = p.parse_args()
    ingest(args.day)
