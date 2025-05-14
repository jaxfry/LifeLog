import json
from datetime import date
from pathlib import Path

import polars as pl
import pytest

from LifeLog.ingestion import activitywatch as aw

SAMPLE_EVENTS = [
    {  # a Chrome tab – has url
        "timestamp": "2025-05-13T09:00:00Z",
        "duration": 1.5,
        "data": {"app": "Arc", "title": "ChatGPT – Research", "url": "https://chat.openai.com"},
    },
    {  # Blender window – no url
        "timestamp": "2025-05-13T09:01:30Z",
        "duration": 4.0,
        "data": {"app": "Blender", "title": "dam.blend"},
    },
]

def test_flatten_schema_and_nulls(tmp_path: Path):
    df = aw._flatten(SAMPLE_EVENTS)
    assert df.columns == ["timestamp", "duration", "app", "title", "url"]
    assert df["url"].to_list() == ["https://chat.openai.com", None]
