"""Mutate ComboList: add/remove entries in SQLite and combolist.txt."""

from __future__ import annotations

import re
import sqlite3
from pathlib import Path

from backend.config import WORDLISTS_DIR
from backend.lexicon_lookup import is_proper_noun

COMBOLIST_TXT = WORDLISTS_DIR / "combolist.txt"
REMOVALS_TXT = WORDLISTS_DIR / "_sources" / "combolist-removals.txt"
ADDITIONS_TXT = WORDLISTS_DIR / "_sources" / "combolist-additions.txt"

_LETTER_RE = re.compile(r"[^A-Za-z]+")
WILDIZE_ALL_BEYOND = 10
DEFAULT_ADD_SCORE = 100.0
MAX_ENTRY_LETTERS = 75


def normalize_form(form: str) -> str:
    """Letters-only uppercase key, matching lexicon build normalization."""
    return _LETTER_RE.sub("", form).upper()


def clean_surface(form: str) -> str:
    """Normalize user input for storage in combolist.txt."""
    cleaned = " ".join(str(form).replace(";", " ").split())
    return cleaned


def _line_form(line: str) -> str:
    return line.split(";", 1)[0].strip()


def _rewrite_list_file(path: Path, key: str, *, add_line: str | None = None) -> None:
    """Drop lines matching normalized key; optionally append add_line."""
    path.parent.mkdir(parents=True, exist_ok=True)
    lines: list[str] = []
    if path.is_file():
        for raw in path.read_text(encoding="utf-8", errors="replace").splitlines(True):
            stripped = raw.strip()
            if not stripped:
                continue
            if normalize_form(_line_form(stripped)) == key:
                continue
            lines.append(raw if raw.endswith("\n") else raw + "\n")
    if add_line is not None:
        lines.append(add_line if add_line.endswith("\n") else add_line + "\n")
    path.write_text("".join(lines), encoding="utf-8")


def append_removal(form: str) -> None:
    """Record a durable removal so sync cannot resurrect the word."""
    key = normalize_form(form)
    if not key:
        return
    _rewrite_list_file(REMOVALS_TXT, key, add_line=form.strip())
    # A removal cancels any prior durable addition.
    if ADDITIONS_TXT.is_file():
        _rewrite_list_file(ADDITIONS_TXT, key, add_line=None)


def append_addition(form: str, score: float) -> None:
    """Record a durable addition so sync keeps the word."""
    key = normalize_form(form)
    if not key:
        return
    surface = clean_surface(form)
    _rewrite_list_file(ADDITIONS_TXT, key, add_line=f"{surface};{score:g}")
    # An addition cancels any prior durable removal.
    if REMOVALS_TXT.is_file():
        _rewrite_list_file(REMOVALS_TXT, key, add_line=None)


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


def append_to_combolist_txt(form: str, score: float) -> bool:
    """Append form;score if not already present. Returns True if appended."""
    key = normalize_form(form)
    if not key:
        return False
    surface = clean_surface(form)
    COMBOLIST_TXT.parent.mkdir(parents=True, exist_ok=True)
    if COMBOLIST_TXT.is_file():
        for raw in COMBOLIST_TXT.read_text(encoding="utf-8", errors="replace").splitlines():
            if normalize_form(_line_form(raw)) == key:
                return False
    with COMBOLIST_TXT.open("a", encoding="utf-8") as fh:
        fh.write(f"{surface};{score:g}\n")
    return True


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


def apply_additions_file(combolist_path: Path, additions_path: Path) -> int:
    """Append missing addition lines to combolist_path. Returns lines added."""
    if not combolist_path.is_file() or not additions_path.is_file():
        return 0
    existing: set[str] = set()
    for raw in combolist_path.read_text(encoding="utf-8", errors="replace").splitlines():
        n = normalize_form(_line_form(raw))
        if n:
            existing.add(n)
    added = 0
    with combolist_path.open("a", encoding="utf-8") as out:
        for raw in additions_path.read_text(encoding="utf-8", errors="replace").splitlines():
            stripped = raw.strip()
            if not stripped or stripped.startswith("#"):
                continue
            form = _line_form(stripped)
            key = normalize_form(form)
            if not key or key in existing:
                continue
            score = DEFAULT_ADD_SCORE
            if ";" in stripped:
                try:
                    score = float(stripped.split(";", 1)[1].strip())
                except ValueError:
                    score = DEFAULT_ADD_SCORE
            out.write(f"{clean_surface(form)};{score:g}\n")
            existing.add(key)
            added += 1
    return added


def patterns_for_normalized(normalized: str) -> list[str]:
    """Pattern keys for fill lookup, matching import-wordlists indexing."""
    parts = [
        ch if i < WILDIZE_ALL_BEYOND else "?"
        for i, ch in enumerate(normalized)
    ]
    n = min(len(parts), WILDIZE_ALL_BEYOND)
    keys: list[str] = []
    if n <= 7:
        limit = 1 << n
        for pattern in range(limit):
            variant = parts[:]
            for i in range(n):
                if pattern & (1 << i):
                    variant[i] = "?"
            keys.append("".join(variant))
        return keys
    keys.append("".join(parts))
    variant = parts[:]
    for i in range(n - 1, -1, -1):
        variant[i] = "?"
        keys.append("".join(variant))
    return keys


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
        txt_removed = remove_from_combolist_txt(form)
        if txt_removed:
            append_removal(form)
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


