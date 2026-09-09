"""FastAPI server for Exet SQLite datasets."""

from __future__ import annotations

import json
import sqlite3
from contextlib import asynccontextmanager
from typing import Annotated

from fastapi import Depends, FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from backend.config import DB_PATH, DEFAULT_HOST, DEFAULT_PORT, EXET_DIR
from backend import puzzle_git
from backend.puzzle_git import PuzzleGitError
from backend.db import connect, get_meta
from backend.lexicon_lookup import get_anagrams, get_fill_choices
from backend.multiword_anagrams import get_multiword_anagrams
from backend.prior_clues_lookup import answer_key, parse_meta
from backend.wordnet_lookup import lookup_synonyms


@asynccontextmanager
async def lifespan(app: FastAPI):
    if not DB_PATH.is_file():
        print(f"Warning: database not found at {DB_PATH}")
        print("Run: python backend/build/build_all.py")
    yield


app = FastAPI(
    title="Exet data server",
    version="0.1.0",
    description="SQLite-backed lookups for Exet lexicons, prior clues, and WordNet.",
    lifespan=lifespan,
)
app.add_middleware(GZipMiddleware, minimum_size=1000)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET", "HEAD", "OPTIONS", "POST"],
    allow_headers=["*"],
)


def get_db() -> sqlite3.Connection:
    if not DB_PATH.is_file():
        raise HTTPException(
            503,
            f"Database missing at {DB_PATH}. Run: python backend/build/build_all.py",
        )
    conn = connect(DB_PATH)
    try:
        yield conn
    finally:
        conn.close()


DbDep = Annotated[sqlite3.Connection, Depends(get_db)]


@app.get("/")
def exet_home():
    path = EXET_DIR / "exet.html"
    if not path.is_file():
        raise HTTPException(404, "exet.html not found")
    return FileResponse(path, media_type="text/html")


@app.api_route("/backend/{path:path}", methods=["GET", "HEAD"])
def block_backend(path: str):
    raise HTTPException(404, "Not found")


@app.get("/health")
def health(db: DbDep):
    lexicon_count = db.execute("SELECT COUNT(*) FROM lexicons").fetchone()[0]
    prior_count = db.execute("SELECT COUNT(*) FROM prior_clues").fetchone()[0]
    wordnet_count = db.execute("SELECT COUNT(*) FROM wordnet_synsets").fetchone()[0]
    return {
        "ok": True,
        "db": str(DB_PATH),
        "lexicons": lexicon_count,
        "prior_clues": prior_count,
        "wordnet_synsets": wordnet_count,
    }


@app.get("/api/datasets")
def datasets(db: DbDep):
    lexicons = [
        dict(row)
        for row in db.execute(
            "SELECT id, slug, display_name, entry_count, built_at FROM lexicons ORDER BY display_name"
        ).fetchall()
    ]
    prior_stats = get_meta(db, "prior_clues_stats")
    wordnet_stats = get_meta(db, "wordnet_stats")
    return {
        "lexicons": lexicons,
        "prior_clues": json.loads(prior_stats) if prior_stats else None,
        "wordnet": json.loads(wordnet_stats) if wordnet_stats else None,
    }


@app.get("/api/lexicons")
def list_lexicons(db: DbDep):
    return [
        dict(row)
        for row in db.execute(
            "SELECT id, slug, display_name, entry_count, built_at FROM lexicons ORDER BY display_name"
        ).fetchall()
    ]


def _resolve_lexicon(db: sqlite3.Connection, lexicon_ref: str) -> sqlite3.Row:
    row = db.execute(
        "SELECT id, slug, display_name, entry_count, built_at FROM lexicons "
        "WHERE id = ? OR slug = ?",
        (lexicon_ref, lexicon_ref),
    ).fetchone()
    if not row:
        raise HTTPException(404, f"Lexicon not found: {lexicon_ref}")
    return row


@app.get("/api/lexicons/{lexicon_ref}/fill")
def lexicon_fill(
    lexicon_ref: str,
    db: DbDep,
    pattern: str = Query(..., min_length=1, description="Partial entry with ? wildcards"),
    limit: int = Query(200, ge=0, le=5000),
    min_score: float = Query(0.0),
    no_proper_nouns: bool = Query(False),
    try_rev: bool = Query(False),
):
    lex = _resolve_lexicon(db, lexicon_ref)
    choices = get_fill_choices(
        db,
        lex["id"],
        pattern,
        limit=limit,
        min_score=min_score,
        no_proper_nouns=no_proper_nouns,
        try_rev=try_rev,
    )
    return {
        "lexicon": dict(lex),
        "pattern": pattern,
        "count": len(choices),
        "choices": choices,
    }


