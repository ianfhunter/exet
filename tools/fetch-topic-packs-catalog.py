#!/usr/bin/env python3
"""Fetch available crossword topic/name packs and write .notes/topic-packs-catalog.md."""

from __future__ import annotations

import json
import ssl
from datetime import datetime, timezone
from pathlib import Path
from urllib.request import Request, urlopen

EXET = Path(__file__).resolve().parent.parent
OUT = EXET / ".notes" / "topic-packs-catalog.md"
CTX = ssl.create_default_context()


def gh_api(path: str) -> list[dict] | dict:
    req = Request(
        f"https://api.github.com{path}",
        headers={
            "User-Agent": "exet-topic-packs-catalog/1.0",
            "Accept": "application/vnd.github+json",
        },
    )
    with urlopen(req, context=CTX, timeout=120) as r:
        return json.loads(r.read().decode("utf-8"))


def list_repo_files(owner: str, repo: str, subpath: str = "") -> list[dict]:
    suffix = f"/contents/{subpath}" if subpath else "/contents"
    data = gh_api(f"/repos/{owner}/{repo}{suffix}")
    if isinstance(data, dict):
        return [data]
    return [x for x in data if x.get("type") == "file"]


def md_table(rows: list[tuple[str, str, str]]) -> str:
    lines = ["| Pack | File | Notes |", "| --- | --- | --- |"]
    for pack, file, notes in rows:
        lines.append(f"| {pack} | `{file}` | {notes} |")
    return "\n".join(lines)


