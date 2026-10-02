"""Filesystem store for Exet localStorage backup JSON files."""

from __future__ import annotations

import re
from datetime import datetime, timezone
from pathlib import Path

from backend.config import DATA_DIR

BACKUPS_DIR = DATA_DIR / "exet-backups"
KEEP_BACKUPS = 5
_SAFE_NAME_RE = re.compile(r"[^A-Za-z0-9._-]+")


def backups_dir() -> Path:
    BACKUPS_DIR.mkdir(parents=True, exist_ok=True)
    return BACKUPS_DIR


def sanitize_backup_name(name: str | None) -> str:
    if not name or not name.strip():
        stamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H-%M-%S-%f")[:-3] + "Z"
        return f"exet-backup-{stamp}.json"
    base = Path(name.strip()).name
    base = base.replace(":", "-")
    base = _SAFE_NAME_RE.sub("_", base)
    if not base.lower().endswith(".json"):
        base += ".json"
    if not base.startswith("exet-backup-"):
        base = "exet-backup-" + base
    return base


def list_backups() -> list[dict]:
    root = backups_dir()
    items = []
    for path in root.glob("exet-backup-*.json"):
        if not path.is_file():
            continue
        stat = path.stat()
        items.append(
            {
                "name": path.name,
                "size": stat.st_size,
                "mtime": stat.st_mtime,
            }
        )
    items.sort(key=lambda row: row["mtime"], reverse=True)
    return items


def prune_backups(keep: int = KEEP_BACKUPS) -> list[str]:
    """Delete older backups beyond `keep`. Returns deleted filenames."""
    items = list_backups()
    deleted: list[str] = []
    for row in items[max(0, keep) :]:
        path = backups_dir() / row["name"]
        try:
            path.unlink(missing_ok=True)
            deleted.append(row["name"])
        except OSError:
            continue
    return deleted


def save_backup(content: str, name: str | None = None, keep: int = KEEP_BACKUPS) -> dict:
    if content is None or not str(content).strip():
        raise ValueError("empty backup content")
    filename = sanitize_backup_name(name)
    path = backups_dir() / filename
    path.write_text(content, encoding="utf-8")
    deleted = prune_backups(keep=keep)
    kept = list_backups()
    return {
        "ok": True,
        "name": filename,
        "size": path.stat().st_size,
        "kept": len(kept),
        "backups": kept,
        "pruned": deleted,
    }
