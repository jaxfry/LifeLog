import argparse
import logging
import sys
from datetime import date, timedelta
from pathlib import Path

from dotenv import load_dotenv
load_dotenv()

# Ensure the project root is on PYTHONPATH for direct script runs
project_root = Path(__file__).resolve().parents[1]
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from LifeLog.config import Settings
from LifeLog.ingestion.activitywatch import ingest as ingest_activitywatch_data
# Import the new enrichment function
from LifeLog.enrichment.timeline_generator import run_enrichment_for_day
# from LifeLog.summary.daily import summarize_day # Assuming you have this

# Configure a simple root logger
logging.basicConfig(
    format="%(asctime)s | %(levelname)-8s | %(name)-20s | %(funcName)-25s | %(message)s",
    level=logging.INFO,
)
log = logging.getLogger("LifeLog.cli") # More specific logger name

def main():
    settings = Settings() # Load settings once

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
    parser_ingest = subparsers.add_parser(
        "ingest",
        help="Ingest data from sources like ActivityWatch."
    )
    ingest_subparsers = parser_ingest.add_subparsers(dest="source", title="Ingestion Sources", required=True)
    
    # Ingest ActivityWatch
    parser_ingest_aw = ingest_subparsers.add_parser(
        "activitywatch",
        help="Fetch and process data from ActivityWatch."
    )
    parser_ingest_aw.add_argument(
        "--day",
        type=lambda s: date.fromisoformat(s) if s else None,
        help="Day to ingest in YYYY-MM-DD format. Defaults to yesterday."
    )
    parser_ingest_aw.add_argument(
        "--days-ago",
        type=int,
        default=None,
        help="Ingest data for this many days ago (e.g., 1 for yesterday). Overrides --day."
    )
    parser_ingest_aw.add_argument(
        "--out-path",
        type=Path,
        help="Optional custom output path for the Parquet file."
    )
    def handle_ingest_activitywatch(args_ns, current_settings):
        target_day_aw: date
        if args_ns.days_ago is not None:
            target_day_aw = date.today() - timedelta(days=args_ns.days_ago)
        elif args_ns.day:
            target_day_aw = args_ns.day
        else:
            target_day_aw = date.today() - timedelta(days=1)
        
        log.info(f"CLI: Initiating ActivityWatch ingestion for {target_day_aw}...")
        # Pass settings to the ingest function if it needs it (current ingest script loads its own)
        ingest_activitywatch_data(day=target_day_aw, out_path=args_ns.out_path)

    parser_ingest_aw.set_defaults(func=handle_ingest_activitywatch)


    # --- Enrich Subcommand ---
    parser_enrich = subparsers.add_parser(
        "enrich",
        help="Enrich ingested data using LLMs or other methods."
    )
    enrich_subparsers = parser_enrich.add_subparsers(dest="target_data", title="Enrichment Targets", required=True)

    # Enrich Timeline (from ActivityWatch)
    parser_enrich_timeline = enrich_subparsers.add_parser(
        "timeline",
        help="Generate an enriched timeline from processed ActivityWatch data using an LLM."
    )
    parser_enrich_timeline.add_argument(
        "--day",
        type=lambda s: date.fromisoformat(s) if s else None,
        help="Day to enrich in YYYY-MM-DD format. Defaults to yesterday."
    )
    parser_enrich_timeline.add_argument(
        "--days-ago",
        type=int,
        default=None,
        help="Enrich data for this many days ago. Overrides --day."
    )
    parser_enrich_timeline.add_argument(
        "--force-llm",
        action="store_true",
        help="Force re-querying the LLM, ignoring cached LLM responses. "
             "Can also be set via LIFELOG_ENRICHMENT_FORCE_LLM."
    )
    parser_enrich_timeline.add_argument(
        "--force-processing",
        action="store_true",
        help="Force re-processing the day even if an output file exists. "
             "Can also be set via LIFELOG_ENRICHMENT_FORCE_PROCESSING_ALL."
    )
    def handle_enrich_timeline(args_ns, current_settings):
        target_day_enrich: date
        if args_ns.days_ago is not None:
            target_day_enrich = date.today() - timedelta(days=args_ns.days_ago)
        elif args_ns.day:
            target_day_enrich = args_ns.day
        else:
            target_day_enrich = date.today() - timedelta(days=1)

        # Update settings based on CLI flags before passing to the function
        if args_ns.force_llm:
            current_settings.enrichment_force_llm = True
        if args_ns.force_processing:
            current_settings.enrichment_force_processing_all = True
            
        log.info(f"CLI: Initiating timeline enrichment for {target_day_enrich}...")
        run_enrichment_for_day(target_day_enrich, current_settings)

    parser_enrich_timeline.set_defaults(func=handle_enrich_timeline)


    # --- Summarize Subcommand (Placeholder - assuming summarize_day exists) ---
    # parser_summarize = subparsers.add_parser(
    #     "summarize",
    #     help="Generate summaries from processed data."
    # )
    # summary_subparsers = parser_summarize.add_subparsers(dest="summary_type", title="Summary Types", required=True)

    # parser_summarize_daily = summary_subparsers.add_parser(
    #     "daily",
    #     help="Generate a daily summary report."
    # )
    # parser_summarize_daily.add_argument(
    #     "--day",
    #     type=lambda s: date.fromisoformat(s) if s else None,
    #     help="Day to summarize in YYYY-MM-DD format. Defaults to yesterday."
    # )
    # parser_summarize_daily.add_argument(
    #     "--days-ago",
    #     type=int,
    #     default=None,
    #     help="Summarize data for this many days ago. Overrides --day."
    # )
    # parser_summarize_daily.add_argument(
    #     "--force",
    #     action="store_true",
    #     help="Force regeneration of the summary."
    # )
    # def handle_summarize_daily(args_ns, current_settings):
    #     target_day_summary: date
    #     if args_ns.days_ago is not None:
    #         target_day_summary = date.today() - timedelta(days=args_ns.days_ago)
    #     elif args_ns.day:
    #         target_day_summary = args_ns.day
    #     else:
    #         target_day_summary = date.today() - timedelta(days=1)
        
    #     log.info(f"CLI: Initiating daily summary for {target_day_summary}...")
    #     summarize_day(day=target_day_summary, force=args_ns.force, settings=current_settings) # Pass settings if needed

    # parser_summarize_daily.set_defaults(func=handle_summarize_daily)

    # --- Parse Arguments ---
    args = parser.parse_args()

    # Handle global debug flag
    if args.debug:
        logging.getLogger("LifeLog").setLevel(logging.DEBUG) # Set base LifeLog logger
        # Set all handlers of the root logger to DEBUG
        root_logger = logging.getLogger()
        root_logger.setLevel(logging.DEBUG)
        for handler in root_logger.handlers:
            handler.setLevel(logging.DEBUG)
        log.debug("Debug logging enabled via CLI.")


    # Execute the subcommand function
    if hasattr(args, "func"):
        args.func(args, settings) # Pass settings to handler functions
    else:
        # This case should ideally be caught by 'required=True' on subparsers
        # or by checking if args.command is None if no command is given
        parser.print_help()
        sys.exit(1)

if __name__ == "__main__":
    main()