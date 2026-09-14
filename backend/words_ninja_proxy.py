"""Proxy Nutrimatic-compatible searches to the local words.ninja (rustomatic) API."""

from __future__ import annotations

import os
import urllib.error
import urllib.parse
import urllib.request

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import Response

WORDS_NINJA_URL = os.environ.get(
    "CROSSWORDS_WORDS_NINJA_URL", "http://words_ninja:8000"
).rstrip("/")
WORDS_NINJA_COMBOLIST_URL = os.environ.get(
    "CROSSWORDS_WORDS_NINJA_COMBOLIST_URL", "http://words_ninja_combolist:8000"
).rstrip("/")

# rustomatic only registers the ids `wikipedia` and `12dicts`, so our ComboList
# index occupies the `12dicts` slot of a second engine.
COMBOLIST_DICTIONARY = "combolist"

router = APIRouter(prefix="/api/words-ninja", tags=["words-ninja"])


def _route(dictionary: str) -> tuple[str, str]:
    if dictionary == COMBOLIST_DICTIONARY:
        return WORDS_NINJA_COMBOLIST_URL, "12dicts"
    return WORDS_NINJA_URL, dictionary


def _upstream(path: str, query: dict[str, str], base: str = WORDS_NINJA_URL) -> Response:
    url = f"{base}{path}"
    if query:
        url += "?" + urllib.parse.urlencode(query)
    req = urllib.request.Request(url, method="GET")
    try:
        with urllib.request.urlopen(req, timeout=40) as resp:
            body = resp.read()
            ctype = resp.headers.get("Content-Type", "application/json")
            return Response(content=body, media_type=ctype, status_code=resp.status)
    except urllib.error.HTTPError as exc:
        body = exc.read() if exc.fp else b""
        ctype = "application/json"
        if exc.headers and exc.headers.get("Content-Type"):
            ctype = exc.headers.get("Content-Type")
        return Response(content=body, media_type=ctype, status_code=exc.code)
    except Exception as exc:
        raise HTTPException(
            status_code=502,
            detail=f"words.ninja unavailable ({base}): {exc}",
        ) from exc


@router.get("/health")
def words_ninja_health(dictionary: str = Query("combolist")):
    base, _ = _route(dictionary)
    return _upstream("/health", {}, base)


@router.get("/search")
def words_ninja_search(
    q: str = Query(..., min_length=1),
    dictionary: str = Query("combolist"),
    limit: int = Query(80, ge=1, le=1000),
    offset: int = Query(0, ge=0),
):
    base, upstream_dictionary = _route(dictionary)
    return _upstream(
        "/search",
        {
            "q": q,
            "dictionary": upstream_dictionary,
            "limit": str(limit),
            "offset": str(offset),
        },
        base,
    )
