#!/usr/bin/env python3
"""Generic importer: turn files in exet/wordlists/ into Exet lexicon JS.

Supports common crossword list formats:
  word;score
  word::score
  score<TAB>word
  word          (unscored; treated as score 0)

Mirrors the Lufz index-word-list algorithm for English/Latin so the
generated files work with exet-lexicon.js (pattern index, anagram shards,
empty phones, identity stems, scores).

Usage:
  python tools/import-wordlists.py
  python tools/import-wordlists.py --only ettulist
  python tools/import-wordlists.py --wordlists-dir wordlists --out-dir wordlists/built

Writes:
  <out-dir>/<slug>-part-1.js   lexicon + index
  <out-dir>/<slug>-part-2.js   anagrams + phones + phindex + scores
  <out-dir>/<slug>-stems.js    identity stems
  <out-dir>/lexicons-manifest.js   merges into exetConfig.lexicons
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
from collections import defaultdict
from pathlib import Path

LETTERS = list("ABCDEFGHIJKLMNOPQRSTUVWXYZ")
LETTER_SET = set(LETTERS)
PUNCT = {"-", "'"}
SPACES = {" ", "\t", "\r", "\n", ".", ",", "!", "?"}

WILDIZE_ALL_BEYOND = 10
MIN_KEY_COUNT = 1024
AGM_INDEX_SHARDS = 2000
PHONE_INDEX_SHARDS = 2000
DEFAULT_MAX_ENTRY_LENGTH = 75
MAX_PART_BYTES = 22 * 1024 * 1024  # stay under GitHub's ~25MB soft limit

SKIP_SUFFIXES = {".zip", ".gz", ".bz2", ".7z", ".rar"}
LIST_SUFFIXES = {".txt", ".dict", ".tsv", ".csv", ".wl"}


# Friendly labels for known sources (stem → menu name).
DISPLAY_NAMES = {
    "spreadthewordlist": "Spread the Wordlist",
    "ettulist": "Ettu List",
    "crossword_wordlist": "Crossword Wordlist",
    "combolist": "ComboList",
    "million_union": "ComboList",  # legacy stem
    "xwordlist": "Crossword Nexus",
}


def humanize(stem: str) -> str:
    key = stem.lower()
    if key in DISPLAY_NAMES:
        return DISPLAY_NAMES[key]
    name = stem.replace("_", " ").replace("-", " ").strip()
    # Title-case words but keep short all-caps tokens (e.g. NYT) as-is.
    parts = []
    for w in name.split():
        if w.isupper() and len(w) <= 4:
            parts.append(w)
        else:
            parts.append(w[:1].upper() + w[1:].lower() if w else w)
    return " ".join(parts) or stem


def slugify(stem: str) -> str:
    s = re.sub(r"[^a-zA-Z0-9]+", "-", stem.strip()).strip("-").lower()
    return s or "wordlist"


def java_hash(key: str) -> int:
    """Match Lufz/Exet Java-style hash over Latin-1 / ASCII bytes."""
    h = 0
    for ch in key.encode("utf-8"):
        c = ch if ch < 128 else ch - 256
        h = ((h << 5) - h) + c
        h &= 0xFFFFFFFF
        if h >= 0x80000000:
            h -= 0x100000000
    return h


def index_shard(key: str, num_shards: int) -> int:
    shard = java_hash(key) % num_shards
    if shard < 0:
        shard += num_shards
    return shard


def parts_of(s: str, map_spaces: bool = True) -> list[str]:
    """English/Latin PartsOf: single-codepoint parts, spaces normalized."""
    if map_spaces:
        out_chars = []
        for ch in s:
            out_chars.append(" " if ch in SPACES else ch)
        s2 = "".join(out_chars)
    else:
        s2 = s
    parts: list[str] = []
    for ch in s2:
        if ch == " " and (not parts or parts[-1] == " "):
            continue
        parts.append(ch)
    return parts


def is_letter(ch: str) -> bool:
    return ch.upper() in LETTER_SET


def pruned_parts_of(s: str) -> tuple[list[str], list[str]]:
    parts = parts_of(s, map_spaces=True)
    pruned: list[str] = []
    for part in parts:
        if is_letter(part) or part in PUNCT or (
            part == " " and pruned and pruned[-1] != " "
        ):
            pruned.append(part)
    while pruned and pruned[-1] == " ":
        pruned.pop()
    return parts, pruned


def letterized_pruned_parts(pruned: list[str]) -> list[str]:
    result: list[str] = []
    for part in pruned:
        if is_letter(part):
            result.append(part.upper())
        elif result and result[-1] != " ":
            result.append(" ")
    while result and result[-1] == " ":
        result.pop()
    return result


def letters_of(letterized: list[str]) -> list[str]:
    return [p for p in letterized if p in LETTER_SET]


def parse_line(line: str) -> tuple[str, float] | None:
    line = line.strip()
    if not line or line.startswith("#"):
        return None
    if "\t" in line:
        left, right = line.split("\t", 1)
        left, right = left.strip(), right.strip()
        if not right:
            return None
        # score\tword  OR  word\tscore
        if _is_number(left) and not _is_number(right):
            return right, float(left)
        if _is_number(right) and not _is_number(left):
            return left, float(right)
        return right, float(left) if _is_number(left) else 0.0
    if "::" in line:
        phrase, score_s = line.split("::", 1)
        phrase = phrase.strip()
        if not phrase:
            return None
        try:
            return phrase, float(score_s.strip())
        except ValueError:
            return phrase, 0.0
    if ";" in line:
        phrase, score_s = line.rsplit(";", 1)
        phrase = phrase.strip()
        if not phrase:
            return None
        try:
            return phrase, float(score_s.strip())
        except ValueError:
            return phrase, 0.0
    return line, 0.0


def _is_number(s: str) -> bool:
    try:
        float(s)
        return True
    except ValueError:
        return False


class PhraseInfo:
    __slots__ = ("normalized", "importance", "forms", "base_index")

    def __init__(self, normalized: str):
        self.normalized = normalized
        self.importance = 0.0
        self.forms: set[str] = set()
        self.base_index = 0


def read_wordlist(path: Path, max_entry_length: int = DEFAULT_MAX_ENTRY_LENGTH):
    phrase_infos: list[PhraseInfo] = []
    # index 0: empty string sentinel
    empty = PhraseInfo("")
    empty.forms.add("")
    phrase_infos.append(empty)

    by_norm: dict[str, int] = {}
    total = 0
    kept = 0
    skipped = 0

    with path.open("r", encoding="utf-8", errors="replace") as f:
        for raw in f:
            total += 1
            parsed = parse_line(raw)
            if not parsed:
                skipped += 1
                continue
            phrase, importance = parsed
            parts, pruned = pruned_parts_of(phrase)
            if not parts or len(parts) != len(pruned):
                # Unrecognized characters (digits, $, etc.) — same as Lufz skip
                skipped += 1
                continue
            letterized = letterized_pruned_parts(pruned)
            letters = letters_of(letterized)
            if not letters:
                skipped += 1
                continue
            if len(letters) > max_entry_length:
                skipped += 1
                continue
            normalized = "".join(letters)
            form = "".join(pruned)
            if normalized not in by_norm:
                by_norm[normalized] = len(phrase_infos)
                phrase_infos.append(PhraseInfo(normalized))
            info = phrase_infos[by_norm[normalized]]
            info.forms.add(form)
            if importance > info.importance:
                info.importance = importance
            kept += 1

    # Sort by importance desc, then shorter normalized first (Lufz)
    head = phrase_infos[:1]
    tail = phrase_infos[1:]
    tail.sort(key=lambda p: (-p.importance, len(p.normalized), p.normalized))
    phrase_infos = head + tail
    if len(phrase_infos) > 1:
        phrase_infos[0].importance = max(
            phrase_infos[0].importance, phrase_infos[1].importance + 1
        )

    base = 0
    for info in phrase_infos:
        info.base_index = base
        base += len(info.forms)

    return phrase_infos, total, kept, skipped


def lex_key(normalized: str) -> str:
    letters = list(normalized)  # already A-Z only
    return "".join(
        letters[i] if i < WILDIZE_ALL_BEYOND else "?" for i in range(len(letters))
    )


def all_wild(key: str) -> bool:
    return bool(key) and all(ch == "?" for ch in key)


def add_key_counts(normalized: str, count: int, counts: dict[str, int]) -> None:
    """Count wildized pattern keys.

    Short keys (len <= 7): full 2^n power set (same as Lufz).
    Longer keys: exact key + progressive right-to-left wildcards only.
    That matches Exet's documented fallback lookup and avoids 2^10 blowups
    on million-entry lists (which otherwise thrash multi-GB dicts).
    """
    key = lex_key(normalized)
    parts = list(key)
    n = min(len(parts), WILDIZE_ALL_BEYOND)
    if n <= 7:
        limit = 1 << n
        for pattern in range(limit):
            variant = parts[:]
            for i in range(n):
                if pattern & (1 << i):
                    variant[i] = "?"
            counts["".join(variant)] += count
        return
    # Progressive trailing wildcards (exact, then ??? from the right).
    counts["".join(parts)] += count
    variant = parts[:]
    for i in range(n - 1, -1, -1):
        variant[i] = "?"
        counts["".join(variant)] += count


def add_keys(
    normalized: str,
    indexing_keys: set[str],
    lex_indices: list[int],
    index: dict[str, set[int]],
) -> None:
    key = lex_key(normalized)
    parts = list(key)
    n = min(len(parts), WILDIZE_ALL_BEYOND)
    if n <= 7:
        limit = 1 << n
        for pattern in range(limit):
            variant = parts[:]
            for i in range(n):
                if pattern & (1 << i):
                    variant[i] = "?"
            key_variant = "".join(variant)
            if key_variant not in indexing_keys:
                continue
            bucket = index[key_variant]
            for li in lex_indices:
                bucket.add(li)
        return
    candidates = ["".join(parts)]
    variant = parts[:]
    for i in range(n - 1, -1, -1):
        variant[i] = "?"
        candidates.append("".join(variant))
    for key_variant in candidates:
        if key_variant not in indexing_keys:
            continue
        bucket = index[key_variant]
        for li in lex_indices:
            bucket.add(li)


def build_indices(phrase_infos: list[PhraseInfo]):
    t0 = time.time()
    counts: dict[str, int] = defaultdict(int)
    n_infos = len(phrase_infos)
    report_every = 50000 if n_infos > 500000 else 20000
    for i, info in enumerate(phrase_infos):
        if not info.normalized:
            continue
        add_key_counts(info.normalized, len(info.forms), counts)
        if i and i % report_every == 0:
            print(
                f"  key counts @ {i}/{n_infos} ({len(counts):,} keys, "
                f"{time.time() - t0:.0f}s)",
                flush=True,
            )
    print(f"  pre-filter keys: {len(counts)} ({time.time() - t0:.1f}s)", flush=True)

    indexing_keys = {
        k for k, c in counts.items() if c >= MIN_KEY_COUNT or all_wild(k)
    }
    print(f"  post-filter keys: {len(indexing_keys)}", flush=True)
    del counts

    index: dict[str, set[int]] = defaultdict(set)
    agm: list[list[int]] = [[] for _ in range(AGM_INDEX_SHARDS)]
    t1 = time.time()
    for i, info in enumerate(phrase_infos):
        if not info.normalized:
            continue
        forms_sorted = sorted(info.forms)
        lex_indices = [info.base_index + j for j in range(len(forms_sorted))]
        add_keys(info.normalized, indexing_keys, lex_indices, index)
        agm_key = "".join(sorted(info.normalized))
        shard = index_shard(agm_key, AGM_INDEX_SHARDS)
        agm[shard].extend(lex_indices)
        if i and i % report_every == 0:
            print(f"  index build @ {i}/{n_infos} ({time.time() - t1:.0f}s)", flush=True)
    print(f"  index built ({time.time() - t1:.1f}s)", flush=True)

    # Sort each index bucket (required for indexLimit early-exit)
    index_out = {k: sorted(v) for k, v in index.items()}
    return index_out, agm


def flat_lexicon(phrase_infos: list[PhraseInfo]) -> tuple[list[str], list[float]]:
    words: list[str] = []
    scores: list[float] = []
    for info in phrase_infos:
        for form in sorted(info.forms):
            words.append(form)
            scores.append(info.importance)
    return words, scores


def js_section(obj: dict) -> str:
    body = json.dumps(obj, ensure_ascii=False, separators=(",", ":"))
    # Prefer JSON.parse("...") so backticks/apostrophes in words cannot break
    # the surrounding script. json.dumps already escapes quotes and backslashes.
    return (
        'exetLexicon = {...((typeof exetLexicon == "object" && exetLexicon) ? '
        f"exetLexicon : {{}}), ...JSON.parse({json.dumps(body)})}};\n"
    )


def write_lexicon_files(
    out_dir: Path,
    slug: str,
    lexicon_id: str,
    words: list[str],
    scores: list[float],
    index: dict[str, list[int]],
    agm: list[list[int]],
) -> list[str]:
    out_dir.mkdir(parents=True, exist_ok=True)
    phones = [[] for _ in words]
    phindex = [[] for _ in range(PHONE_INDEX_SHARDS)]
    stems = list(range(len(words)))  # identity cycles

    part1 = out_dir / f"{slug}-part-1.js"
    part2 = out_dir / f"{slug}-part-2.js"
    stems_path = out_dir / f"{slug}-stems.js"

    with part1.open("w", encoding="utf-8", newline="\n") as f:
        f.write(
            js_section(
                {
                    "id": lexicon_id,
                    "language": "en",
                    "script": "Latin",
                    "letters": LETTERS,
                    "lexicon": words,
                }
            )
        )
        f.write(js_section({"index": index}))

    with part2.open("w", encoding="utf-8", newline="\n") as f:
        f.write(js_section({"anagrams": agm}))
        f.write(js_section({"phones": phones}))
        f.write(js_section({"phindex": phindex}))
        f.write(js_section({"scores": scores}))

    with stems_path.open("w", encoding="utf-8", newline="\n") as f:
        f.write(js_section({"stemsId": lexicon_id, "stems": stems}))

    rel = [part1.name, part2.name, stems_path.name]
    for name in rel:
        size = (out_dir / name).stat().st_size
        print(f"  wrote {name} ({size / (1024 * 1024):.1f} MB)", flush=True)
        if size > MAX_PART_BYTES:
            print(
                f"  warning: {name} exceeds {MAX_PART_BYTES // (1024 * 1024)} MB; "
                "consider splitting further for GitHub hosting",
                flush=True,
            )
    return rel


def discover_sources(wordlists_dir: Path) -> list[Path]:
    """Pick unique source files; prefer .txt over .dict for the same stem."""
    by_stem: dict[str, Path] = {}
    priority = {".txt": 0, ".tsv": 1, ".csv": 2, ".wl": 3, ".dict": 4}
    for path in sorted(wordlists_dir.iterdir()):
        if not path.is_file():
            continue
        if path.suffix.lower() in SKIP_SUFFIXES:
            continue
        if path.suffix.lower() not in LIST_SUFFIXES:
            continue
        stem = path.stem.lower()
        prev = by_stem.get(stem)
        if prev is None or priority.get(path.suffix.lower(), 99) < priority.get(
            prev.suffix.lower(), 99
        ):
            by_stem[stem] = path
    return [by_stem[k] for k in sorted(by_stem)]


def load_existing_manifest(manifest: Path) -> dict:
    if not manifest.is_file():
        return {}
    text = manifest.read_text(encoding="utf-8")
    m = re.search(
        r"Object\.assign\(\s*exetConfig\.lexicons\s*,\s*(\{.*\})\s*\)\s*;",
        text,
        re.S,
    )
    if not m:
        return {}
    try:
        return json.loads(m.group(1))
    except json.JSONDecodeError:
        return {}


def write_manifest(
    out_dir: Path,
    wordlists_dir: Path,
    entries: list[tuple[str, list[str]]],
    merge: bool = False,
) -> Path:
    """entries: (display_name, list of filenames in out_dir)."""
    # Paths in exetConfig are relative to exet.html
    try:
        rel_out = out_dir.resolve().relative_to(wordlists_dir.parent.resolve())
    except ValueError:
        rel_out = out_dir

    manifest = out_dir / "lexicons-manifest.js"
    lexicons = load_existing_manifest(manifest) if merge else {}
    for name, files in entries:
        lexicons[name] = [
            str(Path(rel_out) / f).replace("\\", "/") for f in files
        ]

    payload = json.dumps(lexicons, ensure_ascii=False, indent=2)
    manifest.write_text(
        "/** Auto-generated by tools/import-wordlists.py — do not edit. */\n"
        "if (typeof exetConfig === 'undefined') { var exetConfig = {}; }\n"
        "if (!exetConfig.lexicons) { exetConfig.lexicons = {}; }\n"
        f"Object.assign(exetConfig.lexicons, {payload});\n",
        encoding="utf-8",
        newline="\n",
    )
    print(f"wrote manifest {manifest}", flush=True)
    return manifest


def ensure_html_loads_manifest(exet_html: Path, manifest_src: str) -> None:
    text = exet_html.read_text(encoding="utf-8")
    tag = f'<script src="{manifest_src}"></script>'
    if f'src="{manifest_src}"' in text or f"src='{manifest_src}'" in text:
        print(f"exet.html already loads {manifest_src}", flush=True)
        return
    # Insert immediately after the exetConfig script block closes.
    markers = ("let exetConfig = {", "var exetConfig = {", "exetConfig = {")
    idx = -1
    for marker in markers:
        idx = text.find(marker)
        if idx >= 0:
            break
    if idx < 0:
        raise SystemExit("Could not find exetConfig in exet.html")
    close = text.find("</script>", idx)
    if close < 0:
        raise SystemExit("Could not find end of exetConfig script in exet.html")
    insert_at = close + len("</script>")
    updated = text[:insert_at] + f"\n  {tag}" + text[insert_at:]
    exet_html.write_text(updated, encoding="utf-8", newline="\n")
    print(f"updated {exet_html.name} to load {manifest_src}", flush=True)


def import_one(path: Path, out_dir: Path) -> tuple[str, list[str]]:
    display = humanize(path.stem)
    slug = slugify(path.stem)
    lexicon_id = f"{display.replace(' ', '-')}-imported"
    print(f"\n=== {path.name} -> {display} ({slug}) ===", flush=True)
    t0 = time.time()
    phrase_infos, total, kept, skipped = read_wordlist(path)
    n_forms = sum(len(p.forms) for p in phrase_infos)
    print(
        f"  lines={total} kept={kept} skipped={skipped} "
        f"groups={len(phrase_infos)-1} forms={n_forms-1} "
        f"({time.time()-t0:.1f}s)",
        flush=True,
    )
    if n_forms <= 1:
        raise SystemExit(f"No usable entries in {path}")

    index, agm = build_indices(phrase_infos)
    words, scores = flat_lexicon(phrase_infos)
    files = write_lexicon_files(
        out_dir, slug, lexicon_id, words, scores, index, agm
    )
    print(f"  done in {time.time()-t0:.1f}s", flush=True)
    return display, files


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--wordlists-dir",
        type=Path,
        default=None,
        help="Folder of source wordlists (default: ../wordlists)",
    )
    ap.add_argument(
        "--out-dir",
        type=Path,
        default=None,
        help="Output folder for built lexicons (default: <wordlists>/built)",
    )
    ap.add_argument(
        "--only",
        action="append",
        default=[],
        help="Only import stems matching this substring (repeatable)",
    )
    ap.add_argument(
        "--exet-html",
        type=Path,
        default=None,
        help="exet.html to patch with manifest script tag",
    )
    ap.add_argument(
        "--no-html-patch",
        action="store_true",
        help="Do not modify exet.html",
    )
    args = ap.parse_args(argv)

    tools_dir = Path(__file__).resolve().parent
    exet_dir = tools_dir.parent
    wordlists_dir = (args.wordlists_dir or (exet_dir / "wordlists")).resolve()
    out_dir = (args.out_dir or (wordlists_dir / "built")).resolve()
    exet_html = (args.exet_html or (exet_dir / "exet.html")).resolve()

    if not wordlists_dir.is_dir():
        print(f"wordlists dir not found: {wordlists_dir}", file=sys.stderr)
        return 1

    sources = discover_sources(wordlists_dir)
    if args.only:
        needles = [o.lower() for o in args.only]
        sources = [
            p for p in sources if any(n in p.stem.lower() for n in needles)
        ]
    if not sources:
        print("No wordlist source files found.", file=sys.stderr)
        return 1

    print(f"Sources ({len(sources)}):")
    for p in sources:
        print(f"  {p.name}")

    entries: list[tuple[str, list[str]]] = []
    for path in sources:
        display, files = import_one(path, out_dir)
        entries.append((display, files))

    # --only should extend the existing menu, not wipe other imported lists.
    write_manifest(out_dir, wordlists_dir, entries, merge=bool(args.only))
    if not args.no_html_patch:
        try:
            rel_manifest = (
                out_dir.relative_to(exet_dir) / "lexicons-manifest.js"
            ).as_posix()
        except ValueError:
            rel_manifest = "wordlists/built/lexicons-manifest.js"
        ensure_html_loads_manifest(exet_html, rel_manifest)

    print("\nAll done.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
