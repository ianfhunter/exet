#!/usr/bin/env python3
"""Fetch / extract idiom & phrase packs into wordlists/_sources/.

Writes scored plaintext packs (word;score) suitable for build-million-union.py
or for merging into an existing combolist.txt.

Sources:
  - MAGPIE corpus idiom types (BNC, CC BY 4.0)
  - MIDAS English idiom variants
  - zaghloul404/englishidioms phrases.json
  - Wiktionary English via kaikki.org (pos=phrase + idiom/proverb categories)
  - WordNet multiword lemmas from backend/data/exet.sqlite (optional)

Usage:
  python tools/fetch-idiom-packs.py
  python tools/fetch-idiom-packs.py --merge-combolist
  python tools/fetch-idiom-packs.py --skip-kaikki   # faster; skip ~500MB stream
"""

from __future__ import annotations

import argparse
import gzip
import importlib.util
import json
import re
import sqlite3
import ssl
import sys
import time
from pathlib import Path
from urllib.request import Request, urlopen

TOOLS = Path(__file__).resolve().parent
# When installed as tools/fetch-idiom-packs.py, parent is tools/; patches/ copy uses same.
if TOOLS.name == "patches":
    EXET = TOOLS.parent  # containers/crosswords — not used for live paths
    # Live install path is /exet/tools/... ; patches copy is for sync install only.
    DEFAULT_EXET = Path("/exet")
else:
    DEFAULT_EXET = TOOLS.parent

CTX = ssl.create_default_context()
UA = "exet-idiom-pack-builder/1.0"

# Placeholders that are not grid-friendly as literal crossword entries.
BAD_TOKEN = re.compile(
    r"\b(sb|sth|smth|somebody|someone|something|somebody's|someone's)\b",
    re.I,
)
# Keep one's / one's — already used in combolist.
SLOT_STAR = re.compile(r"[*…_]|<\w+>|\{\w+\}|\[\w+\]")
NON_LETTER_JUNK = re.compile(r"[^A-Za-z0-9 '\-.]")
MULTI_SPACE = re.compile(r"\s+")


def get(url: str, timeout: int = 300) -> bytes:
    req = Request(url, headers={"User-Agent": UA})
    with urlopen(req, context=CTX, timeout=timeout) as r:
        return r.read()


def get_stream(url: str, timeout: int = 600):
    req = Request(url, headers={"User-Agent": UA})
    return urlopen(req, context=CTX, timeout=timeout)


def clean_phrase(raw: str) -> str | None:
    """Normalize a candidate phrase; return None if not lexicon-worthy."""
    if not raw:
        return None
    s = raw.strip()
    # Drop dictionary sense markers / leading numbers.
    s = re.sub(r"^\d+\.\s*", "", s)
    # Prefer form without parenthetical alternatives: "breathe (easily) again"
    # → keep both without-parens and with-parens-as-words when short.
    # Primary: strip parentheticals.
    primary = re.sub(r"\([^)]*\)", " ", s)
    primary = primary.replace("/", " ")
    primary = NON_LETTER_JUNK.sub(" ", primary)
    primary = MULTI_SPACE.sub(" ", primary).strip(" -.'")
    if not primary:
        return None
    if SLOT_STAR.search(primary):
        return None
    if BAD_TOKEN.search(primary):
        return None
    # Must have at least one letter.
    if not re.search(r"[A-Za-z]", primary):
        return None
    # Prefer multi-word or hyphenated compounds; allow solid phrases from pos=phrase.
    letters = re.sub(r"[^A-Za-z]", "", primary)
    if len(letters) < 3 or len(letters) > 75:
        return None
    # Reject tiny fragments / affixes.
    if primary.endswith("-") or primary.startswith("-"):
        return None
    if len(primary) <= 2:
        return None
    return primary


def write_pack(path: Path, phrases: set[str], score: float) -> int:
    path.parent.mkdir(parents=True, exist_ok=True)
    items = sorted(phrases, key=lambda p: (p.lower(), p))
    with path.open("w", encoding="utf-8", newline="\n") as f:
        for p in items:
            # Avoid semicolon clash with scored format.
            form = p.replace(";", ",")
            if abs(score - round(score)) < 1e-9:
                f.write(f"{form};{int(round(score))}\n")
            else:
                f.write(f"{form};{score:.4f}\n")
    return len(items)


def fetch_magpie(out: Path, score: float) -> int:
    url = (
        "https://raw.githubusercontent.com/hslh/magpie-corpus/master/"
        "MAGPIE_unfiltered.jsonl"
    )
    print("MAGPIE …", flush=True)
    data = get(url)
    phrases: set[str] = set()
    for line in data.splitlines():
        if not line.strip():
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            continue
        # Prefer idiomatic-labelled types; still keep unknowns for coverage.
        label = (obj.get("label") or "").lower()
        if label in {"l", "literal"}:
            continue
        got = clean_phrase(obj.get("idiom") or "")
        if got and (" " in got or "-" in got):
            phrases.add(got)
    n = write_pack(out / "idioms-magpie.txt", phrases, score)
    print(f"  wrote idioms-magpie.txt ({n:,})", flush=True)
    return n


