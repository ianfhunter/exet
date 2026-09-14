#!/usr/bin/env python3
"""Server-side lexicon helpers: substring search + batched pattern fill."""

from __future__ import annotations

import re
import sqlite3

from backend.lexicon_lookup import (
    LETTER_SET,
    get_fill_choices,
    parts_of,
)

_MODE_OK = {"contains", "prefix", "suffix", "exact"}


def _normalize_query(q: str) -> str:
    return "".join(ch for ch in parts_of(q.upper()) if ch in LETTER_SET)


def search_entries(
    conn: sqlite3.Connection,
    lexicon_id: str,
    q: str,
    *,
    mode: str = "contains",
    limit: int = 200,
    min_score: float = 0.0,
    max_score: float | None = None,
    no_proper_nouns: bool = False,
    min_len: int = 0,
    max_len: int = 0,
) -> list[dict]:
    """Substring / prefix / suffix / exact search over normalized forms."""
    needle = _normalize_query(q)
    if not needle:
        return []
    mode = (mode or "contains").lower()
    if mode not in _MODE_OK:
        mode = "contains"

    if mode == "exact":
        like = needle
        op = "="
        like_param = needle
    elif mode == "prefix":
        op = "LIKE"
        like_param = needle + "%"
    elif mode == "suffix":
        op = "LIKE"
        like_param = "%" + needle
    else:
        op = "LIKE"
        like_param = "%" + needle + "%"

    sql = f"""
        SELECT id, form, normalized, score, letter_count, is_proper_noun
        FROM lexicon_entries
        WHERE lexicon_id = ?
          AND score >= ?
          AND normalized {op} ?
    """
    params: list[object] = [lexicon_id, min_score, like_param]
    if max_score is not None:
        sql += " AND score <= ?"
        params.append(max_score)
    if no_proper_nouns:
        sql += " AND is_proper_noun = 0"
    if min_len > 0:
        sql += " AND letter_count >= ?"
        params.append(min_len)
    if max_len > 0:
        sql += " AND letter_count <= ?"
        params.append(max_len)
    sql += " ORDER BY score DESC, letter_count ASC, id ASC"
    if limit > 0:
        sql += " LIMIT ?"
        params.append(limit)

    rows = conn.execute(sql, params).fetchall()
    return [
        {
            "id": r["id"] if isinstance(r, sqlite3.Row) else r[0],
            "form": r["form"] if isinstance(r, sqlite3.Row) else r[1],
            "normalized": r["normalized"] if isinstance(r, sqlite3.Row) else r[2],
            "score": r["score"] if isinstance(r, sqlite3.Row) else r[3],
            "letter_count": r["letter_count"] if isinstance(r, sqlite3.Row) else r[4],
            "is_proper_noun": bool(
                r["is_proper_noun"] if isinstance(r, sqlite3.Row) else r[5]
            ),
        }
        for r in rows
    ]


def get_fill_choices_batch(
    conn: sqlite3.Connection,
    lexicon_id: str,
    patterns: list[str],
    *,
    limit_per: int = 200,
    min_score: float = 0.0,
    no_proper_nouns: bool = False,
    try_rev: bool = False,
) -> dict[str, list[dict]]:
    """Run get_fill_choices for many patterns; keyed by the request pattern string.

    Deduplicates identical patterns. Kept single-threaded: SQLite fill lookups
    contend under thread pools and get slower; the client win is one HTTP
    round-trip instead of N.
    """
    cache: dict[str, list[dict]] = {}
    for raw in patterns:
        pattern = raw or ""
        if pattern in cache:
            continue
        cache[pattern] = get_fill_choices(
            conn,
            lexicon_id,
            pattern,
            limit=limit_per,
            min_score=min_score,
            no_proper_nouns=no_proper_nouns,
            try_rev=try_rev,
        )
    return {(raw or ""): cache[raw or ""] for raw in patterns}


def get_subset_anagrams(
    conn: sqlite3.Connection,
    lexicon_id: str,
    phrase: str,
    *,
    limit: int = 500,
    min_score: float = 0.0,
    min_len: int = 1,
    max_len: int = 0,
    no_proper_nouns: bool = False,
) -> list[dict]:
    """Entries whose letter multiset is a subset of the query letters."""
    letters = [ch for ch in parts_of(phrase.upper()) if ch in LETTER_SET]
    if not letters:
        return []
    if max_len <= 0:
        max_len = len(letters)
    min_len = max(1, min_len)
    if min_len > max_len:
        return []

    # Reject keys that contain any letter outside the fodder alphabet.
    outside = "*[^" + "".join(sorted(set(letters))) + "]*"
    sql = """
        SELECT id, form, normalized, score, anagram_key, letter_count
        FROM lexicon_entries
        WHERE lexicon_id = ?
          AND letter_count >= ?
          AND letter_count <= ?
          AND score >= ?
          AND NOT (anagram_key GLOB ?)
    """
    params: list[object] = [lexicon_id, min_len, max_len, min_score, outside]
    if no_proper_nouns:
        sql += " AND is_proper_noun = 0"
    sql += " ORDER BY score DESC, letter_count DESC, id ASC"

    from collections import Counter

    target = Counter(letters)
    out: list[dict] = []
    for row in conn.execute(sql, params):
        form = row["form"] if isinstance(row, sqlite3.Row) else row[1]
        normalized = row["normalized"] if isinstance(row, sqlite3.Row) else row[2]
        score = row["score"] if isinstance(row, sqlite3.Row) else row[3]
        eid = row["id"] if isinstance(row, sqlite3.Row) else row[0]
        letters_n = [ch for ch in normalized if ch in LETTER_SET]
        if not letters_n:
            continue
        if not Counter(letters_n) <= target:
            continue
        out.append(
            {
                "id": eid,
                "form": form,
                "score": score,
                "letter_count": len(letters_n),
            }
        )
        if limit > 0 and len(out) >= limit:
            break
    return out
