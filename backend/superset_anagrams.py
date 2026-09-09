"""Superset anagram lookup for anagrammed-deletions (server lexicons)."""

from __future__ import annotations

import sqlite3

from backend.lexicon_lookup import LETTER_SET, get_anagrams, parts_of


def _letters_of(s: str) -> list[str]:
    return [ch for ch in parts_of(s.upper()) if ch in LETTER_SET]


def _letter_hist(letters: list[str]) -> list[int]:
    hist = [0] * 26
    for ch in letters:
        hist[ord(ch) - ord("A")] += 1
    return hist


def _hist_sub(h1: list[int], h2: list[int]) -> list[int] | None:
    ret = h1[:]
    for i in range(26):
        ret[i] -= h2[i]
        if ret[i] < 0:
            return None
    if not any(ret):
        return None
    return ret


def _letters_x_hist(letters: list[str], hist: list[int]) -> str:
    hist = hist[:]
    out: list[str] = []
    for ch in letters:
        idx = ord(ch) - ord("A")
        if hist[idx] > 0:
            out.append(ch)
            hist[idx] -= 1
    return "".join(out)


def _like_filters(letters: list[str]) -> tuple[str, list[str]]:
    unique = sorted(set(letters))
    sql = ""
    params: list[str] = []
    for ch in unique:
        sql += " AND normalized LIKE ?"
        params.append(f"%{ch}%")
    return sql, params


def get_superset_anagrams(
    conn: sqlite3.Connection,
    lexicon_id: str,
    phrase: str,
    *,
    limit: int = 1000,
    minus_limit: int = 6,
    max_sup_factor: int = 2,
) -> list[dict]:
    letters = _letters_of(phrase)
    if not letters:
        return []

    letters_str = "".join(letters)
    full_hist = _letter_hist(letters)
    min_len = len(letters) + 1
    max_len = len(letters) * max_sup_factor
    like_sql, like_params = _like_filters(letters)

    sql = f"""
        SELECT form, normalized, score
        FROM lexicon_entries
        WHERE lexicon_id = ?
          AND letter_count > ?
          AND letter_count <= ?
          {like_sql}
        ORDER BY score DESC, id ASC
    """
    params: list[object] = [lexicon_id, len(letters), max_len, *like_params]

    out: list[dict] = []
    num = 0
    for form, normalized, score in conn.execute(sql, params):
        sup_letters = _letters_of(normalized)
        if len(sup_letters) < min_len:
            continue
        sup_str = "".join(sup_letters)
        if letters_str in sup_str:
            continue
        diff_hist = _hist_sub(_letter_hist(sup_letters), full_hist)
        if diff_hist is None:
            continue
        diff_str = _letters_x_hist(sup_letters, diff_hist)
        if not diff_str:
            continue
        diff_anags = [
            row["form"]
            for row in get_anagrams(
                conn, lexicon_id, diff_str, limit=minus_limit, min_score=0.0
            )
        ]
        if not diff_anags:
            continue
        out.append({
            "form": form,
            "score": score,
            "diff": diff_str,
            "anagrams": diff_anags,
        })
        num += len(diff_anags)
        if num > limit:
            break
    return out
