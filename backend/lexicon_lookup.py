"""Lexicon pattern matching — mirrors exet-lexicon.js getLexChoices behaviour."""

from __future__ import annotations

import sqlite3

LETTER_SET = set("ABCDEFGHIJKLMNOPQRSTUVWXYZ")
SPACES = {" ", "\t", "\r", "\n", ".", ",", "!"}
PUNCT = {"-", "'"}


def parts_of(s: str) -> list[str]:
    out: list[str] = []
    for ch in s:
        out.append(" " if ch in SPACES else ch)
    parts: list[str] = []
    for ch in out:
        if ch == " " and (not parts or parts[-1] == " "):
            continue
        parts.append(ch)
    return parts


def lexkey(partial_sol: str) -> list[str]:
    key: list[str] = []
    if not partial_sol:
        return key
    for ch in parts_of(partial_sol.upper()):
        if ch in LETTER_SET or ch == "?":
            key.append(ch)
    return key


def generalize_key(key: str) -> str:
    parts = parts_of(key)
    for i in range(len(parts) - 1, -1, -1):
        if parts[i] != "?":
            return "".join(parts[:i]) + "?" + "".join(parts[i + 1 :])
    return key


def key_matches_phrase(key: list[str], phrase_normalized: str) -> bool:
    phrase_key = lexkey(phrase_normalized)
    if len(phrase_key) != len(key):
        return False
    for kc, pc in zip(key, phrase_key):
        if kc != "?" and kc != pc:
            return False
    return True


def is_proper_noun(form: str) -> bool:
    parts = parts_of(form)
    if len(parts) <= 1:
        return False
    first = parts[0]
    if not (first.upper() == first and parts[1] != "-"):
        return False
    if form.startswith("I ") and len(parts) > 2 and parts[2].upper() != parts[2]:
        return False
    if form.startswith("I'm ") and len(parts) > 4 and parts[4].upper() != parts[4]:
        return False
    if form.startswith("I'll ") and len(parts) > 5 and parts[5].upper() != parts[5]:
        return False
    return True


def _fetch_pattern_rows(
    conn: sqlite3.Connection,
    lexicon_id: str,
    pattern: str,
    min_score: float,
    no_proper_nouns: bool,
    index_limit: int,
) -> list[sqlite3.Row]:
    sql = """
        SELECT e.id, e.form, e.normalized, e.score, e.is_proper_noun
        FROM lexicon_pattern p
        JOIN lexicon_entries e ON e.id = p.entry_id
        WHERE p.lexicon_id = ? AND p.pattern = ? AND e.score >= ?
    """
    params: list[object] = [lexicon_id, pattern, min_score]
    if no_proper_nouns:
        sql += " AND e.is_proper_noun = 0"
    if index_limit > 0:
        sql += " AND e.id < ?"
        params.append(index_limit)
    sql += " ORDER BY e.score DESC, e.id ASC"
    return conn.execute(sql, params).fetchall()


def get_fill_choices(
    conn: sqlite3.Connection,
    lexicon_id: str,
    partial_sol: str,
    *,
    limit: int = 0,
    min_score: float = 0.0,
    no_proper_nouns: bool = False,
    index_limit: int = 0,
    try_rev: bool = False,
    exclude_ids: set[int] | None = None,
) -> list[dict]:
    """Return fill candidates as {id, form, score, reversed}."""
    key = lexkey(partial_sol)
    if not key:
        return []

    exclude_ids = exclude_ids or set()
    loops: list[list[str]] = [key]
    if try_rev:
        loops.append(list(reversed(key)))

    seen: set[int] = set()
    out: list[dict] = []

    for loop_key in loops:
        reversed_flag = loop_key is not loops[0]
        gkey = "".join(loop_key)
        while True:
            rows = _fetch_pattern_rows(
                conn, lexicon_id, gkey, min_score, no_proper_nouns, index_limit
            )
            if rows:
                for row in rows:
                    entry_id = row["id"]
                    loop_id = -entry_id if reversed_flag else entry_id
                    if loop_id in seen or entry_id in exclude_ids:
                        continue
                    if not key_matches_phrase(loop_key, row["normalized"]):
                        continue
                    seen.add(loop_id)
                    out.append(
                        {
                            "id": loop_id,
                            "form": row["form"],
                            "score": row["score"],
                            "reversed": reversed_flag,
                        }
                    )
                    if limit > 0 and len(out) >= limit:
                        return out
                return out
            ngkey = generalize_key(gkey)
            if ngkey == gkey:
                break
            gkey = ngkey
    return out


def get_anagrams(
    conn: sqlite3.Connection,
    lexicon_id: str,
    phrase: str,
    *,
    limit: int = 0,
    min_score: float = 0.0,
) -> list[dict]:
    letters = [ch for ch in parts_of(phrase.upper()) if ch in LETTER_SET]
    if not letters:
        return []
    anagram_key = "".join(sorted(letters))
    sql = """
        SELECT id, form, score
        FROM lexicon_entries
        WHERE lexicon_id = ? AND anagram_key = ? AND score >= ?
        ORDER BY score DESC, id ASC
    """
    params: list[object] = [lexicon_id, anagram_key, min_score]
    if limit > 0:
        sql += " LIMIT ?"
        params.append(limit)
    rows = conn.execute(sql, params).fetchall()
    return [{"id": r["id"], "form": r["form"], "score": r["score"]} for r in rows]
