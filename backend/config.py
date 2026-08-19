"""Paths and settings for the Exet data backend."""

from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent
EXET_DIR = BACKEND_DIR.parent
EXET_TOOLS_DIR = EXET_DIR / "tools"
WORDLISTS_DIR = EXET_DIR / "wordlists"

DATA_DIR = BACKEND_DIR / "data"
DB_PATH = DATA_DIR / "exet.sqlite"
IPUZ_FILES_DIR = EXET_DIR / "ipuz_files"

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8000
