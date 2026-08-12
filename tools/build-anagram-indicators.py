#!/usr/bin/env python3
"""Build offline anagram indicator list (wrapper around build-indicator-lists.py)."""

import subprocess
import sys
from pathlib import Path

if __name__ == "__main__":
    script = Path(__file__).resolve().parent / "build-indicator-lists.py"
    sys.exit(subprocess.call([sys.executable, str(script), "anagram"]))