def fetch_midas(out: Path, score: float) -> int:
    url = "https://raw.githubusercontent.com/HYU-NLP/MIDAS/main/data/EN_Idioms.json"
    print("MIDAS …", flush=True)
    objs = json.loads(get(url))
    phrases: set[str] = set()
    for obj in objs:
        for variant in obj.get("Idiom") or []:
            got = clean_phrase(variant)
            if got and (" " in got or "-" in got or len(got) >= 6):
                phrases.add(got)
    n = write_pack(out / "idioms-midas.txt", phrases, score)
    print(f"  wrote idioms-midas.txt ({n:,})", flush=True)
    return n


def fetch_englishidioms(out: Path, score: float) -> int:
    url = (
        "https://raw.githubusercontent.com/zaghloul404/englishidioms/main/"
        "englishidioms/phrases.json"
    )
    print("englishidioms phrases.json …", flush=True)
    root = json.loads(get(url))
    phrases: set[str] = set()
    for entry in root.get("dictionary") or []:
        got = clean_phrase(entry.get("phrase") or "")
        if got and (" " in got or "-" in got):
            phrases.add(got)
        # Also try alternate forms if present.
        for alt in entry.get("alternatives") or entry.get("variants") or []:
            if isinstance(alt, str):
                g2 = clean_phrase(alt)
                if g2 and (" " in g2 or "-" in g2):
                    phrases.add(g2)
    n = write_pack(out / "idioms-englishidioms.txt", phrases, score)
    print(f"  wrote idioms-englishidioms.txt ({n:,})", flush=True)
    return n


def _cat_strings(obj: dict) -> list[str]:
    out: list[str] = []

    def add(c):
        if isinstance(c, str):
            out.append(c)
        elif isinstance(c, dict):
            out.append(str(c.get("name") or c.get("title") or ""))

    for c in obj.get("categories") or []:
        add(c)
    for sense in obj.get("senses") or []:
        for c in sense.get("categories") or []:
            add(c)
        for t in sense.get("tags") or []:
            if isinstance(t, str):
                out.append("tag:" + t)
    return out


def fetch_kaikki(out: Path, score: float) -> int:
    url = (
        "https://kaikki.org/dictionary/English/"
        "kaikki.org-dictionary-English.jsonl.gz"
    )
    print("kaikki.org English (streaming gzip) …", flush=True)
    phrases: set[str] = set()
    n_lines = 0
    t0 = time.time()
    with get_stream(url) as raw:
        with gzip.GzipFile(fileobj=raw) as f:
            for line in f:
                n_lines += 1
                if n_lines % 500_000 == 0:
                    print(
                        f"  … scanned {n_lines:,} kept {len(phrases):,} "
                        f"({time.time() - t0:.0f}s)",
                        flush=True,
                    )
                try:
                    obj = json.loads(line)
                except json.JSONDecodeError:
                    continue
                word = (obj.get("word") or "").strip()
                if not word:
                    continue
                pos = (obj.get("pos") or "").lower()
                cats = _cat_strings(obj)
                blob = " | ".join(cats).lower()
                is_phrase_pos = pos == "phrase"
                is_idiomish = (
                    "idiom" in blob
                    or "proverb" in blob
                    or "saying" in blob
                    or "tag:idiomatic" in blob
                )
                if not (is_phrase_pos or is_idiomish):
                    continue
                # Affix noise: require multiword unless explicit phrase POS
                # with enough letters.
                got = clean_phrase(word)
                if not got:
                    continue
                if " " not in got and "-" not in got:
                    if not is_phrase_pos or len(re.sub(r"[^A-Za-z]", "", got)) < 6:
                        continue
                phrases.add(got)
    n = write_pack(out / "idioms-kaikki.txt", phrases, score)
    print(
        f"  wrote idioms-kaikki.txt ({n:,}) from {n_lines:,} lines "
        f"in {time.time() - t0:.0f}s",
        flush=True,
    )
    return n


def extract_wordnet_mwe(exet_dir: Path, out: Path, score: float) -> int:
    db = exet_dir / "backend" / "data" / "exet.sqlite"
    print("WordNet MWEs …", flush=True)
    if not db.is_file():
        print(f"  MISSING {db} — skip", flush=True)
        return 0
    phrases: set[str] = set()
    conn = sqlite3.connect(str(db))
    try:
        rows = conn.execute(
            "SELECT lemma FROM wordnet_lemma_index WHERE lemma LIKE '% %'"
        ).fetchall()
    finally:
        conn.close()
    for (lemma,) in rows:
        got = clean_phrase(lemma.replace("_", " "))
        if got and " " in got:
            phrases.add(got)
    n = write_pack(out / "idioms-wordnet-mwe.txt", phrases, score)
    print(f"  wrote idioms-wordnet-mwe.txt ({n:,})", flush=True)
    return n


