"""Utility to copy the bundled test day into LifeLog storage."""

import json
from pathlib import Path
import shutil
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
TEST_DIR = PROJECT_ROOT / "tests" / "testdata"
SUMMARY_SRC = TEST_DIR / "2025-05-22.json"

CURATED_DIR = PROJECT_ROOT / "LifeLog" / "storage" / "curated" / "timeline"
SUMMARY_DIR = PROJECT_ROOT / "LifeLog" / "storage" / "summary" / "daily"

CURATED_DIR.mkdir(parents=True, exist_ok=True)
SUMMARY_DIR.mkdir(parents=True, exist_ok=True)

def copy_test_files() -> None:
    """Copy test summary files into storage."""

    if SUMMARY_SRC.exists():
        shutil.copy(SUMMARY_SRC, SUMMARY_DIR / SUMMARY_SRC.name)
        print(f"Copied summary data to {SUMMARY_DIR}")
    else:
        summary = {
            "date": "2025-05-22",
            "blocks": [],
            "day_summary": "Sample data for testing without ActivityWatch.",
            "stats": {
                "total_active_time_min": 0,
                "focus_time_min": 0,
                "number_blocks": 0,
                "top_project": "",
                "top_activity": ""
            },
            "version": 2
        }
        target = SUMMARY_DIR / "2025-05-22.json"
        target.write_text(json.dumps(summary, indent=2))
        print(f"Created placeholder summary at {target}")

if __name__ == "__main__":
    copy_test_files()
