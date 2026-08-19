"""Build prior_clues table from georgeho SQLite + xd-clues.zip."""

from __future__ import annotations

import json
import sqlite3
import time
from datetime import datetime, timezone

from backend.build.load_tool import load_tool_module
from backend.config import EXET_DIR, EXET_TOOLS_DIR
from backend.db import set_meta


def build_prior_clues(
    conn: sqlite3.Connection,
    *,
    max_per_answer: int = 0,
    clear_existing: bool = True,
) -> dict:
    builder = load_tool_module("build-prior-clues-index", EXET_TOOLS_DIR)
    sources_dir = EXET_DIR / "wordlists" / "_sources"
    xd_zip = EXET_DIR / "wordlists" / "xd-clues.zip"

    store: dict = {}
    meta_map: dict = {}
    t0 = time.time()

    gh_rows = builder.ingest_georgeho(sources_dir / "georgeho-data.db", store, meta_map)
    xd_rows = builder.ingest_xd(xd_zip, store, meta_map)

    if not store:
        print(
            "Prior clues: no source data. Run: python exet/tools/fetch-prior-clues-data.py",
            flush=True,
        )
        return {"answers": 0, "clues": 0}

    clues, meta, index = builder.build_index(store, meta_map, max_per_answer)

    if clear_existing:
        conn.execute("DELETE FROM prior_clues")

    print(f"Prior clues: inserting {sum(len(v) for v in index.values()):,} rows ...", flush=True)
    rows = []
    for answer_key, entries in index.items():
        for ci, mi in entries:
            clue_text = clues[ci]
            meta_text = meta[mi] if mi < len(meta) else ""
            popularity = store.get(answer_key, {}).get(clue_text, 1)
            rows.append((answer_key, clue_text, meta_text, popularity))
            if len(rows) >= 25_000:
                conn.executemany(
                    "INSERT INTO prior_clues(answer_key, clue, meta, popularity) "
                    "VALUES (?, ?, ?, ?)",
                    rows,
                )
                rows.clear()
    if rows:
        conn.executemany(
            "INSERT INTO prior_clues(answer_key, clue, meta, popularity) "
            "VALUES (?, ?, ?, ?)",
            rows,
        )

    stats = {
        "answers": len(index),
        "unique_clues": len(clues),
        "georgeho_rows": gh_rows,
        "xd_rows": xd_rows,
        "max_per_answer": max_per_answer or None,
        "built_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }
    set_meta(conn, "prior_clues_stats", json.dumps(stats))
    conn.commit()
    print(f"Prior clues done: {stats['answers']:,} answers ({time.time() - t0:.1f}s)", flush=True)
    return stats