def add_lexicon_entry(
    db: sqlite3.Connection,
    lexicon_id: str,
    form: str,
    score: float = DEFAULT_ADD_SCORE,
) -> dict:
    """
    Insert a ComboList entry into SQLite + combolist.txt (+ durable additions).

    Idempotent on normalized form: if it already exists, bumps score when the
    new score is higher. Caller must commit.
    """
    surface = clean_surface(form)
    key = normalize_form(surface)
    if not key:
        raise ValueError("empty form")
    if len(key) > MAX_ENTRY_LETTERS:
        raise ValueError(f"form too long ({len(key)} letters; max {MAX_ENTRY_LETTERS})")
    if score < 0:
        raise ValueError("score must be non-negative")

    existing = db.execute(
        "SELECT id, form, score FROM lexicon_entries "
        "WHERE lexicon_id = ? AND normalized = ?",
        (lexicon_id, key),
    ).fetchall()

    append_addition(surface, score)
    txt_added = append_to_combolist_txt(surface, score)

    if existing:
        eid = int(existing[0]["id"])
        old_score = float(existing[0]["score"])
        bumped = False
        if score > old_score + 1e-9:
            db.execute(
                "UPDATE lexicon_entries SET score = ? WHERE id = ?",
                (score, eid),
            )
            bumped = True
        count_row = db.execute(
            "SELECT entry_count FROM lexicons WHERE id = ?", (lexicon_id,)
        ).fetchone()
        return {
            "added": 0,
            "already_present": True,
            "bumped": bumped,
            "id": eid,
            "form": str(existing[0]["form"]),
            "normalized": key,
            "score": max(score, old_score),
            "combolist_line_added": txt_added,
            "entry_count": int(count_row["entry_count"]) if count_row else None,
        }

    anagram_key = "".join(sorted(key))
    cur = db.execute(
        """
        INSERT INTO lexicon_entries(
          lexicon_id, form, normalized, letter_count, score, anagram_key, is_proper_noun
        ) VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            lexicon_id,
            surface,
            key,
            len(key),
            float(score),
            anagram_key,
            1 if is_proper_noun(surface) else 0,
        ),
    )
    eid = int(cur.lastrowid)
    patterns = patterns_for_normalized(key)
    db.executemany(
        "INSERT OR IGNORE INTO lexicon_pattern(lexicon_id, pattern, entry_id) "
        "VALUES (?, ?, ?)",
        [(lexicon_id, pattern, eid) for pattern in patterns],
    )
    db.execute(
        "UPDATE lexicons SET entry_count = ("
        "  SELECT COUNT(*) FROM lexicon_entries WHERE lexicon_id = ?"
        "), built_at = datetime('now') WHERE id = ?",
        (lexicon_id, lexicon_id),
    )
    count_row = db.execute(
        "SELECT entry_count FROM lexicons WHERE id = ?", (lexicon_id,)
    ).fetchone()
    return {
        "added": 1,
        "already_present": False,
        "bumped": False,
        "id": eid,
        "form": surface,
        "normalized": key,
        "score": float(score),
        "patterns": len(patterns),
        "combolist_line_added": txt_added,
        "entry_count": int(count_row["entry_count"]) if count_row else None,
    }


def rename_lexicon_entry(
    db: sqlite3.Connection,
    lexicon_id: str,
    old_form: str,
    new_form: str,
    score: float | None = None,
) -> dict:
    """
    Replace old_form with new_form in ComboList.

    Preserves score from the old entry when score is omitted. Caller must commit.
    """
    old_key = normalize_form(old_form)
    new_surface = clean_surface(new_form)
    new_key = normalize_form(new_surface)
    if not old_key:
        raise ValueError("empty old form")
    if not new_key:
        raise ValueError("empty new form")

    if old_key == new_key:
        # Same letters: still allow surface-form / score refresh via add path.
        old_rows = db.execute(
            "SELECT score FROM lexicon_entries "
            "WHERE lexicon_id = ? AND normalized = ?",
            (lexicon_id, old_key),
        ).fetchall()
        use_score = float(score) if score is not None else (
            float(old_rows[0]["score"]) if old_rows else DEFAULT_ADD_SCORE
        )
        # Delete then re-add so surface form and patterns stay consistent.
        deleted = delete_lexicon_entry(db, lexicon_id, old_form)
        added = add_lexicon_entry(db, lexicon_id, new_surface, score=use_score)
        return {
            "renamed": True,
            "same_normalized": True,
            "old_form": old_form,
            "old_normalized": old_key,
            "deleted": deleted,
            "added": added,
        }

    old_rows = db.execute(
        "SELECT score FROM lexicon_entries "
        "WHERE lexicon_id = ? AND normalized = ?",
        (lexicon_id, old_key),
    ).fetchall()
    use_score = float(score) if score is not None else (
        float(old_rows[0]["score"]) if old_rows else DEFAULT_ADD_SCORE
    )

    deleted = delete_lexicon_entry(db, lexicon_id, old_form)
    added = add_lexicon_entry(db, lexicon_id, new_surface, score=use_score)
    return {
        "renamed": True,
        "same_normalized": False,
        "old_form": old_form,
        "old_normalized": old_key,
        "deleted": deleted,
        "added": added,
    }
