import sys
from pathlib import Path
import pytest

# Make sure LifeLog/ is on PYTHONPATH
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
