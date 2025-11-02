#!/usr/bin/env python3
import argparse
import importlib
import io
import json
import os
import sys
from pathlib import Path

"""
Worker entrypoint for isolated actor execution.

Protocol:
- Parent launches this script with --ext-dir and --actor <slug>.
- This script prepends ext-dir to sys.path, imports `external_actor` module
  from the extension directory (convention), and calls its `run(slug, data)`.
- The extension's external_actor.run returns an actions dict which we print as JSON.

Security:
- If LIFELOG_NO_NETWORK=1, sitecustomize in this package disables socket.create_connection.
- No DB access is available here; the extension should emit actions for the parent to apply.
"""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--ext-dir', required=True)
    ap.add_argument('--actor', required=True)
    args = ap.parse_args()

    ext_dir = Path(args.ext_dir)
    if not ext_dir.exists():
        print(json.dumps({"error": "ext_dir not found"}), file=sys.stdout)
        sys.exit(2)

    sys.path.insert(0, str(ext_dir))

    try:
        mod = importlib.import_module('external_actor')
    except Exception as e:
        print(json.dumps({"error": f"failed to import external_actor: {e}"}), file=sys.stdout)
        sys.exit(3)

    data = sys.stdin.read()
    try:
        payload = json.loads(data)
    except Exception as e:
        print(json.dumps({"error": f"invalid input json: {e}"}), file=sys.stdout)
        sys.exit(4)

    try:
        result = mod.run(args.actor, payload)
    except Exception as e:
        print(json.dumps({"error": f"actor error: {e}"}), file=sys.stdout)
        sys.exit(5)

    try:
        print(json.dumps(result or {}), file=sys.stdout)
    except Exception as e:
        print(json.dumps({"error": f"result encoding error: {e}"}), file=sys.stdout)
        sys.exit(6)


if __name__ == '__main__':
    main()
