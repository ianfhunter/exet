#!/usr/bin/env python3
"""Build wordlists/combolist.txt (ComboList) from multiple scored/unscored sources.

Score policy (higher = preferred in Exet):
  - Crossword sources keep native scores (max wins on overlap).
  - xd-clues.zip frequency adds a small boost to published answers
    and inserts missing answers at a mid-low default.
  - Unscored OpenList defaults to 15; dwyl/general dict defaults to 5.
  - Display form is taken from the highest-priority source that has the word.

Usage:
  python tools/extract-exet-lexicons.py   # Nediger + Lufz -> _sources/
  python tools/fetch-extra-wordlists.py   # Broda / ECND / UKACD / queer
  python tools/build-million-union.py
  python tools/import-wordlists.py --only combolist
"""

from __future__ import annotations

import argparse
import csv
import importlib.util
import io
import math
import sys
import time
import zipfile
from pathlib import Path

TOOLS = Path(__file__).resolve().parent


def _load_importer():
    path = TOOLS / "import-wordlists.py"
    spec = importlib.util.spec_from_file_location("import_wordlists", path)
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    return mod


imp = _load_importer()
parse_line = imp.parse_line
pruned_parts_of = imp.pruned_parts_of
letterized_pruned_parts = imp.letterized_pruned_parts
letters_of = imp.letters_of
DEFAULT_MAX_ENTRY_LENGTH = imp.DEFAULT_MAX_ENTRY_LENGTH


# (relative path under exet/, priority 0=best form, default_score if parsed score is 0)
SOURCES = [
    ("wordlists/_sources/nediger.txt", 0, 50.0),
    ("wordlists/_sources/lufz-en.txt", 1, 50.0),
    ("wordlists/_sources/xwordlist.dict", 2, 40.0),  # Crossword Nexus (MIT)
    ("wordlists/_sources/broda.txt", 3, 40.0),
    ("wordlists/spreadthewordlist.txt", 4, 40.0),
    ("wordlists/_sources/matts_wordlist.txt", 5, 35.0),  # CC BY-NC-SA
    ("wordlists/crossword_wordlist.txt", 6, 35.0),  # Chris Jones
    ("wordlists/ettulist.txt", 7, 30.0),
    # Curated phrase / name packs
    ("wordlists/_sources/nzfeng-core.txt", 8, 55.0),
    ("wordlists/_sources/nzfeng-contemporary.txt", 8, 50.0),
    ("wordlists/_sources/nzfeng-idioms.txt", 8, 55.0),
    ("wordlists/_sources/ecnd-names.txt", 8, 64.0),
    ("wordlists/_sources/ecnd-places.txt", 8, 64.0),
    ("wordlists/_sources/maiamcc-queer-scored.dict", 9, 50.0),
    ("wordlists/_sources/queer-scored.dict", 9, 50.0),
    ("wordlists/_sources/maiamcc-celebs-scored.dict", 9, 55.0),
    ("wordlists/_sources/maiamcc-colleges-scored.dict", 9, 50.0),
    ("wordlists/_sources/maiamcc-netspeak-scored.dict", 9, 40.0),
    ("wordlists/_sources/maiamcc-urbandictionary-scored.dict", 9, 35.0),
    ("wordlists/_sources/maiamcc-websites-scored.dict", 9, 45.0),
    ("wordlists/_sources/geo-countrynames.txt", 9, 60.0),
    ("wordlists/_sources/geo-citynames.txt", 10, 55.0),
    ("wordlists/_sources/geo-states-provinces.txt", 10, 55.0),
    ("wordlists/_sources/geo-jobtitles.txt", 10, 45.0),
    ("wordlists/_sources/geo-commonwebsitephrases.txt", 11, 35.0),
    ("wordlists/_sources/ukacd.txt", 11, 45.0),
    ("wordlists/_sources/openlist_valid.txt", 12, 15.0),
    ("wordlists/_sources/words_alpha.txt", 13, 5.0),
]


def normalize_entry(phrase: str, importance: float, default_score: float):
    parts, pruned = pruned_parts_of(phrase)
    if not parts or len(parts) != len(pruned):
        return None
    letterized = letterized_pruned_parts(pruned)
    letters = letters_of(letterized)
    if not letters or len(letters) > DEFAULT_MAX_ENTRY_LENGTH:
        return None
    key = "".join(letters)
    form = "".join(pruned)
    score = importance if importance > 0 else default_score
    return key, form, score


