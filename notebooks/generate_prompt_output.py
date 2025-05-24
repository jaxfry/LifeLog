from __future__ import annotations

import argparse
import logging
import os
from datetime import date, datetime, timedelta
from pathlib import Path
import sys # Add this import

# Add the project root to sys.path
# Assumes the script is in LifeLog/notebooks/ and the LifeLog package is in LifeLog/LifeLog/
# Adjust if your structure is different.
project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root))

from typing import List, Optional, Dict, Any, Union

import polars as pl
# Assuming Settings can be imported from LifeLog.config
# If LifeLog is not in PYTHONPATH, this might need adjustment or copying the Settings class
from LifeLog.config import Settings # Add this import

log = logging.getLogger(__name__)

# --- Core Logic (Adapted from timeline_generator.py) ---

def _load_and_prepare_input_df(day: date, settings: Settings) -> pl.DataFrame:
    ingested_file_path = settings.raw_dir / f"{day}.parquet"
    if not ingested_file_path.exists():
        log.error(f"Ingested data file not found for {day}: {ingested_file_path}")
        raise FileNotFoundError(f"Ingested data file not found for {day}")
    df_raw_ingested = pl.read_parquet(ingested_file_path)
    log.info(f"Loaded {df_raw_ingested.height} raw ingested events for {day}.")
    df_activities = df_raw_ingested.filter(pl.col("app") != settings.afk_app_name_override)
    if df_activities.is_empty(): return df_activities
    df_activities = df_activities.with_columns(((pl.col("end") - pl.col("start")).dt.total_seconds()).alias("duration_s"))
    if settings.enrichment_min_duration_s > 0:
        df_activities = df_activities.filter(pl.col("duration_s") >= settings.enrichment_min_duration_s)
    if df_activities.is_empty(): return df_activities
    truncate_limit = settings.enrichment_prompt_truncate_limit; ellipsis_suffix = "…"
    df_for_prompt = df_activities.select(
        pl.col("start").dt.strftime("%H:%M:%S").alias("time_utc"),
        pl.col("duration_s").round(0).cast(pl.Int32),
        pl.col("app"),
        pl.when(pl.col("title").fill_null("").str.len_chars() > truncate_limit).then(pl.col("title").fill_null("").str.slice(0, truncate_limit) + pl.lit(ellipsis_suffix)).otherwise(pl.col("title").fill_null("")).alias("title"),
        pl.when(pl.col("url").fill_null("").str.len_chars() > truncate_limit).then(pl.col("url").fill_null("").str.slice(0, truncate_limit) + pl.lit(ellipsis_suffix)).otherwise(pl.col("url").fill_null("")).alias("url"),
    ).sort("time_utc")
    log.info(f"Prepared {df_for_prompt.height} activity events for LLM prompt for {day}.")
    return df_for_prompt

def _build_llm_prompt(day: date, events_df: pl.DataFrame, settings: Settings) -> str:
    if events_df.is_empty(): return ""
    max_events_for_prompt = settings.enrichment_max_events
    events_table_md = events_df.head(max_events_for_prompt).to_pandas().to_markdown(index=False)
    
    # This print statement is kept from the original code, it might be useful for you
    print(f"--- Events Table for Prompt (Markdown) ---")
    print(events_table_md)
    print(f"------------------------------------------")

    schema_description = """[{"start": "YYYY-MM-DDTHH:MM:SSZ","end": "YYYY-MM-DDTHH:MM:SSZ","activity": "string","project": "string | null","notes": "string | null"}]"""

    PROMPT_PREAMBLE = f"""You are a meticulous LifeLog assistant. Your task is to analyze a list of raw computer activity events for the date {day.isoformat()}
and group them into meaningful, consolidated timeline entries.

The raw events are provided in a table with columns: time_utc, duration_s, app, title, url.
'time_utc' is the start time of the event in UTC. The date for all events is {day.isoformat()}.
'duration_s' is the duration of the event in seconds.

Your goal is to output a JSON list of "EnrichedTimelineEntry" objects.
Each EnrichedTimelineEntry represents a distinct, user-perceived activity or task.
The JSON output MUST be a list of objects, strictly adhering to this schema for each object:
{schema_description}
"""

    # Using GUIDELINES as it seems more comprehensive from the provided context
    GUIDELINES = """Key Instructions:
1.  Merge Logically: Combine consecutive raw events that clearly belong to the same overarching activity and project.
2.  Determine Start/End (UTC): "start" is UTC start of earliest event, "end" is UTC end of latest event in group. Format: "YYYY-MM-DDTHH:MM:SSZ".
3.  Activity Description ("activity"): Be specific and concise. e.g., "Editing 'script.py' in VS Code".
4.  Project Identification ("project"): Infer project. Null if not clear.
    -   `project`: Assign a project name if clearly identifiable from `app`, `title`, or `url` (e.g., "LifeLog Development", "Course XYZ"). Use `null` if no specific project.
5.  Notes ("notes"): This field is critical for providing rich, contextual information. Aim for a 1-2 sentence summary.
    -   **PRIORITY: Extract and include specific, meaningful details from the `title` and `url` columns of the raw events.** Do not just repeat the application name or a generic activity if more detail is present.
    -   **Examples of GOOD notes (incorporating details from `title`/`url`):**
        - For "Checked emails": "Checked primary inbox (Gmail) which had 2,336 messages, 204 unread." (assuming 'primary inbox', 'Gmail', counts are in `title`)
        - For "Watched YouTube video": "Watched 'Google I/O Keynote Highlights' and 'Advanced Python Tips' on YouTube." (video titles from `title`)
        - For "Used Stitch AI": "Worked on design project ID 12345 in Stitch AI." (ID from `title` or `url`)
        - For "Read documentation": "Read ActivityWatch docs on 'buckets and events'." (topic from `title` or `url`)
        - For "Coding": "Worked on `feature_x.py` and `utils.js` for LifeLog project." (filenames from `title`)
    -   **Examples of BAD notes (AVOID these if details are available):**
        - "Email checking." (too brief, no detail)
        - "Used Miru." (generic, repeats app name)
        - "Watched some videos." (lacks specificity)
        - "Coding activity." (uninformative)
    -   **Synthesize from Merged Events**: If multiple raw events are merged, the notes should summarize the combined specifics. For instance, if multiple videos are watched, list their titles if possible.
    -   **Fallback**: If, after careful inspection of `title` and `url`, no specific details can be extracted, then a more general summary (like "General browsing on Chrome") or `null` is acceptable. Prefer informative notes over `null` if any detail can be gleaned.
6.  **Focus on Meaningful Activities**: Filter out very short, insignificant events if they don't contribute to a larger activity block, unless they are distinct actions like "Sent email". The input data is already somewhat filtered, but use your judgment to create a *useful* timeline.
"""

    prompt = f"{PROMPT_PREAMBLE}\\n\\n{GUIDELINES}\\n\\nRaw Usage Events for {day.isoformat()}:\\n{events_table_md}\\n\\nJSON Output (Strictly Adhering to Schema):\\n"
    return prompt

