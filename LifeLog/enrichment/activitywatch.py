# LifeLog/enrichment/activitywatch.py

from __future__ import annotations

# ── Monkey-patch HTTPX to allow unicode & bytes in header values ────────────
try:
    import httpx._models as _httpx_models

    def _normalize_header_value(value, encoding: str | None):
        if isinstance(value, (bytes, bytearray)):
            return bytes(value)
        try:
            return value.encode(encoding or "ascii")
        except UnicodeEncodeError:
            return value.encode("utf-8", errors="ignore")

    _httpx_models._normalize_header_value = _normalize_header_value
except ImportError:
    pass

import json, logging, os, re, time
from datetime import date, timedelta
from pathlib import Path
from typing import List

import polars as pl
from google import genai

from LifeLog.config import Settings
from LifeLog.models import TimelineEntry
from LifeLog.enrichment.project_resolver import ProjectResolver

# ── Logging ────────────────────────────────────────────────────────────────
log = logging.getLogger(__name__)

# ── JSON extraction ────────────────────────────────────────────────────────

def _extract_json(txt: str) -> list[dict]:
    txt = txt.strip()
    arrays: List[dict] = []

    for block in re.findall(r"```json\s*(\[.*?\])\s*```", txt, re.DOTALL):
        arrays.extend(json.loads(block))

    if not arrays:
        for block in re.findall(r"\[.*?\]", txt, re.DOTALL):
            try:
                arrays.extend(json.loads(block))
            except json.JSONDecodeError:
                continue

    if not arrays:
        raise ValueError("No JSON arrays found in Gemini response")

    return arrays

# ── Layer 1: filter raw events ─────────────────────────────────────────────

def _load_events(day: date) -> pl.DataFrame:
    settings = Settings()
    raw_path = settings.raw_dir / f"{day}.parquet"
    raw_df = pl.read_parquet(raw_path)

    df = raw_df.filter(pl.col("duration") >= settings.min_duration_ms)
    if settings.drop_idle:
        df = df.filter(
            ~pl.col("app")
                .str.to_lowercase()
                .str.contains("idle|afk")
        )

    log.info(
        "🔍 Raw events: %d → after filter: %d (%.1f%% kept)",
        raw_df.height, df.height, df.height / raw_df.height * 100
    )
    return df.sort("timestamp")

# ── Markdown formatting for prompt ─────────────────────────────────────────

def _events_to_markdown(df: pl.DataFrame) -> str:
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

# ── Layer 1b: postprocessing ───────────────────────────────────────────────

PROJECT_ALIASES: dict[str, str] = {
    "city.blend": "Energy Project",
    "Renewable Energy Project": "Energy Project",
    "Blender Project": "Energy Project",
}

def _normalize_projects(entries: List[TimelineEntry]) -> List[TimelineEntry]:
    for e in entries:
        if e.project in PROJECT_ALIASES:
            e.project = PROJECT_ALIASES[e.project]
    return entries

def _can_merge(a: TimelineEntry, b: TimelineEntry, tol_s: int = 15) -> bool:
    gap = (b.start - a.end).total_seconds()
    return (
        a.activity == b.activity
        and a.project == b.project
        and a.notes == b.notes
        and 0 <= gap <= tol_s
    )

def _postprocess(entries: List[TimelineEntry]) -> List[TimelineEntry]:
    entries = sorted(entries, key=lambda e: e.start)
    merged: List[TimelineEntry] = []
    for e in entries:
        if merged and _can_merge(merged[-1], e):
            merged[-1].end = e.end
        else:
            merged.append(e)
    return merged

# ── Public API ─────────────────────────────────────────────────────────────

def enrich(day: date, force: bool = False) -> Path:
    settings = Settings()
    cache_path = settings.cache_dir / f"{day}.txt"
    out_path   = settings.curated_dir / f"{day}.parquet"

    df = _load_events(day)
    md = _events_to_markdown(df)

    settings.cache_dir.mkdir(parents=True, exist_ok=True)
    settings.curated_dir.mkdir(parents=True, exist_ok=True)

    if cache_path.exists() and not force:
        log.info("⚠️ Using cached Gemini response.")
        raw = cache_path.read_text()
    else:
        api_key = os.getenv("GEMINI_API_KEY", "")
        if not api_key:
            raise RuntimeError("Set GEMINI_API_KEY env var")
        client = genai.Client(api_key=api_key)

        raw = _safe_generate(client, _prompt(md))
        cache_path.write_text(raw)
        log.info("💾 Cached Gemini output to %s", cache_path)

    objs = _extract_json(raw)
    entries = [TimelineEntry(**o) for o in objs]

    # ── Layer 1b: automatic project-name resolution ───────────────
    resolver = ProjectResolver()
    for e in entries:
        e.project = resolver.resolve(e.project, context=e.notes)

    entries = _normalize_projects(entries)
    entries = _postprocess(entries)

    pl.DataFrame([e.model_dump() for e in entries]).write_parquet(out_path)
    log.info("✅ Enriched %d entries → %s", len(entries), out_path)

    return out_path

# ── CLI Entrypoint ─────────────────────────────────────────────────────────

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Enrich AW events with Gemini")
    parser.add_argument("--day", type=lambda s: date.fromisoformat(s), help="YYYY-MM-DD (default: yesterday)")
    parser.add_argument("--force", action="store_true", help="Ignore cache and re-prompt Gemini")
    args = parser.parse_args()
    enrich(args.day or (date.today() - timedelta(days=1)), force=args.force)
