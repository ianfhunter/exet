"""Mutate ComboList: remove entries from SQLite and combolist.txt."""

from __future__ import annotations

import re
import sqlite3
from pathlib import Path

from backend.config import WORDLISTS_DIR

COMBOLIST_TXT = WORDLISTS_DIR / "combolist.txt"
REMOVALS_TXT = WORDLISTS_DIR / "_sources" / "combolist-removals.txt"

_LETTER_RE = re.compile(r"[^A-Za-z]+")


def normalize_form(form: str) -> str:
    """Letters-only uppercase key, matching lexicon build normalization."""
    return _LETTER_RE.sub("", form).upper()


def _line_form(line: str) -> str:
    return line.split(";", 1)[0].strip()


def append_removal(form: str) -> None:
    """Record a durable removal so sync cannot resurrect the word."""
    key = normalize_form(form)
    if not key:
        return
    REMOVALS_TXT.parent.mkdir(parents=True, exist_ok=True)
    existing: set[str] = set()
    if REMOVALS_TXT.is_file():
        for raw in REMOVALS_TXT.read_text(encoding="utf-8", errors="replace").splitlines():
            n = normalize_form(raw.strip())
            if n:
                existing.add(n)
    if key in existing:
        return
    with REMOVALS_TXT.open("a", encoding="utf-8") as fh:
        fh.write(form.strip() + "\n")


def remove_from_combolist_txt(form: str) -> int:
    """Drop matching surface lines from combolist.txt. Returns lines removed."""
    if not COMBOLIST_TXT.is_file():
        return 0
    key = normalize_form(form)
    if not key:
        return 0
    lines = COMBOLIST_TXT.read_text(encoding="utf-8", errors="replace").splitlines(True)
    kept: list[str] = []
    removed = 0
    for line in lines:
        stripped = line.strip()
        if not stripped:
            kept.append(line)
            continue
        if normalize_form(_line_form(stripped)) == key:
            removed += 1
            continue
        kept.append(line)
    if removed:
        COMBOLIST_TXT.write_text("".join(kept), encoding="utf-8")
    return removed


def apply_removals_file(combolist_path: Path, removals_path: Path) -> int:
    """Filter combolist_path using removals_path. Returns lines removed."""
    if not combolist_path.is_file() or not removals_path.is_file():
        return 0
    keys: set[str] = set()
    for raw in removals_path.read_text(encoding="utf-8", errors="replace").splitlines():
        n = normalize_form(raw.strip())
        if n:
            keys.add(n)
    if not keys:
        return 0
    lines = combolist_path.read_text(encoding="utf-8", errors="replace").splitlines(True)
    kept: list[str] = []
    removed = 0
    for line in lines:
        stripped = line.strip()
        if stripped and normalize_form(_line_form(stripped)) in keys:
            removed += 1
            continue
        kept.append(line)
    if removed:
        combolist_path.write_text("".join(kept), encoding="utf-8")
    return removed


def delete_lexicon_entry(db: sqlite3.Connection, lexicon_id: str, form: str) -> dict:
    """
    Delete all entries in lexicon_id whose normalized form matches.

    Also updates combolist.txt and the durable removals list when the lexicon
    is ComboList. Caller must commit the DB connection.
    """
    key = normalize_form(form)
    if not key:
        raise ValueError("empty form")

    rows = db.execute(
        "SELECT id, form, normalized FROM lexicon_entries "
        "WHERE lexicon_id = ? AND normalized = ?",
        (lexicon_id, key),
    ).fetchall()
    if not rows:
        # Still record removal + scrub txt so a later rebuild stays clean.
        append_removal(form)
        txt_removed = remove_from_combolist_txt(form)
        return {
            "deleted": 0,
            "forms": [],
            "normalized": key,
            "combolist_lines_removed": txt_removed,
        }

    ids = [int(r["id"]) for r in rows]
    forms = [str(r["form"]) for r in rows]
    placeholders = ",".join("?" * len(ids))
    db.execute(
        f"DELETE FROM lexicon_pattern WHERE lexicon_id = ? AND entry_id IN ({placeholders})",
        (lexicon_id, *ids),
    )
    db.execute(
        f"DELETE FROM lexicon_entries WHERE id IN ({placeholders})",
        ids,
    )
    db.execute(
        "UPDATE lexicons SET entry_count = ("
        "  SELECT COUNT(*) FROM lexicon_entries WHERE lexicon_id = ?"
        ") WHERE id = ?",
        (lexicon_id, lexicon_id),
    )

    append_removal(forms[0] if forms else form)
    txt_removed = remove_from_combolist_txt(forms[0] if forms else form)

    count_row = db.execute(
        "SELECT entry_count FROM lexicons WHERE id = ?", (lexicon_id,)
    ).fetchone()
    return {
        "deleted": len(ids),
        "forms": forms,
        "normalized": key,
        "combolist_lines_removed": txt_removed,
        "entry_count": int(count_row["entry_count"]) if count_row else None,
    }
