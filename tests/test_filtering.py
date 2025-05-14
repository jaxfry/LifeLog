import os
from datetime import date
from pathlib import Path

import polars as pl
import pytest

import LifeLog.enrichment.activitywatch as aw

def test_filtering(tmp_path, monkeypatch):
    # 1) point the raw_dir to our tmp directory via environment
    monkeypatch.setenv("LIFELOG_RAW_DIR", str(tmp_path))
    monkeypatch.setenv("LIFELOG_MIN_MS", "5000")
    monkeypatch.setenv("LIFELOG_DROP_IDLE", "1")

    # 2) write a tiny sample parquet
    day = date(2025, 1, 1)
    sample = pl.DataFrame({
        "timestamp": [1, 2, 3],
        "duration": [1000, 6000, 10000],
        "app": ["Test", "IdleApp", "Work"],
        "title": ["a", "b", "c"],
    })
    path = tmp_path / f"{day}.parquet"
    sample.write_parquet(path)

    # 3) now load & filter
    filtered = aw._load_events(day)

    # Expect only the “Work” row survives (≥5 s, not idle)
    assert filtered.height == 1
    assert filtered["app"].to_list() == ["Work"]
