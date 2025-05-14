"""
LifeLog.ingestion.activitywatch
--------------------------------
Pull one day of raw ActivityWatch events and save them as Parquet.

Schema (fixed for every output file)

    timestamp | duration | app | title | url

❯ python -m LifeLog.cli ingest-activitywatch         # yesterday
❯ python -m LifeLog.cli ingest-activitywatch --day 2025-05-12
"""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List

import polars as pl
from aw_client import ActivityWatchClient

# --------------------------------------------------------------------------- #
# Configuration
# --------------------------------------------------------------------------- #

RAW_DIR = Path("LifeLog/storage/raw/activitywatch")   # change if you want
REQUIRED_COLS = ["timestamp", "duration", "app", "title", "url"]

# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #

def _iso_bounds(day: date) -> tuple[datetime, datetime]:
    """Return UTC start & end datetimes for a calendar day."""
    start = datetime.combine(day, datetime.min.time(), tzinfo=timezone.utc)
    end   = datetime.combine(day, datetime.max.time(), tzinfo=timezone.utc)
    return start, end


def _flatten(events: List[Dict[str, Any]]) -> pl.DataFrame:
    """
    Flatten ActivityWatch event dicts to the canonical schema.
    Compatible with Polars ≤ 1.x (uses map_elements instead of struct.get_field).
    """
    if not events:
        return pl.DataFrame(schema=REQUIRED_COLS)

    df = pl.DataFrame(events).with_columns(
        [
            pl.col("data")
              .map_elements(lambda d: d.get("app"), return_dtype=pl.Utf8)
              .alias("app"),

            pl.col("data")
              .map_elements(lambda d: d.get("title"), return_dtype=pl.Utf8)
              .alias("title"),

            pl.col("data")
              .map_elements(lambda d: d.get("url"), return_dtype=pl.Utf8)
              .alias("url"),
        ]
    )

    # ensure every required column exists (pad with nulls if necessary)
    for col in REQUIRED_COLS:
        if col not in df.columns:
            df = df.with_columns(pl.lit(None).alias(col))

    return df.select(REQUIRED_COLS)

# --------------------------------------------------------------------------- #
# Public API
# --------------------------------------------------------------------------- #

def fetch_day(day: date) -> pl.DataFrame:
    """
    Pull *all* watcher buckets for `day` and return one tidy DataFrame.
    """
    start, end = _iso_bounds(day)

    client = ActivityWatchClient()                     # localhost:5600
    buckets: Dict[str, Dict[str, Any]] = client.get_buckets()  # id → meta dict

    dfs: list[pl.DataFrame] = []
    for bucket_id in buckets.keys():
        if not bucket_id.startswith("aw-watcher-"):
            continue

        events = client.get_events(bucket_id=bucket_id, start=start, end=end)
        dfs.append(_flatten(events))

    if not dfs:
        return pl.DataFrame(schema=REQUIRED_COLS)

    return pl.concat(dfs)


def ingest(day: date | None = None) -> Path:
    """
    Fetch `day` (default: yesterday), write Parquet, and return the output path.
    """
    if day is None:
        day = date.today() - timedelta(days=1)

    df = fetch_day(day)

    out_path = RAW_DIR / f"{day}.parquet"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    df.write_parquet(out_path)

    print(f"✅ Saved {len(df)} rows to {out_path}")
    return out_path

# --------------------------------------------------------------------------- #
# Stand-alone usage
# --------------------------------------------------------------------------- #

if __name__ == "__main__":
    import argparse

    p = argparse.ArgumentParser(description="Ingest ActivityWatch raw events")
    p.add_argument("--day", type=lambda s: date.fromisoformat(s),
                   help="YYYY-MM-DD (default: yesterday)")
    args = p.parse_args()

    ingest(args.day)
