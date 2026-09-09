"""Multi-word anagram lookup for server-backed lexicons.

exet-lexicon.js builds multi-word anagrams from an in-memory `slkIndex` over
the whole lexicon. Server-backed lexicons have no in-memory lexicon, so that
index is empty and getAnagramsK() finds nothing. This reimplements the search
in SQL: every word of a multi-word anagram is a strict letter-subset of the
fodder, so one indexed scan collects every usable word, and the partitioning
runs in memory over that much smaller set.
"""

from __future__ import annotations

import sqlite3
from collections import defaultdict

from backend.lexicon_lookup import LETTER_SET, parts_of

A = ord("A")
# Guards pathological fodder (many repeated common letters) from unbounded DFS.
DEFAULT_NODE_BUDGET = 400_000


def _letters_of(s: str) -> list[str]:
    return [ch for ch in parts_of(s.upper()) if ch in LETTER_SET]


def _hist_of(letters: list[str]) -> tuple[int, ...]:
    hist = [0] * 26
    for ch in letters:
        hist[ord(ch) - A] += 1
    return tuple(hist)


def _hist_sub(h1: tuple[int, ...], h2: tuple[int, ...]) -> tuple[int, ...] | None:
    ret = list(h1)
    for i in range(26):
        ret[i] -= h2[i]
        if ret[i] < 0:
            return None
    return tuple(ret)


def _key_of(hist: tuple[int, ...]) -> str:
    return "".join(chr(A + i) * n for i, n in enumerate(hist) if n)


def _candidates(
    conn: sqlite3.Connection,
    lexicon_id: str,
    letters: list[str],
    full_hist: tuple[int, ...],
    min_score: float,
) -> list[tuple[str, tuple[int, ...], float, str]]:
    """Every lexicon entry whose letters are a strict sub-multiset of the fodder."""
    # anagram_key is sorted letters, so a key holding any letter outside the
    # fodder's alphabet is rejected by GLOB before we touch the histogram.
    outside = "*[^" + "".join(sorted(set(letters))) + "]*"
    sql = """
        SELECT form, normalized, score, anagram_key
        FROM lexicon_entries
        WHERE lexicon_id = ?
          AND letter_count > 0
          AND letter_count < ?
          AND score >= ?
          AND NOT (anagram_key GLOB ?)
        ORDER BY score DESC, id ASC
    """
    out = []
    for form, normalized, score, _key in conn.execute(
        sql, (lexicon_id, len(letters), min_score, outside)
    ):
        sub_letters = _letters_of(normalized)
        if not sub_letters:
            continue
        hist = _hist_of(sub_letters)
        if _hist_sub(full_hist, hist) is None:
            continue
        out.append((form, hist, score, "".join(sub_letters)))
    return out


def get_multiword_anagrams(
    conn: sqlite3.Connection,
    lexicon_id: str,
    phrase: str,
    *,
    k: int = 2,
    limit: int = 100,
    min_score: float = 0.0,
    seq_ok: bool = True,
    node_budget: int = DEFAULT_NODE_BUDGET,
) -> list[dict]:
    letters = _letters_of(phrase)
    if len(letters) < 2 or k < 2:
        return []

    full_hist = _hist_of(letters)
    phrase_seq = "" if seq_ok else "".join(letters)
    cands = _candidates(conn, lexicon_id, letters, full_hist, min_score)
    if not cands:
        return []

    by_key: dict[str, list[int]] = defaultdict(list)
    for i, (_form, hist, _score, _letters) in enumerate(cands):
        by_key[_key_of(hist)].append(i)

    results: list[dict] = []
    seen: set[tuple[int, ...]] = set()
    budget = [node_budget]

    def emit(chosen: list[int]) -> None:
        combo = tuple(sorted(chosen))
        if combo in seen:
            return
        seen.add(combo)
        words = [cands[i][0] for i in combo]
        results.append({
            "words": words,
            "phrase": " ".join(words),
            # Weakest word decides how usable the phrase is, matching the
            # "worsening worst popularity" ordering of exet-lexicon.js.
            "score": min(cands[i][2] for i in combo),
        })

    def search(hist: tuple[int, ...], depth: int, start: int, chosen: list[int]) -> bool:
        """Partition `hist` into exactly `depth` words. Returns True when full."""
        if len(results) >= limit or budget[0] <= 0:
            return True

        if depth == 1:
            for i in by_key.get(_key_of(hist), ()):
                if i < start:
                    continue
                if not seq_ok and phrase_seq.find(cands[i][3]) >= 0:
                    continue
                emit(chosen + [i])
                if len(results) >= limit:
                    return True
            return False

        for i in range(start, len(cands)):
            budget[0] -= 1
            if budget[0] <= 0:
                return True
            rest = _hist_sub(hist, cands[i][1])
            if rest is None or not any(rest):
                continue
            if not seq_ok and phrase_seq.find(cands[i][3]) >= 0:
                continue
            chosen.append(i)
            full = search(rest, depth - 1, i + 1, chosen)
            chosen.pop()
            if full:
                return True
        return False

    # Iterative deepening: exhaust 2-word anagrams before spending the result
    # budget on wordier ones, so a truncated search still returns the best.
    for depth in range(2, k + 1):
        if search(full_hist, depth, 0, []):
            break

    results.sort(key=lambda r: (len(r["words"]), -r["score"]))
    return results[:limit] if limit > 0 else results
