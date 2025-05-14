# LifeLog/enrichment/activitywatch.py

from __future__ import annotations

# ── Monkey-patch HTTPX to allow unicode & bytes in header values ────────────
try:
    import httpx._models as _httpx_models

    def _normalize_header_value(value, encoding: str | None):
        # If it's already bytes, leave it as is
        if isinstance(value, (bytes, bytearray)):
            return bytes(value)
        # Otherwise it's a str: try ASCII, fall back to UTF-8
        try:
            return value.encode(encoding or "ascii")
        except UnicodeEncodeError:
            return value.encode("utf-8", errors="ignore")

    _httpx_models._normalize_header_value = _normalize_header_value
except ImportError:
    pass

import json
import logging
import os
import re
import time
from datetime import date, timedelta
from pathlib import Path
from typing import List

import polars as pl
from google import genai

from LifeLog.config import Settings
from LifeLog.models import TimelineEntry

# ---------- logging ---------------------------------------------------------
log = logging.getLogger(__name__)

# ---------- JSON Extraction ------------------------------------------------

def _extract_json(txt: str) -> list[dict]:
    """
    Extract & concatenate all JSON arrays from Gemini’s response,
    including fenced ```json``` blocks.
    """
    txt = txt.strip()
    arrays: List[dict] = []

    # fenced blocks
    for block in re.findall(r"```json\s*(\[.*?\])\s*```", txt, re.DOTALL):
        arrays.extend(json.loads(block))

    # naked arrays fallback
    if not arrays:
        for block in re.findall(r"\[.*?\]", txt, re.DOTALL):
            try:
                arrays.extend(json.loads(block))
            except json.JSONDecodeError:
                continue

    if not arrays:
        raise ValueError("No JSON arrays found in Gemini response")

    return arrays

# ---------- helpers ---------------------------------------------------------

def _load_events(day: date) -> pl.DataFrame:
    """
    Load raw Parquet, apply Layer 1 filters, and log shrink stats.
    """
    settings = Settings()
    raw_dir = settings.raw_dir

    raw_path = raw_dir / f"{day}.parquet"
    raw_df = pl.read_parquet(raw_path)

    df = raw_df.filter(pl.col("duration") >= settings.min_duration_ms)
    if settings.drop_idle:
        df = df.filter(
            ~pl.col("app")
                .str.to_lowercase()
                .str.contains("idle|afk")
        )

    kept = df.height
    total = raw_df.height
    log.info(
        "🔍 Raw events: %d → after filter: %d (%.1f%% kept)",
        total,
        kept,
        kept / total * 100,
    )
    return df.sort("timestamp")

def _events_to_markdown(df: pl.DataFrame) -> str:
    """Convert up to max_events rows to a Markdown table."""
    settings = Settings()
    return (
        df
        .select(
            pl.col("timestamp").dt.strftime("%H:%M:%S").alias("time"),
            "duration", "app", "title"
        )
        .head(settings.max_events)
        .to_pandas()
        .to_markdown(index=False)
    )

def _prompt(markdown_table: str) -> str:
    """Build the Gemini prompt with schema & rules."""
    settings = Settings()
    return f"""
You are a personal life-logging assistant.
Group the raw computer-usage events below into higher-level timeline entries.
Respond **ONLY with JSON** exactly matching this schema:

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
* Merge consecutive events belonging to the same activity/project.
* If unsure, return null.
* Use window titles & URLs for context.
* Keep entries chronological.

Raw events (max {settings.max_events} shown):

{markdown_table}
"""

def _safe_generate(client, contents: str, retries=5) -> str:
    """Call Gemini with exponential backoff on transient errors."""
    for attempt in range(1, retries + 1):
        try:
            resp = client.models.generate_content(
                model=Settings().model_name,
                contents=contents,
            )
            return resp.candidates[0].content.parts[0].text
        except Exception as e:
            if attempt == retries:
                raise
            log.warning("⚠️ Gemini error (%s), retrying in %ds", e, 2**attempt)
            time.sleep(2**attempt)

# ---------- postprocessing (Layer 1b) --------------------------------------

# Map known project aliases to a single canonical name
PROJECT_ALIASES: dict[str, str] = {
    "city.blend": "Energy Project",
    "Renewable Energy Project": "Energy Project",
    # add more aliases here as needed
}

def _normalize_projects(entries: List[TimelineEntry]) -> List[TimelineEntry]:
    """Map known aliases to a single canonical project name."""
    for e in entries:
        if e.project in PROJECT_ALIASES:
            e.project = PROJECT_ALIASES[e.project]
    return entries

def _can_merge(a: TimelineEntry, b: TimelineEntry, tol_s: int = 15) -> bool:
    """
    Return True if entries a & b should be collapsed:
      - same activity
      - same project
      - same notes
      - gap between them ≤ tol_s seconds
    """
    gap = (b.start - a.end).total_seconds()
    return (
        a.activity == b.activity
        and a.project  == b.project
        and a.notes    == b.notes
        and 0 <= gap <= tol_s
    )

def _postprocess(entries: List[TimelineEntry]) -> List[TimelineEntry]:
    """
    Sort + merge any adjacent entries that pass `_can_merge`.
    """
    entries = sorted(entries, key=lambda e: e.start)
    merged: List[TimelineEntry] = []
    for e in entries:
        if merged and _can_merge(merged[-1], e):
            merged[-1].end = e.end
        else:
            merged.append(e)
    return merged

# ---------- public API ------------------------------------------------------

def enrich(day: date, force: bool = False) -> Path:
    """
    Enrich one day’s data:
      1) load & filter
      2) convert to Markdown & call Gemini
      3) extract JSON → Pydantic → Parquet
      4) cache responses
      5) postprocess (Layer 1b)
    """
    settings = Settings()
    cache_dir   = settings.cache_dir
    curated_dir = settings.curated_dir

    # 1) Load & filter raw events
    df = _load_events(day)
    md = _events_to_markdown(df)

    # 2) Cache / call Gemini
    cache_dir.mkdir(parents=True, exist_ok=True)
    cache_file = cache_dir / f"{day}.txt"
    if cache_file.exists() and not force:
        log.info("⚠️ Using cached Gemini response.")
        raw = cache_file.read_text()
    else:
        api_key = os.getenv("GEMINI_API_KEY", "")
        if not api_key:
            raise RuntimeError("Set GEMINI_API_KEY env var")
        client = genai.Client(api_key=api_key)

        raw = _safe_generate(client, _prompt(md))
        cache_file.write_text(raw)
        log.info("💾 Cached Gemini output to %s", cache_file)

    # 3) Parse & validate JSON
    objs    = _extract_json(raw)
    entries = [TimelineEntry(**o) for o in objs]

    # 4) Layer 1b: postprocess
    entries = _normalize_projects(entries)
    entries = _postprocess(entries)

    # 5) Write curated Parquet
    curated_dir.mkdir(parents=True, exist_ok=True)
    out = curated_dir / f"{day}.parquet"
    pl.DataFrame([e.model_dump() for e in entries]).write_parquet(out)
    log.info("✅ Enriched %d entries → %s", len(entries), out)

    return out

# ---------- CLI entrypoint -------------------------------------------------

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Enrich AW events with Gemini")
    parser.add_argument(
        "--day",
        type=lambda s: date.fromisoformat(s),
        help="YYYY-MM-DD (default yesterday)"
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Ignore cache and re-prompt Gemini"
    )
    args = parser.parse_args()
    target = args.day or (date.today() - timedelta(days=1))
    enrich(target, force=args.force)
