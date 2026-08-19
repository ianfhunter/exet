"""Build wordnet tables from exet-wordnet.js."""

from __future__ import annotations

import json
import re
import sqlite3
import time
from datetime import datetime, timezone

from backend.config import EXET_DIR
from backend.db import set_meta


def _extract_wordnet_data(text: str) -> dict:
    marker = "const DATA = "
    start = text.find(marker)
    if start < 0:
        raise ValueError("Could not find WordNet DATA object in exet-wordnet.js")
    start += len(marker)
    decoder = json.JSONDecoder()
    data, _ = decoder.raw_decode(text, start)
    return data


def _normalize_lemma(word: str) -> str:
    if not word:
        return ""
    return (
        str(word)
        .lower()
        .replace("\u2019", "'")
        .replace("'", "'")
        .replace("_", " ")
        .replace("\u2013", " ")
        .replace("\u2014", " ")
    )
    # collapse spaces below


def build_wordnet(conn: sqlite3.Connection, *, clear_existing: bool = True) -> dict:
    path = EXET_DIR / "exet-wordnet.js"
    if not path.is_file():
        print(f"WordNet: missing {path.name} — skip", flush=True)
        return {"synsets": 0, "lemmas": 0}

    print(f"WordNet: parsing {path.name} ...", flush=True)
    t0 = time.time()
    text = path.read_text(encoding="utf-8")
    data = _extract_wordnet_data(text)
    synsets = data.get("s") or []
    lemma_index = data.get("i") or {}

    if clear_existing:
        conn.execute("DELETE FROM wordnet_synsets")
        conn.execute("DELETE FROM wordnet_lemma_index")

    print(f"  inserting {len(synsets):,} synsets ...", flush=True)
    synset_rows = []
    for i, syn in enumerate(synsets):
        pos = syn[0] if syn else ""
        lemmas = syn[1] if len(syn) > 1 else []
        gloss = syn[2] if len(syn) > 2 else ""
        synset_rows.append((i, pos, json.dumps(lemmas, ensure_ascii=False), gloss))
        if len(synset_rows) >= 10_000:
            conn.executemany(
                "INSERT INTO wordnet_synsets(id, pos, lemmas_json, gloss) VALUES (?, ?, ?, ?)",
                synset_rows,
            )
            synset_rows.clear()
    if synset_rows:
        conn.executemany(
            "INSERT INTO wordnet_synsets(id, pos, lemmas_json, gloss) VALUES (?, ?, ?, ?)",
            synset_rows,
        )

    print(f"  inserting {len(lemma_index):,} lemma index entries ...", flush=True)
    lemma_rows = []
    for lemma, idxs in lemma_index.items():
        key = _normalize_lemma(lemma)
        key = re.sub(r"\s+", " ", key).strip()
        if not key:
            continue
        lemma_rows.append((key, json.dumps(idxs)))
        if len(lemma_rows) >= 10_000:
            conn.executemany(
                "INSERT OR REPLACE INTO wordnet_lemma_index(lemma, synset_ids_json) "
                "VALUES (?, ?)",
                lemma_rows,
            )
            lemma_rows.clear()
    if lemma_rows:
        conn.executemany(
            "INSERT OR REPLACE INTO wordnet_lemma_index(lemma, synset_ids_json) "
            "VALUES (?, ?)",
            lemma_rows,
        )

    stats = {
        "synsets": len(synsets),
        "lemmas": len(lemma_index),
        "version": data.get("version"),
        "built_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }
    set_meta(conn, "wordnet_stats", json.dumps(stats))
    conn.commit()
    print(f"WordNet done ({time.time() - t0:.1f}s)", flush=True)
    return stats