def _load_importer(exet_dir: Path):
    path = exet_dir / "tools" / "import-wordlists.py"
    spec = importlib.util.spec_from_file_location("import_wordlists", path)
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    return mod


def merge_into_combolist(exet_dir: Path, pack_paths: list[Path], default_score: float) -> int:
    """Merge pack files into wordlists/combolist.txt (max score wins)."""
    imp = _load_importer(exet_dir)
    combolist = exet_dir / "wordlists" / "combolist.txt"
    if not combolist.is_file():
        print(f"MISSING {combolist}", flush=True)
        return 0

    store: dict[str, tuple[str, float]] = {}
    print(f"Loading existing {combolist.name} …", flush=True)
    with combolist.open("r", encoding="utf-8", errors="replace") as f:
        for raw in f:
            parsed = imp.parse_line(raw)
            if not parsed:
                continue
            phrase, importance = parsed
            parts, pruned = imp.pruned_parts_of(phrase)
            if not parts or len(parts) != len(pruned):
                continue
            letterized = imp.letterized_pruned_parts(pruned)
            letters = imp.letters_of(letterized)
            if not letters or len(letters) > imp.DEFAULT_MAX_ENTRY_LENGTH:
                continue
            key = "".join(letters)
            form = "".join(pruned)
            score = importance if importance > 0 else default_score
            prev = store.get(key)
            if prev is None or score > prev[1]:
                store[key] = (form, score)

    before = len(store)
    added = boosted = 0
    for path in pack_paths:
        if not path.is_file():
            continue
        print(f"Merging {path.name} …", flush=True)
        with path.open("r", encoding="utf-8", errors="replace") as f:
            for raw in f:
                parsed = imp.parse_line(raw)
                if not parsed:
                    continue
                phrase, importance = parsed
                parts, pruned = imp.pruned_parts_of(phrase)
                if not parts or len(parts) != len(pruned):
                    continue
                letterized = imp.letterized_pruned_parts(pruned)
                letters = imp.letters_of(letterized)
                if not letters or len(letters) > imp.DEFAULT_MAX_ENTRY_LENGTH:
                    continue
                key = "".join(letters)
                form = "".join(pruned)
                score = importance if importance > 0 else default_score
                prev = store.get(key)
                if prev is None:
                    store[key] = (form, score)
                    added += 1
                elif score > prev[1]:
                    store[key] = (prev[0], score)  # keep existing display form
                    boosted += 1

    items = sorted(store.values(), key=lambda e: (-e[1], len(e[0]), e[0].upper()))
    with combolist.open("w", encoding="utf-8", newline="\n") as f:
        for form, score in items:
            form = form.replace(";", "")
            if abs(score - round(score)) < 1e-9:
                f.write(f"{form};{int(round(score))}\n")
            else:
                f.write(f"{form};{score:.4f}\n")
    print(
        f"combolist: {before:,} → {len(items):,} "
        f"(+{added:,} new, {boosted:,} score bumps)",
        flush=True,
    )
    return added


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--exet-dir", type=Path, default=DEFAULT_EXET)
    ap.add_argument("--skip-kaikki", action="store_true")
    ap.add_argument("--skip-magpie", action="store_true")
    ap.add_argument("--skip-midas", action="store_true")
    ap.add_argument("--skip-englishidioms", action="store_true")
    ap.add_argument("--skip-wordnet", action="store_true")
    ap.add_argument(
        "--merge-combolist",
        action="store_true",
        help="Merge written packs into wordlists/combolist.txt",
    )
    ap.add_argument("--score", type=float, default=50.0, help="Default pack score")
    args = ap.parse_args(argv)

    exet_dir = args.exet_dir.resolve()
    out = exet_dir / "wordlists" / "_sources"
    out.mkdir(parents=True, exist_ok=True)

    # Slight score differentiation by source quality / noisiness.
    packs: list[Path] = []
    if not args.skip_magpie:
        fetch_magpie(out, score=min(args.score + 5, 60))
        packs.append(out / "idioms-magpie.txt")
    if not args.skip_midas:
        fetch_midas(out, score=args.score)
        packs.append(out / "idioms-midas.txt")
    if not args.skip_englishidioms:
        fetch_englishidioms(out, score=max(args.score - 5, 40))
        packs.append(out / "idioms-englishidioms.txt")
    if not args.skip_kaikki:
        fetch_kaikki(out, score=args.score)
        packs.append(out / "idioms-kaikki.txt")
    if not args.skip_wordnet:
        extract_wordnet_mwe(exet_dir, out, score=args.score)
        packs.append(out / "idioms-wordnet-mwe.txt")

    if args.merge_combolist:
        # If every fetch was skipped, still merge any idioms-*.txt already on disk.
        if not packs:
            packs = sorted(out.glob("idioms-*.txt"))
        if not packs:
            print("No idiom packs to merge", flush=True)
        else:
            merge_into_combolist(exet_dir, packs, args.score)

    print("done", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