def generate_prompt_for_day(target_day: date, settings: Settings) -> str | None:
    log.info(f"Starting prompt generation process for day: {target_day.isoformat()}")
    
    try:
        df_for_prompt = _load_and_prepare_input_df(target_day, settings)
        if df_for_prompt.is_empty():
            log.warning(f"No suitable events for LLM for {target_day}. No prompt will be generated.")
            return None
            
        prompt_text = _build_llm_prompt(target_day, df_for_prompt, settings)
        
        if not prompt_text:
            log.warning(f"Prompt generation resulted in an empty prompt for {target_day}.")
            return None
            
        return prompt_text
        
    except FileNotFoundError:
        log.error(f"Could not generate prompt for {target_day} due to missing input file.")
        return None
    except Exception as e:
        log.error(f"Unhandled error during prompt generation for day {target_day}: {e}", exc_info=True)
        return None

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)-7s] [%(name)-20s] %(message)s", datefmt="%Y-%m-%d %H:%M:%S")
    
    parser = argparse.ArgumentParser(description="Generate and save LLM prompt for LifeLog data.")
    parser.add_argument("--day", type=lambda s: date.fromisoformat(s) if s else None, 
                        default=None, help="Target day in YYYY-MM-DD format (default: yesterday)")
    parser.add_argument("--days-ago", type=int, default=None, 
                        help="Number of days ago (overrides --day if specified)")
    parser.add_argument("--output-dir", type=str, default="LifeLog/tmp/generated_prompts",
                        help="Directory to save the generated prompt file.")
    parser.add_argument("--debug", action="store_true", help="Enable debug logging")

    args = parser.parse_args()
    
    # Initialize settings
    # This assumes your Settings class can be initialized like this and find its config
    # You might need to adjust this if LifeLog.config expects specific paths or env vars
    # For simplicity, if LifeLog is a top-level package in your workspace, this should work.
    current_script_path = Path(__file__).resolve()
    # Assuming the script is in /Users/jaxon/Coding/LifeLog/notebooks/
    # and LifeLog (package) is at /Users/jaxon/Coding/LifeLog/LifeLog/
    # We need to ensure LifeLog.config can be found.
    # If LifeLog is directly in PYTHONPATH or the script is run from the workspace root, it might just work.
    # Otherwise, you might need to add the workspace root to sys.path or ensure Settings() handles paths correctly.
    settings = Settings() 

    if args.debug:
        logging.getLogger().setLevel(logging.DEBUG)
        log.setLevel(logging.DEBUG)
        log.debug("Debug mode enabled.")

    if args.days_ago is not None:
        target_day = date.today() - timedelta(days=args.days_ago)
    elif args.day:
        target_day = args.day
    else:
        target_day = date.today() - timedelta(days=1)

    log.info(f"Target day for prompt generation: {target_day.isoformat()}")

    # Ensure output directory exists
    # Construct absolute path for output_dir relative to workspace root
    workspace_root = Path("/Users/jaxon/Coding/LifeLog") # Explicitly set workspace root
    output_directory = workspace_root / args.output_dir
    output_directory.mkdir(parents=True, exist_ok=True)

    prompt_content = generate_prompt_for_day(target_day, settings)

    if prompt_content:
        output_file_path = output_directory / f"prompt_{target_day.isoformat()}.txt"
        try:
            with open(output_file_path, "w", encoding="utf-8") as f:
                f.write(prompt_content)
            log.info(f"Successfully generated and saved prompt to: {output_file_path}")
        except IOError as e:
            log.error(f"Failed to write prompt to file {output_file_path}: {e}")
    else:
        log.error(f"Prompt generation failed for {target_day.isoformat()}. No file written.")

