# LifeLog/ingestion/activitywatch.py
from __future__ import annotations

import argparse
import logging
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Sequence

import polars as pl
from aw_client import ActivityWatchClient
from zoneinfo import ZoneInfo  # stdlib ≥ 3.9

from LifeLog.config import Settings

# ────────────────────────────────────────────────────────────────────────────
# Logging
# ────────────────────────────────────────────────────────────────────────────
log = logging.getLogger(__name__)
log.addHandler(logging.NullHandler())

# ────────────────────────────────────────────────────────────────────────────
# Constants / schema
# ────────────────────────────────────────────────────────────────────────────
REQUIRED_COLS = ["timestamp", "duration", "app", "title", "url"]
EMPTY_SCHEMA = [(col, pl.Null) for col in REQUIRED_COLS]  # for empty DataFrames


# ────────────────────────────────────────────────────────────────────────────
# Helpers
# ────────────────────────────────────────────────────────────────────────────
def _iso_bounds(day: date, *, tz: timezone | None = None) -> tuple[datetime, datetime]:
    """
    Return (UTC_start, UTC_end) for a local calendar day.

    The end-instant is the *next* midnight (half-open interval [start, end) ),
    which is easier to reason about than 23:59:59.999999.
    """
    if tz is None:  # platform-independent local TZ
        tz = datetime.now().astimezone().tzinfo or ZoneInfo("UTC")

    start_local = datetime.combine(day, time.min, tzinfo=tz)
    end_local   = start_local + timedelta(days=1)          # next midnight
    return start_local.astimezone(timezone.utc), end_local.astimezone(timezone.utc)


def _flatten(events: Sequence[dict[str, Any]]) -> pl.DataFrame:
    if not events:
        return pl.DataFrame(schema=EMPTY_SCHEMA)

    df = pl.DataFrame(events)

    # safe key-lookup (returns None when the key is absent)
    def _get(key: str) -> pl.Expr:
        return (
            pl.col("data")
            .map_elements(lambda d: d.get(key), return_dtype=pl.Utf8)
            .alias(key)
        )

    df = (
        df.with_columns(
            _get("app"),
            _get("title"),
            _get("url"),
        )
        .drop("data")            # no longer needed
    )

    # make sure every required column exists & is ordered
    for col in REQUIRED_COLS:
        if col not in df.columns:
            df = df.with_columns(pl.lit(None).alias(col))

    return df.select(REQUIRED_COLS)


# ────────────────────────────────────────────────────────────────────────────
# Public API
# ────────────────────────────────────────────────────────────────────────────
def fetch_day(day: date, *, client: ActivityWatchClient | None = None) -> pl.DataFrame:
    """
    Pull all AW watcher buckets for `day`, flatten, filter, and return a DF.
    """
    settings = Settings()
    start_utc, end_utc = _iso_bounds(day)

    client = client or ActivityWatchClient()
    bucket_meta = client.get_buckets()  # id ➜ meta

    dfs: list[pl.DataFrame] = []
    for bucket_id in bucket_meta:
        if not bucket_id.startswith("aw-watcher-"):
            continue

        events = client.get_events(bucket_id=bucket_id, start=start_utc, end=end_utc)
        dfs.append(_flatten(events))

    if not dfs:
        log.warning("No ActivityWatch events found for %s", day)
        return pl.DataFrame(schema=EMPTY_SCHEMA)

    df_all   = pl.concat(dfs, how="vertical")
    raw_rows = df_all.height

    # ───── Layer-1 filtering ───────────────────────────────────────────────
    if settings.min_duration_ms is not None:
        df_all = df_all.filter(
            pl.col("duration") >= settings.min_duration_ms / 1_000  # AW uses seconds
        )

    if settings.drop_idle:
        df_all = df_all.filter(~pl.col("app").str.to_lowercase().str.contains("idle|afk"))

    log.info("🔍 Raw rows: %d  →  after filter: %d", raw_rows, df_all.height)
    return df_all


def ingest(day: date | None = None) -> Path:
    """
    Ingest raw events for `day` (default: *yesterday*), write them to Parquet,
    and return the output path.
    """
    settings = Settings()
    day = day or (date.today() - timedelta(days=1))

    df = fetch_day(day)
    out_path = settings.raw_dir / f"{day}.parquet"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    df.write_parquet(out_path)

    log.info("✅ Saved %d rows to %s", df.height, out_path)
    return out_path


# ────────────────────────────────────────────────────────────────────────────
# CLI entry-point
# ────────────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Ingest ActivityWatch raw events")
    parser.add_argument("--day", type=date.fromisoformat, help="YYYY-MM-DD (default: yesterday)")
    args = parser.parse_args()

    ingest(args.day)