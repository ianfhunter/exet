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
from backend.db import connect, get_meta, set_meta
from backend.lexicon_lookup import (
    get_anagrams,
    get_fill_choices,
    get_score_quantiles,
    score_quantiles_key,
)
from backend.superset_anagrams import get_superset_anagrams
from backend.multiword_anagrams import get_multiword_anagrams
from backend.lexicon_ext import (
    get_fill_choices_batch,
    get_subset_anagrams,
    search_entries,
)
from backend.prior_clues_lookup import answer_key, parse_meta
from backend.wordnet_lookup import lookup_synonyms
from backend.words_ninja_proxy import router as words_ninja_router


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
app.include_router(words_ninja_router)



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


_score_quantiles_memo: dict[str, dict] = {}


def _score_quantiles_for(db: sqlite3.Connection, lex: sqlite3.Row) -> list[float]:
    """Rank -> score map for a lexicon, keyed on its build timestamp.

    Normally written by the build step; computed and persisted on first use for
    databases built before it existed.
    """
    key = score_quantiles_key(lex["id"])
    built_at = lex["built_at"] or ""
    cached = _score_quantiles_memo.get(key)
    if cached is None:
        raw = get_meta(db, key)
        if raw:
            try:
                cached = json.loads(raw)
            except ValueError:
                cached = None
    if cached and cached.get("built_at") == built_at:
        _score_quantiles_memo[key] = cached
        return cached.get("quantiles") or []

    cached = {"built_at": built_at, "quantiles": get_score_quantiles(db, lex["id"])}
    _score_quantiles_memo[key] = cached
    try:
        set_meta(db, key, json.dumps(cached))
        db.commit()
    except sqlite3.Error:
        pass
    return cached["quantiles"]


@app.get("/api/datasets")
def datasets(db: DbDep):
    lexicons = []
    for row in db.execute(
        "SELECT id, slug, display_name, entry_count, built_at FROM lexicons ORDER BY display_name"
    ).fetchall():
        if row["display_name"] != "ComboList":
            continue
        lex = dict(row)
        quantiles = _score_quantiles_for(db, row)
        lex["score_quantiles"] = quantiles
        lex["score_max"] = quantiles[0] if quantiles else 0.0
        lex["score_min"] = quantiles[-1] if quantiles else 0.0
        lexicons.append(lex)
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
            "SELECT id, slug, display_name, entry_count, built_at FROM lexicons "
            "WHERE display_name = 'ComboList' ORDER BY display_name"
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


@app.post("/api/lexicons/{lexicon_ref}/fill-batch")
def lexicon_fill_batch(
    lexicon_ref: str,
    db: DbDep,
    body: dict,
):
    """Resolve all grid-light patterns in one request for the fill worker."""
    lex = _resolve_lexicon(db, lexicon_ref)
    patterns = body.get("patterns") or []
    if not isinstance(patterns, list) or any(
        not isinstance(pattern, str) for pattern in patterns
    ):
        raise HTTPException(400, "patterns must be a list of strings")
    if len(patterns) > 500:
        raise HTTPException(400, "at most 500 patterns per batch")
    limit = max(0, min(int(body.get("limit_per") or 200), 5000))
    min_score = float(body.get("min_score") or 0)
    no_proper_nouns = bool(body.get("no_proper_nouns") or False)
    try_rev = bool(body.get("try_rev") or False)
    results = {
        pattern: get_fill_choices(
            db,
            lex["id"],
            pattern,
            limit=limit,
            min_score=min_score,
            no_proper_nouns=no_proper_nouns,
            try_rev=try_rev,
        )
        for pattern in dict.fromkeys(patterns)
    }
    return {"lexicon": dict(lex), "results": results}


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
    min_score: float = Query(0.0),
):
    lex = _resolve_lexicon(db, lexicon_ref)
    results = get_multiword_anagrams(
        db,
        lex["id"],
        q,
        k=k,
        limit=limit,
        seq_ok=seq_ok,
        min_score=min_score,
    )
    return {
        "lexicon": dict(lex),
        "query": q,
        "count": len(results),
        "results": results,
    }


@app.get("/api/lexicons/{lexicon_ref}/superset-anagrams")
def lexicon_superset_anagrams(
    lexicon_ref: str,
    db: DbDep,
    q: str = Query(
        ..., min_length=1, description="Letters or phrase for anagrammed deletions"
    ),
    limit: int = Query(1000, ge=0, le=5000),
    minus_limit: int = Query(6, ge=0, le=100),
    max_sup_factor: int = Query(2, ge=1, le=4),
    min_score: float = Query(0.0),
):
    lex = _resolve_lexicon(db, lexicon_ref)
    results = get_superset_anagrams(
        db,
        lex["id"],
        q,
        limit=limit,
        minus_limit=minus_limit,
        max_sup_factor=max_sup_factor,
        min_score=min_score,
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