def ingest(path: Path, priority: int, default_score: float, store: dict) -> tuple[int, int]:
    kept = skipped = 0
    with path.open("r", encoding="utf-8", errors="replace") as f:
        for raw in f:
            parsed = parse_line(raw)
            if not parsed:
                skipped += 1
                continue
            phrase, importance = parsed
            got = normalize_entry(phrase, importance, default_score)
            if not got:
                skipped += 1
                continue
            key, form, score = got
            prev = store.get(key)
            if prev is None:
                store[key] = {"form": form, "score": score, "priority": priority}
            else:
                if score > prev["score"]:
                    prev["score"] = score
                if priority < prev["priority"]:
                    prev["form"] = form
                    prev["priority"] = priority
            kept += 1
    return kept, skipped


def apply_xd_boost(exet_dir: Path, store: dict) -> tuple[int, int]:
    """Boost / insert answers from wordlists/xd-clues.zip by published frequency."""
    zpath = exet_dir / "wordlists" / "xd-clues.zip"
    if not zpath.is_file():
        print("MISSING wordlists/xd-clues.zip — skip frequency boost", flush=True)
        return 0, 0

    csv.field_size_limit(sys.maxsize)
    counts: dict[str, int] = {}
    forms: dict[str, str] = {}
    rows = 0
    print("Scanning xd-clues.zip for answer frequencies ...", flush=True)
    with zipfile.ZipFile(zpath) as z:
        with z.open("xd/clues.tsv") as f:
            text = io.TextIOWrapper(f, encoding="utf-8", errors="replace")
            reader = csv.DictReader(text, delimiter="\t")
            for row in reader:
                rows += 1
                ans = (row.get("answer") or "").strip()
                if not ans:
                    continue
                got = normalize_entry(ans, 0.0, 0.0)
                if not got:
                    continue
                key, form, _ = got
                if not (2 <= len(key) <= 21):
                    continue
                counts[key] = counts.get(key, 0) + 1
                forms.setdefault(key, form)
                if rows % 3_000_000 == 0:
                    print(f"  xd rows={rows:,} unique={len(counts):,}", flush=True)

    boosted = inserted = 0
    for key, count in counts.items():
        # log10 boost: 1→0, 10→~3, 100→~6, 1000→~9, capped at 12
        boost = min(12.0, 3.0 * math.log10(count + 1))
        if key in store:
            store[key]["score"] = min(99.5, store[key]["score"] + boost)
            boosted += 1
        else:
            # Published but missing from all lists — mid-low floor + boost
            base = 22.0 + boost
            store[key] = {
                "form": forms[key],
                "score": min(55.0, base),
                "priority": 15,
            }
            inserted += 1
    print(
        f"  xd rows={rows:,} unique={len(counts):,} "
        f"boosted={boosted:,} inserted={inserted:,}",
        flush=True,
    )
    return boosted, inserted


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--exet-dir", type=Path, default=TOOLS.parent)
    ap.add_argument("--out", type=Path, default=None)
    ap.add_argument(
        "--no-xd",
        action="store_true",
        help="Skip xd-clues.zip frequency boost",
    )
    args = ap.parse_args(argv)
    exet_dir = args.exet_dir.resolve()
    out = (args.out or (exet_dir / "wordlists" / "combolist.txt")).resolve()

    store: dict[str, dict] = {}
    t0 = time.time()
    for rel, priority, default_score in SOURCES:
        path = exet_dir / rel
        if not path.is_file():
            print(f"MISSING {rel} — skip", flush=True)
            continue
        print(f"Reading {rel} ...", flush=True)
        kept, skipped = ingest(path, priority, default_score, store)
        print(
            f"  kept={kept:,} skipped={skipped:,} union={len(store):,}",
            flush=True,
        )

    if not args.no_xd:
        apply_xd_boost(exet_dir, store)
        print(f"  union after xd={len(store):,}", flush=True)

    items = sorted(
        store.values(),
        key=lambda e: (-e["score"], len(e["form"]), e["form"].upper()),
    )
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", encoding="utf-8", newline="\n") as f:
        for e in items:
            form = e["form"].replace(";", "")
            score = e["score"]
            if abs(score - round(score)) < 1e-9:
                f.write(f"{form};{int(round(score))}\n")
            else:
                f.write(f"{form};{score:.4f}\n")

    print(
        f"\nWrote {out} ({len(items):,} entries) in {time.time() - t0:.1f}s",
        flush=True,
    )
    if len(items) < 1_000_000:
        print(
            f"WARNING: under 1,000,000 ({len(items):,}). "
            "Check missing sources under wordlists/_sources/.",
            flush=True,
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
