import sys
from pathlib import Path
from datetime import date
import polars as pl

# Add project root to sys.path so LifeLog modules can be imported
sys.path.append(str(Path(__file__).resolve().parents[1]))

from LifeLog.config import Settings


# Your prompt template
PROMPT_TEMPLATE = """
You are the world’s leading personal life-logging assistant.  Your sole output must be a JSON array (no prose, no markdown) with entries strictly following this schema:

[
  {{
    "start":     "YYYY-MM-DDTHH:MM:SSZ",
    "end":       "YYYY-MM-DDTHH:MM:SSZ",
    "activity":  "short phrase",
    "project":   "optional",
    "location":  "optional",
    "notes":     "brief description"
  }}
]

Guidelines:
* Parse only events on {day} (UTC).
* Merge consecutive events with identical activity and project.
* Maintain chronological order.
* All timestamps and fields must exactly match the schema.
* No extra keys or nested objects.

Raw events (table):

{events_md}
"""

def load_day(day: date) -> pl.DataFrame:
    settings = Settings()
    path = settings.raw_dir / f"{day}.parquet"
    df = pl.read_parquet(path)
    df = df.filter(pl.col("duration") >= settings.min_duration_ms)
    if settings.drop_idle:
        df = df.filter(~pl.col("app").str.to_lowercase().str.contains("idle|afk"))
    df = df.sort("timestamp")
    return df


def df_to_md(df: pl.DataFrame) -> str:
    return (
        df.select(
            pl.col("timestamp").dt.strftime("%Y-%m-%d %H:%M:%S").alias("timestamp"),
            "duration", "app", "title"
        )
        .to_pandas()
        .to_markdown(index=False)
    )


if __name__ == "__main__":
    target_day = date(2025, 5, 13)
    df = load_day(target_day)
    md = df_to_md(df)
    prompt = PROMPT_TEMPLATE.format(day=target_day.isoformat(), events_md=md)

    out = Path("test.txt")
    out.write_text(prompt)
    print(f"✅ Prompt written to {out}")
