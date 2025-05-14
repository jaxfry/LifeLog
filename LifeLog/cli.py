# LifeLog/cli.py
import argparse
from datetime import date
from ingestion import activitywatch as aw

def _ingest_activitywatch(ns):
    aw.ingest(ns.day)

def main():
    parser = argparse.ArgumentParser(prog="lifelog")
    sub = parser.add_subparsers(dest="cmd")

    p_aw = sub.add_parser("ingest-activitywatch")
    p_aw.add_argument("--day", type=lambda s: date.fromisoformat(s),
                      help="YYYY-MM-DD (default: yesterday)")
    p_aw.set_defaults(func=_ingest_activitywatch)

    ns = parser.parse_args()
    if hasattr(ns, "func"):
        ns.func(ns)
    else:
        parser.print_help()

if __name__ == "__main__":
    main()
