import argparse
import logging
import sys
from datetime import date, timedelta
from pathlib import Path

from dotenv import load_dotenv
load_dotenv()

# Ensure the project root is on PYTHONPATH for direct script runs
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from LifeLog.config import Settings
from LifeLog.ingestion.activitywatch import ingest as ingest_aw
from LifeLog.summary.daily import summarize_day

# Configure a simple root logger
logging.basicConfig(
    format="%(asctime)s %(levelname)s %(message)s", level=logging.INFO
)
log = logging.getLogger(__name__)

def main():
    settings = Settings()

    parser = argparse.ArgumentParser(prog="lifelog")
    sub = parser.add_subparsers(dest="cmd")

    # Ingest raw ActivityWatch data
    p_ing = sub.add_parser("ingest-activitywatch")
    p_ing.add_argument(
        "--day", type=lambda s: date.fromisoformat(s),
        help="YYYY-MM-DD (default: yesterday)"
    )
    p_ing.set_defaults(func=lambda ns: ingest_aw(ns.day))

    # Enrich with Gemini
    p_enr = sub.add_parser("enrich-activitywatch")
    p_enr.add_argument(
        "--day", type=lambda s: date.fromisoformat(s),
        help="YYYY-MM-DD (default: yesterday)"
    )
    p_enr.add_argument(
        "--force", action="store_true",
        help="Ignore cache and re-prompt Gemini"
    )
    p_enr.set_defaults(func=lambda ns: enrich_aw(
        ns.day or (date.today() - timedelta(days=1)),
        force=ns.force
    ))

    # Summarize daily activity (Layer 2)
    p_sum = sub.add_parser("summarize-day", help="Generate Layer-2 daily summary")
    p_sum.add_argument("--day", type=lambda s: date.fromisoformat(s), help="YYYY-MM-DD")
    p_sum.add_argument("--force", action="store_true")
    p_sum.set_defaults(func=lambda ns: summarize_day(
        ns.day or (date.today() - timedelta(days=1)),
        force=ns.force
    ))

    args = parser.parse_args()
    if not hasattr(args, "func"):
        parser.print_help()
        sys.exit(1)

    args.func(args)

if __name__ == "__main__":
    main()
