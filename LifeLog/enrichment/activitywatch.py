from __future__ import annotations

import json
import os
import re
import time
from datetime import date, timedelta
from pathlib import Path
from typing import List

import polars as pl
import sys
from pathlib import Path as _Path
# Allow running as script: add project root to PYTHONPATH
sys.path.insert(0, str(_Path(__file__).resolve().parents[2]))

from google import genai
# Retry on any exception (since google-genai has no specific GoogleAPIError class)
from LifeLog.models import TimelineEntry

# --------------------------------------------------------------------------- #
# Configuration & filtering thresholds
# --------------------------------------------------------------------------- #
RAW_DIR = Path("LifeLog/storage/raw/activitywatch")
CURATED_DIR = Path("LifeLog/storage/curated/timeline")
CACHE_DIR = Path("LifeLog/tmp/gemini_cache")
MODEL_NAME = "gemini-2.0-flash"
MAX_EVENTS = 600
MIN_DURATION_MS = int(os.getenv("LIFELOG_MIN_MS", 5000))  # milliseconds threshold
DROP_IDLE = os.getenv("LIFELOG_DROP_IDLE", "1") == "1"

# --------------------------------------------------------------------------- #
# Data loading & pre-AI filtering
# --------------------------------------------------------------------------- #

def _load_events(day: date) -> pl.DataFrame:
    """
    Load raw events for a day, apply pre-AI filtering:
    - Remove events shorter than MIN_DURATION_MS
    - Optionally drop idle/AFK events
    """
    p = RAW_DIR / f"{day}.parquet"
    if not p.exists():
        raise FileNotFoundError(p)

    df = pl.read_parquet(p)

    # Filter out very short events
    df = df.filter(pl.col("duration") >= MIN_DURATION_MS)

    # Optionally drop idle/AFK
    if DROP_IDLE and "app" in df.columns:
        df = df.filter(~pl.col("app")
                        .str.to_lowercase()
                        .str.contains(r"idle|afk", literal=False))

    return df.sort("timestamp")

# --------------------------------------------------------------------------- #
# Markdown conversion
# --------------------------------------------------------------------------- #

def _events_to_markdown(df: pl.DataFrame) -> str:
    """
    Convert a DataFrame slice to a markdown table for prompting.
    """
    show = (
        df.select(
            pl.col("timestamp").dt.strftime("%H:%M:%S").alias("time"),
            "duration",
            "app",
            "title",
        )
        .head(MAX_EVENTS)
        .to_pandas()
        .to_markdown(index=False)
    )
    return show

# --------------------------------------------------------------------------- #
# JSON extraction
# --------------------------------------------------------------------------- #

def _extract_json(txt: str):
    txt = txt.strip()
    if not txt:
        raise ValueError("Input text is empty or invalid")

    try:
        return json.loads(txt)
    except json.JSONDecodeError as e:
        print(f"⚠️ Initial JSON decode error: {e}")
        match = re.search(r"\[.*?\]", txt, re.DOTALL)
        if not match:
            raise ValueError("No JSON array found in Gemini response")
        json_str = match.group(0)
        try:
            return json.loads(json_str)
        except json.JSONDecodeError as e:
            print(f"⚠️ Regex-extracted JSON decode error: {e}")
            print(f"Extracted JSON string: {json_str[:500]}... (truncated)")
            raise ValueError("Failed to parse JSON from extracted string") from e

# --------------------------------------------------------------------------- #
# Prompt template
# --------------------------------------------------------------------------- #

def _prompt(markdown_table: str) -> str:
    return f"""
You are a personal life‑logging assistant.
Group the raw computer‑usage events below into higher‑level timeline entries.
Respond **ONLY with JSON** that exactly matches this schema:

[
  {{
    "start": "YYYY-MM-DDTHH:MM:SSZ",
    "end":   "YYYY-MM-DDTHH:MM:SSZ",
    "activity": "short verb phrase",
    "project": "optional project/course name",
    "location": "optional place name",
    "notes": "1–2 sentence summary"
  }}
]

Rules:
* Merge consecutive events that belong to the same activity/project.
* If unsure of a field, return null.
* Use window titles & URLs for context (e.g. GitHub repo → project name).
* Keep entries chronological.

Raw events (max {MAX_EVENTS} shown):

{markdown_table}
"""

# --------------------------------------------------------------------------- #
# Safe generation with retry
# --------------------------------------------------------------------------- #

def _safe_generate(client, chunk: str, retries=5) -> str:
    for attempt in range(1, retries + 1):
        try:
            resp = client.models.generate_content(
                model=MODEL_NAME,
                contents=_prompt(chunk),
            )
            return resp.candidates[0].content.parts[0].text
        except Exception as e:
            if attempt == retries:
                raise
            print(f"⚠️ Gemini error: {e} — retrying in {2 ** attempt}s...")
            time.sleep(2 ** attempt)

# --------------------------------------------------------------------------- #
# Enrichment entry point
# --------------------------------------------------------------------------- #

def enrich(day: date, force: bool = False) -> Path:
    # Load raw and filtered events to measure filter impact
    raw_df = pl.read_parquet(RAW_DIR / f"{day}.parquet")
    raw_count = raw_df.height
    df = _load_events(day)
    filtered_count = df.height
    # Report shrink stats
    if raw_count > 0:
        pct = filtered_count / raw_count * 100
        print(f"🔍 Raw events: {raw_count}, After filter: {filtered_count} ({pct:.1f}% kept)")
    else:
        print("🔍 No raw events to process today.")
    md = _events_to_markdown(df)

    cache_file = CACHE_DIR / f"{day}.txt"
    CACHE_DIR.mkdir(parents=True, exist_ok=True)

    if cache_file.exists() and not force:
        print("⚠️ Using cached Gemini response.")
        raw_response = cache_file.read_text()
    else:
        api_key = os.getenv("GEMINI_API_KEY")
        if not api_key:
            raise RuntimeError("Set GEMINI_API_KEY env variable with your Google AI key.")

        client = genai.Client(api_key=api_key)

        markdown_chunks = [md[i:i+12000] for i in range(0, len(md), 12000)]
        responses = []

        for i, chunk in enumerate(markdown_chunks):
            print(f"🧠 Prompt chunk {i+1}/{len(markdown_chunks)}")
            text = _safe_generate(client, chunk)
            responses.append(text)

        raw_response = "\n".join(responses)
        cache_file.write_text(raw_response)
        print(f"💾 Saved Gemini response to cache: {cache_file}")

    try:
        timeline_data = _extract_json(raw_response)
    except Exception as e:
        print("Raw Gemini output:\n", raw_response[:3000])
        raise RuntimeError("Failed to extract valid JSON") from e

    entries: List[TimelineEntry] = [TimelineEntry(**obj) for obj in timeline_data]

    CURATED_DIR.mkdir(parents=True, exist_ok=True)
    out_p = CURATED_DIR / f"{day}.parquet"
    pl.DataFrame([e.model_dump() for e in entries]).write_parquet(out_p)

    print(f"✅ Enriched {len(entries)} entries → {out_p}")
    return out_p

# --------------------------------------------------------------------------- #
# CLI runner
# --------------------------------------------------------------------------- #

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Enrich ActivityWatch day with Gemini")
    parser.add_argument("--day", type=lambda s: date.fromisoformat(s), help="YYYY-MM-DD (default: yesterday)")
    parser.add_argument("--force", action="store_true", help="Ignore cached responses and re-prompt Gemini")
    args = parser.parse_args()
    target_day = args.day or (date.today() - timedelta(days=1))
    enrich(target_day, force=args.force)
