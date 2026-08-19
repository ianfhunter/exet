#!/usr/bin/env bash
# Start the Exet SQLite data API (FastAPI + uvicorn).
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
BACKEND="$ROOT/backend"
VENV="$BACKEND/.venv"
PYTHON="$VENV/bin/python"
DB="$BACKEND/data/exet.sqlite"
HOST="${EXET_HOST:-127.0.0.1}"
PORT="${EXET_PORT:-8000}"

cd "$ROOT"

venv_ok() {
  [[ -x "$PYTHON" ]] && "$PYTHON" -c "import sys" >/dev/null 2>&1
}

if ! venv_ok; then
  if [[ -d "$VENV" ]]; then
    echo "Removing broken virtualenv at backend/.venv (stale paths — recreate after a move) ..."
    rm -rf "$VENV"
  fi
  echo "Creating virtualenv at backend/.venv ..."
  python3 -m venv "$VENV"
  venv_ok || { echo "Failed to create virtualenv at $VENV" >&2; exit 1; }
fi

"$PYTHON" -m pip install -q -r "$BACKEND/requirements.txt"

if [[ ! -f "$DB" ]]; then
  echo "Warning: $DB not found."
  echo "Build it with: python backend/build/build_all.py"
  echo
fi

echo "Starting Exet data server at http://${HOST}:${PORT}"
exec "$PYTHON" -m uvicorn backend.main:app --reload --host "$HOST" --port "$PORT"
