"""Build lexicon tables from exet/wordlists/*.txt sources."""

from __future__ import annotations

import sqlite3
import time
from datetime import datetime, timezone

from backend.build.load_tool import load_tool_module
from backend.config import EXET_TOOLS_DIR, WORDLISTS_DIR
from backend.db import set_meta
from backend.lexicon_lookup import is_proper_noun


def build_lexicon(
    conn: sqlite3.Connection,
    source_path,
    *,
    slug: str | None = None,
    display_name: str | None = None,
    lexicon_id: str | None = None,
    clear_existing: bool = True,
) -> dict:
    importer = load_tool_module("import-wordlists", EXET_TOOLS_DIR)
    path = source_path
    slug = slug or importer.slugify(path.stem)
    display_name = display_name or importer.humanize(path.stem)
    lexicon_id = lexicon_id or f"{display_name}-imported"

    print(f"Lexicon {display_name}: reading {path.name} ...", flush=True)
    t0 = time.time()
    phrase_infos, total, kept, skipped = importer.read_wordlist(path)
    print(
        f"  parsed lines={total:,} kept={kept:,} skipped={skipped:,} "
        f"entries={len(phrase_infos) - 1:,} ({time.time() - t0:.1f}s)",
        flush=True,
    )

    print("  building indices ...", flush=True)
    t1 = time.time()
    index, _agm = importer.build_indices(phrase_infos)
    words, scores = importer.flat_lexicon(phrase_infos)
    print(
        f"  {len(words):,} surface forms, {len(index):,} pattern keys "
        f"({time.time() - t1:.1f}s)",
        flush=True,
    )

    if clear_existing:
        conn.execute("DELETE FROM lexicon_pattern WHERE lexicon_id = ?", (lexicon_id,))
        conn.execute("DELETE FROM lexicon_entries WHERE lexicon_id = ?", (lexicon_id,))
        conn.execute("DELETE FROM lexicons WHERE id = ?", (lexicon_id,))

    built_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    conn.execute(
        """
        INSERT INTO lexicons(id, slug, display_name, entry_count, built_at)
        VALUES (?, ?, ?, ?, ?)
        ON CONFLICT(id) DO UPDATE SET
          slug = excluded.slug,
          display_name = excluded.display_name,
          entry_count = excluded.entry_count,
          built_at = excluded.built_at
        """,
        (lexicon_id, slug, display_name, len(words), built_at),
    )

    print("  inserting entries ...", flush=True)
    t2 = time.time()
    entry_rows = []
    for idx, (form, score) in enumerate(zip(words, scores)):
        normalized = "".join(ch for ch in form.upper() if ch in importer.LETTER_SET)
        if not normalized and idx == 0:
            normalized = ""
        letter_count = len(normalized)
        anagram_key = "".join(sorted(normalized)) if normalized else ""
        entry_rows.append(
            (
                lexicon_id,
                form,
                normalized,
                letter_count,
                float(score),
                anagram_key,
                1 if is_proper_noun(form) else 0,
            )
        )

    conn.executemany(
        """
        INSERT INTO lexicon_entries(
          lexicon_id, form, normalized, letter_count, score, anagram_key, is_proper_noun
        ) VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        entry_rows,
    )

    # SQLite rowids for inserted entries: first id = last_insert_rowid - n + 1
    first_id = conn.execute("SELECT MIN(id) FROM lexicon_entries WHERE lexicon_id = ?", (lexicon_id,)).fetchone()[0]
    print(f"  inserted entries ({time.time() - t2:.1f}s), first_id={first_id}", flush=True)

    print("  inserting pattern index ...", flush=True)
    t3 = time.time()
    pattern_rows = []
    batch = 0
    for pattern, indices in index.items():
        for li in indices:
            entry_id = first_id + li
            pattern_rows.append((lexicon_id, pattern, entry_id))
            if len(pattern_rows) >= 50_000:
                conn.executemany(
                    "INSERT OR IGNORE INTO lexicon_pattern(lexicon_id, pattern, entry_id) "
                    "VALUES (?, ?, ?)",
                    pattern_rows,
                )
                pattern_rows.clear()
                batch += 1
                if batch % 20 == 0:
                    print(f"    pattern batches={batch}", flush=True)
    if pattern_rows:
        conn.executemany(
            "INSERT OR IGNORE INTO lexicon_pattern(lexicon_id, pattern, entry_id) "
            "VALUES (?, ?, ?)",
            pattern_rows,
        )
    print(f"  pattern index done ({time.time() - t3:.1f}s)", flush=True)
    conn.commit()

    stats = {
        "id": lexicon_id,
        "slug": slug,
        "display_name": display_name,
        "entries": len(words),
        "pattern_keys": len(index),
        "source": str(path),
    }
    print(f"Lexicon {display_name} done in {time.time() - t0:.1f}s", flush=True)
    return stats


def discover_wordlists(wordlists_dir=WORDLISTS_DIR) -> list:
    importer = load_tool_module("import-wordlists", EXET_TOOLS_DIR)
    return importer.discover_sources(wordlists_dir)


def build_all_lexicons(conn: sqlite3.Connection, only: str | None = None) -> list[dict]:
    sources = discover_wordlists()
    if only:
        only_l = only.lower()
        sources = [p for p in sources if only_l in p.stem.lower()]
    if not sources:
        print("No wordlist sources found.", flush=True)
        return []

    results = []
    for path in sources:
        stats = build_lexicon(conn, path)
        results.append(stats)
    set_meta(conn, "lexicons_built", str(len(results)))
    conn.commit()
    return results
