from __future__ import annotations

# ── Monkey-patch HTTPX for lenient headers ──────────────────────────────────
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
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import List

import polars as pl
from google import genai

from LifeLog.config import Settings
from LifeLog.models import TimelineEntry
from LifeLog.enrichment.project_resolver import ProjectResolver

log = logging.getLogger(__name__)

# ────────────────────────────────────────────────────────────────────────────
#  JSON extraction that never crashes on truncation
# ────────────────────────────────────────────────────────────────────────────

FENCE_RE = re.compile(r"```(?:json)?\s*|\s*```", re.IGNORECASE)

def _extract_json(text: str) -> list[dict]:
    """
    Strip ```json fences, then collect every balanced { ... } object.
    Skips malformed tail fragments so we never raise JSONDecodeError.
    """
    text = FENCE_RE.sub("", text).strip()
    objs, current, stack = [], [], 0

    for ch in text:
        if ch == "{":
            stack += 1
        if stack > 0:
            current.append(ch)
        if ch == "}":
            stack -= 1
            if stack == 0:
                try:
                    objs.append(json.loads("".join(current)))
                except json.JSONDecodeError:
                    pass
                current = []
    return objs

# ────────────────────────────────────────────────────────────────────────────
#  Load + filter raw ActivityWatch parquet
# ────────────────────────────────────────────────────────────────────────────

def _load_events(day: date) -> pl.DataFrame:
    settings = Settings()
    raw_path = settings.raw_dir / f"{day}.parquet"
    raw_df = pl.read_parquet(raw_path)

    df = raw_df.filter(pl.col("duration") >= settings.min_duration_ms)
    if settings.drop_idle:
        df = df.filter(~pl.col("app").str.to_lowercase().str.contains("idle|afk"))

    log.info("🔍 Raw events: %d → filtered: %d (%.1f%% kept)",
             raw_df.height, df.height, df.height / raw_df.height * 100)
    return df.sort("timestamp")

def _events_to_md(df: pl.DataFrame) -> str:
    settings = Settings()
    return (
        df
        .select(
            pl.col("timestamp").dt.strftime("%Y-%m-%d %H:%M:%S").alias("timestamp"),
            "duration", "app", "title"
        )
        .head(settings.max_events)
        .to_pandas()
        .to_markdown(index=False)
    )

# ────────────────────────────────────────────────────────────────────────────
#  Prompt
# ────────────────────────────────────────────────────────────────────────────

def _prompt(md: str, day: date) -> str:
    return f"""
You are a personal life-logging assistant. Convert the raw events to concise
timeline entries.

JSON schema:

[
  {{
    "start": "YYYY-MM-DDTHH:MM:SSZ",
    "end":   "YYYY-MM-DDTHH:MM:SSZ",
    "activity": "short phrase",
    "project": "optional",
    "location": "optional",
    "notes": "brief description"
  }}
]

Rules:
* ALL start times MUST be on {day.isoformat()} only.
* Merge adjacent events of same activity/project.
* Keep entries chronological. Output JSON only.

Raw events:

{md}
"""

# ────────────────────────────────────────────────────────────────────────────
#  Robust Gemini generator with continuation
# ────────────────────────────────────────────────────────────────────────────

def _generate_full_json(client, prompt: str, max_retries=5) -> str:
    def is_complete(txt: str) -> bool:
        depth = 0
        for ch in txt:
            if ch == "{": depth += 1
            elif ch == "}": depth -= 1
        return depth == 0 and txt.rstrip().endswith("]")

    def last_balanced(txt: str) -> int:
        depth = 0
        last = -1
        for i, ch in enumerate(txt):
            if ch == "{": depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0: last = i
        return last

    def call(contents: str) -> str:
        for n in range(1, max_retries + 1):
            try:
                res = client.models.generate_content(
                    model=Settings().model_name,
                    contents=contents,
                )
                return res.candidates[0].content.parts[0].text.strip()
            except Exception as e:
                if n == max_retries: raise
                log.warning("⚠️ Gemini error %s, retry %d", e, n)
                time.sleep(2**n)

    full = call(prompt)
    loops = 0

    while not is_complete(full):
        log.warning("🔁 Gemini truncated, requesting continuation…")
        idx = last_balanced(full)
        if idx == -1:
            log.error("🛑 No balanced object in:\n%s", full[:400])
            raise ValueError("Unrecoverable truncation")

        partial = full[full.find("[")+1 : idx+1].strip()
        cont_prompt = f"""
Continue the JSON array. ONLY output missing entries.

Partial:
[
{partial}
"""
        tail = call(cont_prompt).strip()
        # strip fences/brackets
        tail = FENCE_RE.sub("", tail).strip()
        if tail.startswith("["): tail = tail[1:]
        if tail.endswith("]"): tail = tail[:-1]

        full = full[:idx+1].rstrip() + "," + tail.lstrip(", \n") + "]"
        loops += 1
        if loops > 6:
            log.error("🛑 Too many continuation loops.")
            break
    return full

