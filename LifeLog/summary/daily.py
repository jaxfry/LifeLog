"""
Layer 2  ── Daily semantic summaries
===================================

Inputs : curated/timeline/2025-05-12.parquet  (Layer 1b)
Outputs: summary/daily/2025-05-12.json       (Layer 2)
"""

from __future__ import annotations
import json, logging, os, time, re
from datetime import date, timedelta, datetime
from pathlib import Path
from typing import List, Optional

import polars as pl
from google import genai
from pydantic import BaseModel, Field, PositiveInt
from sentence_transformers import SentenceTransformer

from LifeLog.config import Settings
from LifeLog.models import TimelineEntry

log = logging.getLogger(__name__)
EMBED_MODEL = SentenceTransformer("sentence-transformers/paraphrase-MiniLM-L6-v2", device="cpu")

# ────────────────────────────────────────────────────────────────────────────
# 1.  Pydantic schema
# ────────────────────────────────────────────────────────────────────────────

class Block(BaseModel):
    start: str            # "HH:MM"
    end:   str
    label: str
    project: Optional[str]
    activity: str
    summary: str
    tags: List[str] = Field(default_factory=list)
    embedding: Optional[List[float]] = None

class Stats(BaseModel):
    total_active_time_min: PositiveInt
    focus_time_min:        PositiveInt
    number_blocks:         PositiveInt
    top_project: Optional[str]
    top_activity: str

class DailySummary(BaseModel):
    date: str             # YYYY-MM-DD
    blocks: List[Block]
    day_summary: str
    stats: Stats
    version: int = 1

# ────────────────────────────────────────────────────────────────────────────
# 2.  Deterministic pre-grouping
# ────────────────────────────────────────────────────────────────────────────

def _group_adjacent(entries: list[TimelineEntry], gap_s=300) -> list[list[TimelineEntry]]:
    groups: list[list[TimelineEntry]] = []
    for e in sorted(entries, key=lambda x: x.start):
        if not groups:
            groups.append([e])
            continue
        last = groups[-1][-1]
        if (
            e.project == last.project
            and e.activity == last.activity
            and (e.start - last.end).total_seconds() <= gap_s
        ):
            groups[-1].append(e)
        else:
            groups.append([e])
    return groups

def _blocks_markdown(groups: list[list[TimelineEntry]]) -> str:
    rows = []
    for g in groups:
        start = g[0].start.strftime("%H:%M")
        end   = g[-1].end.strftime("%H:%M")
        proj  = g[0].project or ""
        act   = g[0].activity
        notes = (g[0].notes or "")[:60]
        rows.append([start, end, proj, act, notes])
    import pandas as pd
    return pd.DataFrame(rows, columns=["start","end","project","activity","notes"]).to_markdown(index=False)

# ────────────────────────────────────────────────────────────────────────────
# 3.  Gemini prompt & call
# ────────────────────────────────────────────────────────────────────────────

_PROMPT_TEMPLATE = """
You are a life-logging summarizer.
Given the table of timeline groups, return ONLY JSON matching this schema:

{{
  "blocks":[
    {{
      "start":"HH:MM",
      "end":"HH:MM",
      "label":"Project · Activity",
      "project":"... or null",
      "activity":"...",
      "summary":"1–2 sentences",
      "tags":["..."]
    }}
  ],
  "day_summary":"2–3 sentences narrating the overall day.",
  "stats":{{
    "total_active_time_min":int,
    "focus_time_min":int,
    "number_blocks":int,
    "top_project":"string or null",
    "top_activity":"string"
  }}
}}

Rules:
* Merge rows that represent one coherent block.
* Use concise labels.
* Use null for project when unknown.
* Return VALID JSON – no markdown, no comments.
----------------------------------------------------------------
{markdown}
"""

def _safe_generate(client, prompt: str, retries=4) -> str:
    for i in range(1, retries+1):
        try:
            resp = client.models.generate_content(
                model=Settings().model_name,
                contents=prompt,
            )
            return resp.candidates[0].content.parts[0].text
        except Exception as e:
            if i == retries:
                raise
            log.warning("Gemini error (%s) – retry in %ds", e, 2**i)
            time.sleep(2**i)

def _extract_json(txt: str) -> dict:
    txt = txt.strip()
    try:
        return json.loads(txt)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", txt, re.DOTALL)
        if match:
            return json.loads(match.group(0))
        raise

# ────────────────────────────────────────────────────────────────────────────
# 4.  Main entrypoint
# ────────────────────────────────────────────────────────────────────────────

def summarize_day(day: date, force=False) -> Path:
    st = Settings()
    src = st.curated_dir / f"{day}.parquet"
    dst = st.summary_dir / f"{day}.json"
    st.summary_dir.mkdir(parents=True, exist_ok=True)

    if dst.exists() and not force:
        log.info("⚠️ Using cached summary %s", dst)
        return dst

    df = pl.read_parquet(src)
    entries = [TimelineEntry(**r) for r in df.to_dicts()]
    groups  = _group_adjacent(entries)

    markdown = _blocks_markdown(groups)
    prompt   = _PROMPT_TEMPLATE.format(markdown=markdown)

    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise RuntimeError("Set GEMINI_API_KEY")
    client = genai.Client(api_key=api_key)

    raw = _safe_generate(client, prompt)
    data = _extract_json(raw)
    summary = DailySummary(**data, date=str(day))

    # add embeddings
    texts = [b.summary for b in summary.blocks]
    embs  = EMBED_MODEL.encode(texts, normalize_embeddings=True).tolist()
    for b, vec in zip(summary.blocks, embs):
        b.embedding = vec

    dst.write_text(summary.model_dump_json(indent=2))
    log.info("✅ Daily summary → %s", dst)
    return dst

# ── CLI helper for tests ----------------------------------------------------

if __name__ == "__main__":             # quick manual test
    summarize_day(date.today() - timedelta(days=1), force=True)
