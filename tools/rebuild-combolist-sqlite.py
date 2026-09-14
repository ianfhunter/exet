#!/usr/bin/env python3
"""Rebuild or incrementally update the ComboList lexicon in exet.sqlite.

Design goals:
  - Deletes use indexes (never cascade-delete after dropping indexes).
  - Bulk inserts run with secondary indexes dropped, then reindex once.
  - --incremental upserts only new/changed rows so idiom packs can land
    in seconds–minutes instead of a full wipe.

Usage:
  python tools/rebuild-combolist-sqlite.py              # full rebuild
  python tools/rebuild-combolist-sqlite.py --incremental
  python tools/rebuild-combolist-sqlite.py --exet-dir /exet
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

# Allow running from /patches, /exet/tools, or a checkout.
for _p in (Path("/exet"), Path(__file__).resolve().parent.parent):
    if (_p / "backend").is_dir():
        if str(_p) not in sys.path:
            sys.path.insert(0, str(_p))
        break

from backend.db import connect  # noqa: E402
from backend.build.lexicon import build_lexicon  # noqa: E402
from backend.build.load_tool import load_tool_module  # noqa: E402
from backend.lexicon_lookup import is_proper_noun  # noqa: E402

INDEX_SQL = [
    """CREATE INDEX IF NOT EXISTS idx_lexicon_entries_lookup
  ON lexicon_entries (lexicon_id, letter_count, normalized)""",
    """CREATE INDEX IF NOT EXISTS idx_lexicon_entries_anagram
  ON lexicon_entries (lexicon_id, anagram_key, score DESC)""",
    """CREATE INDEX IF NOT EXISTS idx_lexicon_entries_score
  ON lexicon_entries (lexicon_id, score DESC)""",
    """CREATE INDEX IF NOT EXISTS idx_lexicon_pattern_lookup
  ON lexicon_pattern (lexicon_id, pattern)""",
]

INDEX_NAMES = (
    "idx_lexicon_entries_lookup",
    "idx_lexicon_entries_anagram",
    "idx_lexicon_entries_score",
    "idx_lexicon_pattern_lookup",
)

PREFERRED_ID = "ComboList-imported"  # historical Exet id
SLUG = "combolist"


def _speed_pragmas(conn) -> None:
    conn.execute("PRAGMA busy_timeout=120000")
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=OFF")
    conn.execute("PRAGMA temp_store=MEMORY")
    conn.execute("PRAGMA cache_size=-1000000")


def _ensure_indexes(conn) -> None:
    for sql in INDEX_SQL:
        conn.execute(sql)
    conn.commit()


def _drop_secondary_indexes(conn) -> None:
    for name in INDEX_NAMES:
        conn.execute(f"DROP INDEX IF EXISTS {name}")
    conn.commit()


def resolve_lexicon_ids(conn) -> list[str]:
    """All DB ids that represent ComboList (legacy + current)."""
    rows = conn.execute(
        "SELECT id FROM lexicons WHERE slug = ? OR id = ? OR id = ?",
        (SLUG, SLUG, PREFERRED_ID),
    ).fetchall()
    ids = [r[0] for r in rows]
    # Always include preferred id so deletes are complete even if row missing.
    for cand in (PREFERRED_ID, SLUG):
        if cand not in ids:
            ids.append(cand)
    return ids


def delete_lexicon_fast(conn, lexicon_ids: list[str]) -> None:
    """Delete pattern + entry rows using indexes, then the lexicon row(s)."""
    _ensure_indexes(conn)
    for lid in lexicon_ids:
        t0 = time.time()
        cur = conn.execute(
            "DELETE FROM lexicon_pattern WHERE lexicon_id = ?", (lid,)
        )
        print(
            f"  patterns {lid!r}: deleted {cur.rowcount:,} ({time.time() - t0:.1f}s)",
            flush=True,
        )
        t1 = time.time()
        cur = conn.execute(
            "DELETE FROM lexicon_entries WHERE lexicon_id = ?", (lid,)
        )
        print(
            f"  entries  {lid!r}: deleted {cur.rowcount:,} ({time.time() - t1:.1f}s)",
            flush=True,
        )
        conn.execute("DELETE FROM lexicons WHERE id = ?", (lid,))
    conn.commit()


def full_rebuild(conn, source: Path) -> dict:
    ids = resolve_lexicon_ids(conn)
    print(f"full rebuild; clearing ids={ids} ...", flush=True)
    delete_lexicon_fast(conn, ids)

    print("dropping secondary indexes for bulk insert ...", flush=True)
    t0 = time.time()
    _drop_secondary_indexes(conn)
    print(f"  dropped ({time.time() - t0:.1f}s)", flush=True)

    # Keep stable id the API already knows.
    stats = build_lexicon(
        conn,
        source,
        slug=SLUG,
        display_name="ComboList",
        lexicon_id=PREFERRED_ID,
        clear_existing=False,
    )
    conn.commit()

    print("recreating secondary indexes ...", flush=True)
    t1 = time.time()
    _ensure_indexes(conn)
    print(f"  indexed ({time.time() - t1:.1f}s)", flush=True)
    return stats


def _patterns_for_form(importer, form: str, entry_id: int, lexicon_id: str) -> list[tuple]:
    """Build lexicon_pattern rows for one surface form (mirrors build_lexicon)."""
    # Use the same index builder on a tiny one-word list.
    phrase_infos, _t, _k, _s = importer.read_wordlist_lines([form])
    # Fallback if helper missing: synthesize via pruned parts.
    if not hasattr(importer, "read_wordlist_lines"):
        return _patterns_via_indices(importer, form, entry_id, lexicon_id)
    index, _agm = importer.build_indices(phrase_infos)
    # phrase_infos[0] is empty sentinel; form is index 1 → local idx 1
    rows = []
    for pattern, indices in index.items():
        for li in indices:
            if li == 1:
                rows.append((lexicon_id, pattern, entry_id))
    return rows


def _patterns_via_indices(importer, form: str, entry_id: int, lexicon_id: str) -> list[tuple]:
    from tempfile import NamedTemporaryFile

    with NamedTemporaryFile("w", suffix=".txt", encoding="utf-8", delete=False) as f:
        f.write(f"{form};50\n")
        tmp = Path(f.name)
    try:
        phrase_infos, _t, _k, _s = importer.read_wordlist(tmp)
        index, _agm = importer.build_indices(phrase_infos)
    finally:
        tmp.unlink(missing_ok=True)
    rows = []
    for pattern, indices in index.items():
        for li in indices:
            if li == 1:
                rows.append((lexicon_id, pattern, entry_id))
    return rows


def incremental_upsert(conn, source: Path, lexicon_id: str = PREFERRED_ID) -> dict:
    """Insert new forms / bump scores; add pattern rows only for inserts.

    Does not delete stale entries (safe + fast for pack merges).
    """
    importer = load_tool_module("import-wordlists", Path("/exet/tools"))
    _ensure_indexes(conn)

    # Ensure lexicon row exists.
    row = conn.execute(
        "SELECT id FROM lexicons WHERE id = ? OR slug = ?", (lexicon_id, SLUG)
    ).fetchone()
    if row:
        lexicon_id = row[0]
    else:
        conn.execute(
            "INSERT INTO lexicons(id, slug, display_name, entry_count, built_at) "
            "VALUES (?, ?, ?, 0, datetime('now'))",
            (lexicon_id, SLUG, "ComboList"),
        )
        conn.commit()

    print(f"loading existing forms for {lexicon_id!r} ...", flush=True)
    t0 = time.time()
    existing: dict[str, tuple[int, float]] = {}
    for eid, form, score in conn.execute(
        "SELECT id, form, score FROM lexicon_entries WHERE lexicon_id = ?",
        (lexicon_id,),
    ):
        existing[form] = (eid, float(score))
    print(f"  {len(existing):,} forms ({time.time() - t0:.1f}s)", flush=True)

    print(f"scanning {source} ...", flush=True)
    inserted = bumped = skipped = 0
    new_entry_ids: list[tuple[int, str]] = []
    batch_entries: list[tuple] = []
    t1 = time.time()

    with source.open("r", encoding="utf-8", errors="replace") as f:
        for raw in f:
            parsed = importer.parse_line(raw)
            if not parsed:
                skipped += 1
                continue
            phrase, importance = parsed
            parts, pruned = importer.pruned_parts_of(phrase)
            if not parts or len(parts) != len(pruned):
                skipped += 1
                continue
            letterized = importer.letterized_pruned_parts(pruned)
            letters = importer.letters_of(letterized)
            if not letters or len(letters) > importer.DEFAULT_MAX_ENTRY_LENGTH:
                skipped += 1
                continue
            form = "".join(pruned).replace(";", "")
            score = float(importance) if importance > 0 else 50.0
            prev = existing.get(form)
            if prev is None:
                normalized = "".join(
                    ch for ch in form.upper() if ch in importer.LETTER_SET
                )
                anagram_key = "".join(sorted(normalized)) if normalized else ""
                batch_entries.append(
                    (
                        lexicon_id,
                        form,
                        normalized,
                        len(normalized),
                        score,
                        anagram_key,
                        1 if is_proper_noun(form) else 0,
                    )
                )
                existing[form] = (-1, score)  # placeholder; fix id after flush
                inserted += 1
            elif score > prev[1] + 1e-9:
                conn.execute(
                    "UPDATE lexicon_entries SET score = ? WHERE id = ?",
                    (score, prev[0]),
                )
                existing[form] = (prev[0], score)
                bumped += 1

            if len(batch_entries) >= 5000:
                _flush_entries(conn, batch_entries, new_entry_ids)
                batch_entries.clear()

    if batch_entries:
        _flush_entries(conn, batch_entries, new_entry_ids)
        batch_entries.clear()

    print(
        f"  entries: +{inserted:,} inserted, {bumped:,} score bumps, "
        f"{skipped:,} skipped ({time.time() - t1:.1f}s)",
        flush=True,
    )

    if new_entry_ids:
        print(f"building pattern rows for {len(new_entry_ids):,} new forms ...", flush=True)
        t2 = time.time()
        # Cheaper: rebuild patterns via a temp wordlist of only new forms.
        from tempfile import NamedTemporaryFile

        with NamedTemporaryFile(
            "w", suffix=".txt", encoding="utf-8", delete=False
        ) as tf:
            for _eid, form in new_entry_ids:
                tf.write(f"{form};1\n")
            tmp = Path(tf.name)
        try:
            phrase_infos, _t, _k, _s = importer.read_wordlist(tmp)
            index, _agm = importer.build_indices(phrase_infos)
            # Map local lexicon index → entry id (idx 0 is empty sentinel).
            local_to_eid = {0: None}
            for i, (_eid, _form) in enumerate(new_entry_ids, start=1):
                local_to_eid[i] = _eid
            pattern_rows: list[tuple] = []
            batch = 0
            for pattern, indices in index.items():
                for li in indices:
                    eid = local_to_eid.get(li)
                    if eid is None:
                        continue
                    pattern_rows.append((lexicon_id, pattern, eid))
                    if len(pattern_rows) >= 50_000:
                        conn.executemany(
                            "INSERT OR IGNORE INTO lexicon_pattern"
                            "(lexicon_id, pattern, entry_id) VALUES (?, ?, ?)",
                            pattern_rows,
                        )
                        pattern_rows.clear()
                        batch += 1
                        if batch % 20 == 0:
                            print(f"    pattern batches={batch}", flush=True)
            if pattern_rows:
                conn.executemany(
                    "INSERT OR IGNORE INTO lexicon_pattern"
                    "(lexicon_id, pattern, entry_id) VALUES (?, ?, ?)",
                    pattern_rows,
                )
        finally:
            tmp.unlink(missing_ok=True)
        print(f"  patterns done ({time.time() - t2:.1f}s)", flush=True)

    count = conn.execute(
        "SELECT COUNT(*) FROM lexicon_entries WHERE lexicon_id = ?",
        (lexicon_id,),
    ).fetchone()[0]
    conn.execute(
        "UPDATE lexicons SET entry_count = ?, built_at = datetime('now') WHERE id = ?",
        (count, lexicon_id),
    )
    conn.commit()
    return {
        "id": lexicon_id,
        "slug": SLUG,
        "inserted": inserted,
        "bumped": bumped,
        "entry_count": count,
    }


def _flush_entries(conn, batch_entries: list[tuple], new_entry_ids: list) -> None:
    conn.executemany(
        """
        INSERT INTO lexicon_entries(
          lexicon_id, form, normalized, letter_count, score, anagram_key, is_proper_noun
        ) VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        batch_entries,
    )
    # Map inserted forms to ids.
    forms = [row[1] for row in batch_entries]
    lexicon_id = batch_entries[0][0]
    qmarks = ",".join("?" * len(forms))
    rows = conn.execute(
        f"SELECT id, form FROM lexicon_entries WHERE lexicon_id = ? AND form IN ({qmarks})",
        [lexicon_id, *forms],
    ).fetchall()
    by_form = {form: eid for eid, form in rows}
    for row in batch_entries:
        form = row[1]
        new_entry_ids.append((by_form[form], form))


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--exet-dir", type=Path, default=Path("/exet"))
    ap.add_argument(
        "--incremental",
        action="store_true",
        help="Upsert new/changed forms only (no full wipe)",
    )
    ap.add_argument(
        "--source",
        type=Path,
        default=None,
        help="Wordlist path (default: wordlists/combolist.txt)",
    )
    args = ap.parse_args(argv)
    exet = args.exet_dir.resolve()
    source = (args.source or (exet / "wordlists" / "combolist.txt")).resolve()
    if not source.is_file():
        print(f"MISSING {source}", flush=True)
        return 1

    # Prefer tools next to the live site.
    if str(exet) not in sys.path:
        sys.path.insert(0, str(exet))

    conn = connect()
    _speed_pragmas(conn)

    t_all = time.time()
    if args.incremental:
        print(f"incremental upsert from {source} ...", flush=True)
        stats = incremental_upsert(conn, source)
    else:
        stats = full_rebuild(conn, source)

    conn.execute("PRAGMA synchronous=NORMAL")
    conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    conn.commit()
    print(f"OK ({time.time() - t_all:.1f}s) {stats}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
