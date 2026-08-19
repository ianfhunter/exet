"""SQLite connection and schema for Exet datasets."""

from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from typing import Iterator

from backend.config import DATA_DIR, DB_PATH

SCHEMA = """
PRAGMA journal_mode = WAL;
PRAGMA synchronous = NORMAL;
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS meta (
  key TEXT PRIMARY KEY,
  value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS lexicons (
  id TEXT PRIMARY KEY,
  slug TEXT NOT NULL UNIQUE,
  display_name TEXT NOT NULL,
  entry_count INTEGER NOT NULL DEFAULT 0,
  built_at TEXT
);

CREATE TABLE IF NOT EXISTS lexicon_entries (
  id INTEGER PRIMARY KEY,
  lexicon_id TEXT NOT NULL REFERENCES lexicons(id) ON DELETE CASCADE,
  form TEXT NOT NULL,
  normalized TEXT NOT NULL,
  letter_count INTEGER NOT NULL,
  score REAL NOT NULL,
  anagram_key TEXT NOT NULL,
  is_proper_noun INTEGER NOT NULL DEFAULT 0
);

CREATE INDEX IF NOT EXISTS idx_lexicon_entries_lookup
  ON lexicon_entries (lexicon_id, letter_count, normalized);
CREATE INDEX IF NOT EXISTS idx_lexicon_entries_anagram
  ON lexicon_entries (lexicon_id, anagram_key, score DESC);
CREATE INDEX IF NOT EXISTS idx_lexicon_entries_score
  ON lexicon_entries (lexicon_id, score DESC);

CREATE TABLE IF NOT EXISTS lexicon_pattern (
  lexicon_id TEXT NOT NULL REFERENCES lexicons(id) ON DELETE CASCADE,
  pattern TEXT NOT NULL,
  entry_id INTEGER NOT NULL REFERENCES lexicon_entries(id) ON DELETE CASCADE,
  PRIMARY KEY (lexicon_id, pattern, entry_id)
);

CREATE INDEX IF NOT EXISTS idx_lexicon_pattern_lookup
  ON lexicon_pattern (lexicon_id, pattern);

CREATE TABLE IF NOT EXISTS prior_clues (
  id INTEGER PRIMARY KEY,
  answer_key TEXT NOT NULL,
  clue TEXT NOT NULL,
  meta TEXT NOT NULL DEFAULT '',
  popularity INTEGER NOT NULL DEFAULT 1
);

CREATE INDEX IF NOT EXISTS idx_prior_clues_answer
  ON prior_clues (answer_key, popularity DESC);

CREATE TABLE IF NOT EXISTS wordnet_synsets (
  id INTEGER PRIMARY KEY,
  pos TEXT NOT NULL,
  lemmas_json TEXT NOT NULL,
  gloss TEXT NOT NULL DEFAULT ''
);

CREATE TABLE IF NOT EXISTS wordnet_lemma_index (
  lemma TEXT PRIMARY KEY,
  synset_ids_json TEXT NOT NULL
);
"""


def ensure_data_dir() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)


def connect(db_path=DB_PATH) -> sqlite3.Connection:
    ensure_data_dir()
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA)
    return conn


@contextmanager
def db_conn(db_path=DB_PATH) -> Iterator[sqlite3.Connection]:
    conn = connect(db_path)
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def set_meta(conn: sqlite3.Connection, key: str, value: str) -> None:
    conn.execute(
        "INSERT INTO meta(key, value) VALUES (?, ?) "
        "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
        (key, value),
    )


def get_meta(conn: sqlite3.Connection, key: str) -> str | None:
    row = conn.execute("SELECT value FROM meta WHERE key = ?", (key,)).fetchone()
    return row["value"] if row else None
