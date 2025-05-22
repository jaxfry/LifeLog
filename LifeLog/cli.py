# LifeLog/cli.py

import argparse
import logging
import sys
from datetime import date, timedelta
from pathlib import Path

from dotenv import load_dotenv
load_dotenv()

project_root = Path(__file__).resolve().parents[1]
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from LifeLog.config import Settings
from LifeLog.ingestion.activitywatch import ingest as ingest_activitywatch_data
from LifeLog.enrichment.timeline_generator import run_enrichment_for_day
from LifeLog.summary.daily import summarize_day_activities # Import the correct function

logging.basicConfig(
    format="%(asctime)s | %(levelname)-8s | %(name)-20s | %(funcName)-25s | %(message)s",
    level=logging.INFO,
)
log = logging.getLogger("LifeLog.cli")

def main():
    settings = Settings() 

    parser = argparse.ArgumentParser(
        prog="lifelog",
        description="LifeLog: Personalized Activity Tracking & Analysis CLI"
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Enable debug logging for all LifeLog modules."
    )
    subparsers = parser.add_subparsers(dest="command", title="Available Commands", required=True)

    # --- Ingest Subcommand ---
    parser_ingest = subparsers.add_parser("ingest", help="Ingest data from sources.")
    ingest_subparsers = parser_ingest.add_subparsers(dest="source", title="Ingestion Sources", required=True)
    parser_ingest_aw = ingest_subparsers.add_parser("activitywatch", help="Fetch/process ActivityWatch data.")
    parser_ingest_aw.add_argument("--day", type=lambda s: date.fromisoformat(s) if s else None, help="Day YYYY-MM-DD (default: yesterday).")
    parser_ingest_aw.add_argument("--days-ago", type=int, default=None, help="Days ago (overrides --day).")
    parser_ingest_aw.add_argument("--out-path", type=Path, help="Custom output Parquet path.")
    def handle_ingest_activitywatch(args_ns, current_settings):
        target_day = (date.today() - timedelta(days=args_ns.days_ago)) if args_ns.days_ago is not None else (args_ns.day or (date.today() - timedelta(days=1)))
        log.info(f"CLI: Initiating ActivityWatch ingestion for {target_day}...")
        ingest_activitywatch_data(day=target_day, out_path=args_ns.out_path)
    parser_ingest_aw.set_defaults(func=handle_ingest_activitywatch)

    # --- Enrich Subcommand ---
    parser_enrich = subparsers.add_parser("enrich", help="Enrich ingested data.")
    enrich_subparsers = parser_enrich.add_subparsers(dest="target_data", title="Enrichment Targets", required=True)
    parser_enrich_timeline = enrich_subparsers.add_parser("timeline", help="Generate LLM-enriched timeline from ActivityWatch data.")
    parser_enrich_timeline.add_argument("--day", type=lambda s: date.fromisoformat(s) if s else None, help="Day YYYY-MM-DD (default: yesterday).")
    parser_enrich_timeline.add_argument("--days-ago", type=int, default=None, help="Days ago (overrides --day).")
    parser_enrich_timeline.add_argument("--force-llm", action="store_true", help="Force LLM re-query, ignore cache.")
    parser_enrich_timeline.add_argument("--force-processing", action="store_true", help="Force re-process day even if output exists.")
    def handle_enrich_timeline(args_ns, current_settings):
        target_day = (date.today() - timedelta(days=args_ns.days_ago)) if args_ns.days_ago is not None else (args_ns.day or (date.today() - timedelta(days=1)))
        if args_ns.force_llm: current_settings.enrichment_force_llm = True
        if args_ns.force_processing: current_settings.enrichment_force_processing_all = True
        log.info(f"CLI: Initiating timeline enrichment for {target_day}...")
        run_enrichment_for_day(target_day, current_settings)
    parser_enrich_timeline.set_defaults(func=handle_enrich_timeline)

    # --- Summarize Subcommand (UPDATED) ---
    parser_summarize = subparsers.add_parser(
        "summarize",
        help="Generate summaries from processed data."
    )
    summary_subparsers = parser_summarize.add_subparsers(dest="summary_type", title="Summary Types", required=True)

    parser_summarize_daily = summary_subparsers.add_parser(
        "daily",
        help="Generate a daily summary report using an LLM."
    )
    parser_summarize_daily.add_argument(
        "--day",
        type=lambda s: date.fromisoformat(s) if s else None,
        help="Day to summarize in YYYY-MM-DD format. Defaults to yesterday."
    )
    parser_summarize_daily.add_argument(
        "--days-ago",
        type=int,
        default=None,
        help="Summarize data for this many days ago. Overrides --day."
    )
    parser_summarize_daily.add_argument(
        "--force", # General force flag for summary regeneration
        action="store_true",
        help="Force regeneration of the summary, ignoring existing output file and potentially cached LLM responses (if summary_force_llm is also true or implied)."
    )
    # Add a specific flag if you want to force ONLY the LLM call for summary, separate from output file force
    parser_summarize_daily.add_argument(
        "--force-summary-llm", 
        action="store_true",
        help="Force re-querying the LLM for the summary, ignoring cached summary LLM responses."
    )

    def handle_summarize_daily(args_ns, current_settings: Settings): # Type hint settings
        target_day_summary: date
        if args_ns.days_ago is not None:
            target_day_summary = date.today() - timedelta(days=args_ns.days_ago)
        elif args_ns.day:
            target_day_summary = args_ns.day
        else:
            target_day_summary = date.today() - timedelta(days=1)
        
        # The `force_regenerate` parameter in summarize_day_activities handles ignoring the output file.
        # The settings `summary_force_llm` handles ignoring the LLM cache.
        force_output_regeneration = args_ns.force 
        
        if args_ns.force_summary_llm: # If this specific flag is used
            current_settings.summary_force_llm = True
        elif args_ns.force: # If general --force is used, also imply forcing summary LLM
             current_settings.summary_force_llm = True


        log.info(f"CLI: Initiating daily summary for {target_day_summary} (Force output: {force_output_regeneration}, Force LLM: {current_settings.summary_force_llm})...")
        summarize_day_activities(
            day=target_day_summary, 
            settings=current_settings, 
            force_regenerate=force_output_regeneration
        )

    parser_summarize_daily.set_defaults(func=handle_summarize_daily)
    # --- End Summarize Subcommand ---

    args = parser.parse_args()

    if args.debug:
        logging.getLogger("LifeLog").setLevel(logging.DEBUG)
        root_logger = logging.getLogger()
        root_logger.setLevel(logging.DEBUG)
        for handler in root_logger.handlers:
            handler.setLevel(logging.DEBUG)
        log.debug("Debug logging enabled via CLI.")

    if hasattr(args, "func"):
        args.func(args, settings)
    else:
        parser.print_help()
        sys.exit(1)

if __name__ == "__main__":
    main()