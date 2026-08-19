"""Git-backed puzzle storage in the ipuz_files submodule."""

from __future__ import annotations

import base64
import subprocess
from datetime import datetime, timezone
from pathlib import Path

from backend.config import IPUZ_FILES_DIR

KINDS = ("drafts", "puzzles")
ALLOWED_EXTENSIONS = (".puz", ".ipuz", ".json")


class PuzzleGitError(Exception):
    pass


def _run_git(*args: str, check: bool = True) -> str:
    if not IPUZ_FILES_DIR.is_dir():
        raise PuzzleGitError(
            f"ipuz_files directory not found at {IPUZ_FILES_DIR}. "
            "Run: git submodule update --init ipuz_files"
        )
    result = subprocess.run(
        ["git", *args],
        cwd=IPUZ_FILES_DIR,
        capture_output=True,
        text=True,
        timeout=120,
    )
    if check and result.returncode != 0:
        err = (result.stderr or result.stdout or "").strip()
        raise PuzzleGitError(err or f"git {' '.join(args)} failed")
    return (result.stdout or "").strip()


def status() -> dict:
    if not IPUZ_FILES_DIR.is_dir():
        return {
            "ok": False,
            "path": str(IPUZ_FILES_DIR),
            "error": "ipuz_files directory not found",
        }
    try:
        branch = _run_git("rev-parse", "--abbrev-ref", "HEAD")
        head = _run_git("rev-parse", "--short", "HEAD")
        dirty = bool(_run_git("status", "--porcelain", check=False))
        return {
            "ok": True,
            "path": str(IPUZ_FILES_DIR),
            "branch": branch,
            "head": head,
            "dirty": dirty,
        }
    except PuzzleGitError as exc:
        return {"ok": False, "path": str(IPUZ_FILES_DIR), "error": str(exc)}


def sync() -> dict:
    before = _run_git("rev-parse", "HEAD")
    _run_git("pull", "--ff-only")
    after = _run_git("rev-parse", "HEAD")
    return {
        "ok": True,
        "pulled": before != after,
        "head": _run_git("rev-parse", "--short", "HEAD"),
    }


def _validate_kind(kind: str) -> str:
    if kind not in KINDS:
        raise PuzzleGitError(f"Invalid kind: {kind!r} (expected drafts or puzzles)")
    return kind


def _validate_name(name: str) -> str:
    name = Path(name).name
    if not name or len(name) > 200:
        raise PuzzleGitError("Invalid filename")
    if name != name.strip() or ".." in name or "/" in name or "\\" in name:
        raise PuzzleGitError("Invalid filename")
    if Path(name).suffix.lower() not in ALLOWED_EXTENSIONS:
        raise PuzzleGitError("Filename must end with .puz, .ipuz, or .json")
    return name


def list_files() -> dict:
    sync()
    out: dict[str, list[dict]] = {kind: [] for kind in KINDS}
    for kind in KINDS:
        folder = IPUZ_FILES_DIR / kind
        if not folder.is_dir():
            folder.mkdir(parents=True, exist_ok=True)
            continue
        for path in sorted(folder.iterdir()):
            if not path.is_file():
                continue
            if path.suffix.lower() not in ALLOWED_EXTENSIONS:
                continue
            stat = path.stat()
            out[kind].append(
                {
                    "name": path.name,
                    "size": stat.st_size,
                    "modified": datetime.fromtimestamp(
                        stat.st_mtime, tz=timezone.utc
                    ).isoformat(),
                }
            )
    return out


def read_file(kind: str, name: str) -> dict:
    sync()
    kind = _validate_kind(kind)
    name = _validate_name(name)
    path = IPUZ_FILES_DIR / kind / name
    if not path.is_file():
        raise PuzzleGitError(f"File not found: {kind}/{name}")
    data = path.read_bytes()
    return {
        "kind": kind,
        "name": name,
        "size": len(data),
        "content_base64": base64.b64encode(data).decode("ascii"),
    }


def save_file(kind: str, name: str, content_base64: str) -> dict:
    kind = _validate_kind(kind)
    name = _validate_name(name)
    try:
        content = base64.b64decode(content_base64, validate=True)
    except Exception as exc:
        raise PuzzleGitError(f"Invalid base64 content: {exc}") from exc
    if not content:
        raise PuzzleGitError("Empty file content")

    folder = IPUZ_FILES_DIR / kind
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / name
    path.write_bytes(content)

    rel = f"{kind}/{name}"
    _run_git("add", rel)
    commit_msg = f"Save {rel}"
    commit = subprocess.run(
        ["git", "commit", "-m", commit_msg],
        cwd=IPUZ_FILES_DIR,
        capture_output=True,
        text=True,
        timeout=120,
    )
    committed = commit.returncode == 0
    if not committed and "nothing to commit" not in (commit.stdout + commit.stderr):
        err = (commit.stderr or commit.stdout or "").strip()
        raise PuzzleGitError(err or "git commit failed")

    _run_git("push")
    return {
        "ok": True,
        "path": rel,
        "committed": committed,
        "head": _run_git("rev-parse", "--short", "HEAD"),
    }