@app.get("/api/lexicons/{lexicon_ref}/anagrams")
def lexicon_anagrams(
    lexicon_ref: str,
    db: DbDep,
    q: str = Query(..., min_length=1, description="Letters or phrase to anagram"),
    limit: int = Query(200, ge=0, le=5000),
    min_score: float = Query(0.0),
):
    lex = _resolve_lexicon(db, lexicon_ref)
    results = get_anagrams(db, lex["id"], q, limit=limit, min_score=min_score)
    return {
        "lexicon": dict(lex),
        "query": q,
        "count": len(results),
        "anagrams": results,
    }


@app.get("/api/lexicons/{lexicon_ref}/multiword-anagrams")
def lexicon_multiword_anagrams(
    lexicon_ref: str,
    db: DbDep,
    q: str = Query(..., min_length=1, description="Letters or phrase to anagram"),
    k: int = Query(2, ge=2, le=4, description="Max words in the anagram"),
    limit: int = Query(200, ge=0, le=2000),
    seq_ok: bool = Query(True, description="Allow words that are runs of the fodder"),
):
    lex = _resolve_lexicon(db, lexicon_ref)
    results = get_multiword_anagrams(
        db,
        lex["id"],
        q,
        k=k,
        limit=limit,
        seq_ok=seq_ok,
    )
    return {
        "lexicon": dict(lex),
        "query": q,
        "count": len(results),
        "results": results,
    }


@app.get("/api/prior-clues/stats")
def prior_clues_stats(db: DbDep):
    raw = get_meta(db, "prior_clues_stats")
    if not raw:
        count = db.execute("SELECT COUNT(*) FROM prior_clues").fetchone()[0]
        return {"rows": count}
    return json.loads(raw)


@app.get("/api/prior-clues/{answer}")
def prior_clues_for_answer(
    answer: str,
    db: DbDep,
    limit: int = Query(500, ge=1, le=5000),
):
    key = answer_key(answer)
    if not key:
        raise HTTPException(400, "Invalid answer")
    rows = db.execute(
        """
        SELECT clue, meta, popularity
        FROM prior_clues
        WHERE answer_key = ?
        ORDER BY popularity DESC, clue ASC
        LIMIT ?
        """,
        (key, limit),
    ).fetchall()
    clues = []
    for row in rows:
        parsed = parse_meta(row["meta"])
        clues.append(
            {
                "clue": row["clue"],
                "meta": row["meta"],
                "popularity": row["popularity"],
                **parsed,
            }
        )
    return {"answer": key, "count": len(clues), "clues": clues}


@app.get("/api/synonyms")
def synonyms(
    db: DbDep,
    word: str = Query(..., min_length=1),
):
    if "?" in word:
        return {"word": word, "count": 0, "synsets": []}
    synsets = lookup_synonyms(db, word)
    return {"word": word, "count": len(synsets), "synsets": synsets}


class PuzzleSaveBody(BaseModel):
    kind: str = Field(..., description="drafts or puzzles")
    name: str = Field(..., description="Filename ending in .puz, .ipuz, or .json")
    content_base64: str = Field(..., description="File bytes, base64-encoded")


def _puzzle_git_error(exc: PuzzleGitError) -> HTTPException:
    return HTTPException(400, str(exc))


@app.get("/api/puzzles/status")
def puzzles_status():
    return puzzle_git.status()


@app.post("/api/puzzles/sync")
def puzzles_sync():
    try:
        return puzzle_git.sync()
    except PuzzleGitError as exc:
        raise _puzzle_git_error(exc) from exc


@app.get("/api/puzzles/list")
def puzzles_list():
    try:
        return puzzle_git.list_files()
    except PuzzleGitError as exc:
        raise _puzzle_git_error(exc) from exc


@app.get("/api/puzzles/file")
def puzzles_file(
    kind: str = Query(..., description="drafts or puzzles"),
    name: str = Query(..., min_length=1),
):
    try:
        return puzzle_git.read_file(kind, name)
    except PuzzleGitError as exc:
        raise _puzzle_git_error(exc) from exc


@app.post("/api/puzzles/save")
def puzzles_save(body: PuzzleSaveBody):
    try:
        return puzzle_git.save_file(body.kind, body.name, body.content_base64)
    except PuzzleGitError as exc:
        raise _puzzle_git_error(exc) from exc


# Static assets (exet.js, wordlists/, lists/, …). Registered last; /api routes win.
app.mount("/", StaticFiles(directory=EXET_DIR, check_dir=False), name="exet-static")


def main() -> None:
    import uvicorn

    uvicorn.run(
        "backend.main:app",
        host=DEFAULT_HOST,
        port=DEFAULT_PORT,
        reload=True,
    )


if __name__ == "__main__":
    main()