def main() -> int:
    rows: list[tuple[str, str, str, str]] = []  # category, pack, file, notes

    # nzfeng curated packs
    try:
        for x in list_repo_files("nzfeng", "crossword-dataset", "raw"):
            name = x.get("name", "")
            if not name.endswith((".txt", ".dict", ".csv")):
                continue
            stem = name.replace(".txt", "").replace(".dict", "").replace(".csv", "")
            notes = {
                "core": "High-quality curated entries; good default",
                "contemporary": "Modern vocabulary and references",
                "idioms": "Multi-word idioms and phrases",
            }.get(stem, "Curated crossword dataset slice")
            rows.append(("nzfeng", stem, f"nzfeng-{name}", notes))
    except Exception as e:
        print(f"nzfeng FAIL: {e}", flush=True)

    # maiamcc specialty dicts
    try:
        for x in list_repo_files("maiamcc", "xword_dicts", "dictionaries"):
            name = x.get("name", "")
            if not name.endswith(".dict"):
                continue
            stem = name.replace("-scored.dict", "").replace(".dict", "")
            notes = {
                "queer": "LGBTQ+ terms (also fetched standalone)",
                "celebs": "Celebrity names",
                "colleges": "College / university names",
                "netspeak": "Internet slang and abbreviations",
                "urbandictionary": "Slang from Urban Dictionary (lower score recommended)",
                "websites": "Website and brand names",
            }.get(stem, "Specialty scored dict")
            rows.append(("maiamcc", stem, f"maiamcc-{name}", notes))
    except Exception as e:
        print(f"maiamcc FAIL: {e}", flush=True)

    # BirdsAreFlyingCameras geo packs
    geo_notes = {
        "CityNames.txt": "City names worldwide",
        "CountryNames.txt": "Country names",
        "States-Provinces.txt": "US states and provinces",
        "JobTitles.txt": "Occupations and job titles",
        "CommonWebsitePhrases.txt": "Web-era phrases (login, click here, …)",
        "Names.txt": "Large unfiltered name list — usually skip (too noisy)",
    }
    try:
        for x in list_repo_files("BirdsAreFlyingCameras", "WordLists"):
            name = x.get("name", "")
            if not name.endswith(".txt"):
                continue
            note = geo_notes.get(name, "Geo/name pack")
            skip = " **skip by default**" if name == "Names.txt" else ""
            rows.append(("geo", name.replace(".txt", ""), f"geo-{name.lower().replace('.txt', '')}.txt", note + skip))
    except Exception as e:
        print(f"geo FAIL: {e}", flush=True)

    # Static / manual sources already wired in Exet
    static = [
        ("core", "Nediger List", "wordlists/_sources/nediger.txt", "Extract via extract-exet-lexicons.py"),
        ("core", "Lufz English", "wordlists/_sources/lufz-en.txt", "Extract via extract-exet-lexicons.py"),
        ("core", "Crossword Nexus", "wordlists/_sources/xwordlist.dict", "MIT collaborative list"),
        ("core", "Peter Broda", "wordlists/_sources/broda.txt", "fetch-extra-wordlists.py"),
        ("core", "Solve The Crossword", "wordlists/_sources/stc-wordlist.dict", "fetch-extra-wordlists.py"),
        ("core", "Spread the Wordlist", "wordlists/spreadthewordlist.txt", "Shipped with Exet"),
        ("core", "Matt's list", "wordlists/_sources/matts_wordlist.txt", "CC BY-NC-SA"),
        ("core", "Chris Jones", "wordlists/crossword_wordlist.txt", "Shipped with Exet"),
        ("core", "Ettu", "wordlists/ettulist.txt", "UK-friendly; shipped with Exet"),
        ("names", "ECND names", "wordlists/_sources/ecnd-names.txt", "fetch-extra-wordlists.py"),
        ("names", "ECND places", "wordlists/_sources/ecnd-places.txt", "fetch-extra-wordlists.py"),
        ("fill", "UKACD", "wordlists/_sources/ukacd.txt", "fetch-extra-wordlists.py"),
        ("padding", "English OpenList", "wordlists/_sources/openlist_valid.txt", "Low score padding"),
        ("padding", "dwyl words_alpha", "wordlists/_sources/words_alpha.txt", "Low score padding"),
    ]
    for cat, pack, file, notes in static:
        rows.append((cat, pack, file, notes))

    # Group by category
    categories: dict[str, list[tuple[str, str, str]]] = {}
    for cat, pack, file, notes in rows:
        categories.setdefault(cat, []).append((pack, file, notes))

    order = ["core", "nzfeng", "maiamcc", "geo", "names", "fill", "padding"]
    titles = {
        "core": "Core wordlists (ComboList pipeline)",
        "nzfeng": "nzfeng curated packs (`fetch-recommended-packs.py`)",
        "maiamcc": "maiamcc specialty packs (`fetch-recommended-packs.py`)",
        "geo": "BirdsAreFlyingCameras geo packs (`fetch-recommended-packs.py`)",
        "names": "Name / place databases",
        "fill": "General fill",
        "padding": "Low-priority padding",
    }

    built = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    parts = [
        "# Topic pack catalog",
        "",
        f"Generated by `python tools/fetch-topic-packs-catalog.py` on {built}.",
        "",
        "To fetch downloadable packs into `wordlists/_sources/`:",
        "",
        "```bash",
        "python tools/fetch-recommended-packs.py   # nzfeng, maiamcc, geo",
        "python tools/fetch-extra-wordlists.py     # Broda, STC, ECND, UKACD",
        "python tools/build-million-union.py",
        "python tools/import-wordlists.py --only combolist",
        "```",
        "",
        "Enable a pack by ensuring its file exists under `_sources/` (or shipped paths)",
        "and that it appears in `tools/build-million-union.py` SOURCES.",
        "",
    ]

    for cat in order:
        if cat not in categories:
            continue
        parts.append(f"## {titles.get(cat, cat)}")
        parts.append("")
        parts.append(md_table(sorted(categories[cat], key=lambda r: r[0].lower())))
        parts.append("")

    parts.extend([
        "## Suggested combinations",
        "",
        "| If you write… | Consider enabling |",
        "| --- | --- |",
        "| American dailies / minis | Broda, STC, nzfeng-core, xd boost |",
        "| Cryptics (UK) | Ettu, Chris Jones, UKACD; prior clues: georgeho |",
        "| Pop-culture heavy | maiamcc-celebs, nzfeng-contemporary, geo-citynames |",
        "| Inclusive / modern surfaces | maiamcc-queer, nzfeng-contemporary |",
        "| Desperate fill only | openlist_valid, words_alpha (keep scores low) |",
        "",
        "## Not topic packs (prior clues only)",
        "",
        "| Source | Fetch | Use |",
        "| --- | --- | --- |",
        "| cryptics.georgeho.org | `fetch-prior-clues-data.py` | Cryptic prior clues |",
        "| xd.saul.pw | `fetch-prior-clues-data.py` | General published clues + ComboList frequency boost |",
        "| Ginsberg Cluer | `fetch-prior-clues-data.py` | NYT-weighted American clue suggestions |",
    ])

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text("\n".join(parts) + "\n", encoding="utf-8")
    print(f"Wrote {OUT} ({len(rows)} packs)", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