# ────────────────────────────────────────────────────────────────────────────
#  Timestamp fix + day filter
# ────────────────────────────────────────────────────────────────────────────

def _fix_entries(objs: list[dict], day: date) -> list[TimelineEntry]:
    start_day = datetime.combine(day, datetime.min.time())
    end_day   = start_day + timedelta(days=1)
    ok: list[TimelineEntry] = []

    for o in objs:
        try:
            s = datetime.fromisoformat(o["start"].replace("Z", ""))
            e = datetime.fromisoformat(o["end"].replace("Z", ""))
            if s >= e or not (start_day <= s < end_day):
                continue
            o["start"], o["end"] = s, e
            ok.append(TimelineEntry(**o))
        except Exception:
            continue
    return ok

# ────────────────────────────────────────────────────────────────────────────
#  Post-processing helpers
# ────────────────────────────────────────────────────────────────────────────

PROJECT_ALIASES = {
    "city.blend": "Energy Project",
    "Renewable Energy Project": "Energy Project",
    "Blender Project": "Energy Project",
}

def _norm_projects(entries: list[TimelineEntry]) -> list[TimelineEntry]:
    for e in entries:
        if e.project in PROJECT_ALIASES:
            e.project = PROJECT_ALIASES[e.project]
    return entries

def _merge(entries: list[TimelineEntry], tol: int = 15) -> list[TimelineEntry]:
    out: list[TimelineEntry] = []
    entries.sort(key=lambda e: e.start)
    for e in entries:
        if out and (
            e.activity == out[-1].activity
            and e.project == out[-1].project
            and (e.start - out[-1].end).total_seconds() <= tol
        ):
            out[-1].end = e.end
        else:
            out.append(e)
    return out

# ────────────────────────────────────────────────────────────────────────────
#  Public enrich()
# ────────────────────────────────────────────────────────────────────────────

def enrich(day: date, force=False) -> Path:
    st = Settings()
    cache = st.cache_dir / f"{day}.txt"
    out   = st.curated_dir / f"{day}.parquet"

    df = _load_events(day)
    md = _events_to_md(df)
    st.cache_dir.mkdir(parents=True, exist_ok=True)
    st.curated_dir.mkdir(parents=True, exist_ok=True)

    if cache.exists() and not force:
        log.info("⚠️ Using cached Gemini response.")
        raw = cache.read_text()
    else:
        key = os.getenv("GEMINI_API_KEY", "")
        if not key: raise RuntimeError("Set GEMINI_API_KEY")
        client = genai.Client(api_key=key)
        raw = _generate_full_json(client, _prompt(md, day))
        cache.write_text(raw)
        log.info("💾 Cached Gemini output to %s", cache)

    objs     = _extract_json(raw)
    entries  = _fix_entries(objs, day)
    resolver = ProjectResolver()
    for e in entries:
        e.project = resolver.resolve(e.project, context=e.notes)
    entries = _merge(_norm_projects(entries))
    entries = [e for e in entries if (e.end - e.start).total_seconds() >= 15]

    pl.DataFrame([e.model_dump() for e in entries]).write_parquet(out)
    log.info("✅ Enriched %d entries → %s", len(entries), out)
    return out

# ────────────────────────────────────────────────────────────────────────────
#  CLI standalone
# ────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import argparse, sys
    p = argparse.ArgumentParser(description="Enrich ActivityWatch day via Gemini")
    p.add_argument("--day", type=lambda s: date.fromisoformat(s),
                   help="YYYY-MM-DD (default yesterday)")
    p.add_argument("--force", action="store_true")
    args = p.parse_args()
    try:
        enrich(args.day or (date.today() - timedelta(days=1)), force=args.force)
    except Exception as e:
        log.error("❌ Enrichment failed: %s", e)
        sys.exit(1)
