#!/usr/bin/env python3
"""Test script to verify CLI functionality"""

import sys
import os
from pathlib import Path

# Add the project root to the path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from LifeLog.cli import main

if __name__ == "__main__":
    # Test the enrich command help
    sys.argv = ["lifelog", "enrich", "--help"]
    try:
        main()
    except SystemExit as e:
        print(f"CLI exited with code: {e.code}")
