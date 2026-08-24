#!/usr/bin/env python3
"""Build exet-prior-clues.js — offline answer → published-clue lookup for Exet.

Sources (best-effort, any combination):
  - wordlists/_sources/georgeho-data.db  (cryptics.georgeho.org SQLite, ~187 MB)
  - wordlists/xd-clues.zip               (xd.saul.pw clue corpus, ~67 MB)
  - wordlists/_sources/ginsberg-cluedata (Matt Ginsberg Cluer DB, from tiwwdty.com)

Fetch sources first:
  python tools/fetch-prior-clues-data.py

Usage:
  python tools/build-prior-clues-index.py
  python tools/build-prior-clues-index.py --max-per-answer 50   # optional cap
"""

from __future__ import annotations

import argparse
import csv
import io
import json
import re
import sqlite3
import struct
import sys
import time
import zipfile
from pathlib import Path

TOOLS = Path(__file__).resolve().parent
EXET = TOOLS.parent
DEFAULT_OUT = EXET / "wordlists" / "built"
MAX_PART_BYTES = 22 * 1024 * 1024

# clue_text -> count (for ranking within an answer)
ClueBucket = dict[str, int]
# answer_key -> ClueBucket
AnswerStore = dict[str, ClueBucket]
# clue_text -> meta string (first seen wins unless we prefer georgeho)
ClueMeta = dict[str, str]


def letter_key(s: str) -> str:
    return re.sub(r"[^A-Za-z]", "", s).upper()


def clean_clue(s: str) -> str:
    s = (s or "").replace("\r", " ").replace("\n", " ").strip()
    s = re.sub(r"\s+", " ", s)
    return s[:500]


def add_clue(store: AnswerStore, meta_map: ClueMeta, answer: str, clue: str, meta: str) -> None:
    key = letter_key(answer)
    clue = clean_clue(clue)
    if not key or len(key) < 2 or len(key) > 75 or not clue:
        return
    bucket = store.setdefault(key, {})
    bucket[clue] = bucket.get(clue, 0) + 1
    if clue not in meta_map:
        meta_map[clue] = meta


def ingest_georgeho(db_path: Path, store: AnswerStore, meta_map: ClueMeta) -> int:
    if not db_path.is_file():
        print(f"MISSING {db_path} — skip georgeho", flush=True)
        return 0
    print(f"Reading georgeho SQLite {db_path.name} ...", flush=True)
    conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    cur = conn.execute(
        """
        SELECT clue, answer, definition, puzzle_date, puzzle_name, source
        FROM clues
        WHERE answer IS NOT NULL AND clue IS NOT NULL
        """
    )
    n = 0
    while True:
        rows = cur.fetchmany(50_000)
        if not rows:
            break
        for row in rows:
            definition = (row["definition"] or "").strip()
            meta = "|".join(
                [
                    "g",
                    (row["source"] or "").strip(),
                    (row["puzzle_date"] or "").strip(),
                    (row["puzzle_name"] or "").strip(),
                    definition,
                ]
            )
            add_clue(store, meta_map, row["answer"], row["clue"], meta)
            n += 1
        if n % 200_000 == 0:
            print(f"  georgeho rows={n:,} answers={len(store):,}", flush=True)
    conn.close()
    print(f"  georgeho done rows={n:,} answers={len(store):,}", flush=True)
    return n


def ingest_xd(zip_path: Path, store: AnswerStore, meta_map: ClueMeta) -> int:
    if not zip_path.is_file():
        print(f"MISSING {zip_path} — skip xd-clues", flush=True)
        return 0
    print(f"Reading xd clues from {zip_path.name} ...", flush=True)
    try:
        zf = zipfile.ZipFile(zip_path, "r", allowZip64=True)
    except zipfile.BadZipFile as e:
        print(f"  FAIL bad/incomplete zip ({e}). Re-run fetch-prior-clues-data.py", flush=True)
        return 0
    names = zf.namelist()
    tsv_name = next((n for n in names if n.endswith("clues.tsv")), None)
    if not tsv_name:
        print("  FAIL no clues.tsv in zip", flush=True)
        return 0
    csv.field_size_limit(sys.maxsize)
    n = 0
    with zf.open(tsv_name) as raw:
        text = io.TextIOWrapper(raw, encoding="utf-8", errors="replace")
        reader = csv.reader(text, delimiter="\t")
        header = next(reader, None)
        if not header:
            return 0
        cols = {h.strip().lower(): i for i, h in enumerate(header)}

        def col(row: list[str], *names: str) -> str:
            for name in names:
                if name in cols and cols[name] < len(row):
                    return row[cols[name]].strip()
            return ""

        # xd clues.tsv: publication, year, answer, clue (names may vary)
        if "answer" not in cols:
            # fallback: last col = clue, third = answer
            for row in reader:
                if len(row) < 4:
                    continue
                pub, year, ans, clue = row[0], row[1], row[2], row[3]
                meta = f"x|{pub}|{year}|"
                add_clue(store, meta_map, ans, clue, meta)
                n += 1
        else:
            for row in reader:
                ans = col(row, "answer")
                clue = col(row, "clue", "cluetext", "text")
                pub = col(row, "publication", "pub", "source")
                year = col(row, "year", "date")
                if not ans or not clue:
                    continue
                meta = f"x|{pub}|{year}|"
                add_clue(store, meta_map, ans, clue, meta)
                n += 1
                if n % 1_000_000 == 0:
                    print(f"  xd rows={n:,} answers={len(store):,}", flush=True)
    print(f"  xd done rows={n:,} answers={len(store):,}", flush=True)
    return n


def ingest_ginsberg(cluedata_path: Path, store: AnswerStore, meta_map: ClueMeta) -> int:
    """Ingest Matt Ginsberg Cluer binary (same format Crosshare uses)."""
    if not cluedata_path.is_file():
        print(f"MISSING {cluedata_path} — skip ginsberg", flush=True)
        return 0
    print(f"Reading Ginsberg cluedata {cluedata_path.name} ...", flush=True)
    words: list[str] = []
    clues: list[str] = []
    n = 0
    with cluedata_path.open("rb") as f:
        numwords = struct.unpack("<I", f.read(4))[0]
        for _ in range(numwords):
            length = struct.unpack("<B", f.read(1))[0]
            raw = struct.unpack(f"<{length}s", f.read(length))[0]
            words.append(raw.decode("ascii", errors="replace"))

        numclues = struct.unpack("<I", f.read(4))[0]
        for _ in range(numclues):
            length = struct.unpack("<B", f.read(1))[0]
            raw = struct.unpack(f"<{length}s", f.read(length))[0]
            clues.append(raw.decode("latin-1", errors="replace"))
            numtraps = struct.unpack("<I", f.read(4))[0]
            if numtraps:
                f.read(4 * numtraps)

        word_idx = struct.unpack("<I", f.read(4))[0]
        while True:
            freq = struct.unpack("<h", f.read(2))[0]
            _diff = struct.unpack("<h", f.read(2))[0]
            yr = struct.unpack("<h", f.read(2))[0]
            _th = struct.unpack("<b", f.read(1))[0]
            pnum = struct.unpack("<b", f.read(1))[0]
            cnum = struct.unpack("<I", f.read(4))[0]
            if word_idx >= len(words) or cnum >= len(clues):
                break
            answer = words[word_idx]
            clue = clues[cnum]
            pub = "NYT" if pnum == 8 else (f"pub{pnum}" if pnum else "Ginsberg")
            year = str(yr) if yr > 0 else ""
            meta = f"b|{pub}|{year}|{max(freq, 1)}"
            # Weight by published frequency for ranking within an answer
            key = letter_key(answer)
            clue_clean = clean_clue(clue)
            if key and len(key) >= 2 and len(key) <= 75 and clue_clean:
                bucket = store.setdefault(key, {})
                bucket[clue_clean] = bucket.get(clue_clean, 0) + max(freq, 1)
                if clue_clean not in meta_map:
                    meta_map[clue_clean] = meta
                n += 1
            try:
                word_idx = struct.unpack("<I", f.read(4))[0]
            except struct.error:
                break
            if n and n % 500_000 == 0:
                print(f"  ginsberg rows={n:,} answers={len(store):,}", flush=True)
    print(f"  ginsberg done rows={n:,} answers={len(store):,}", flush=True)
    return n


def build_index(
    store: AnswerStore, meta_map: ClueMeta, max_per_answer: int
) -> tuple[list[str], list[str], dict[str, list[list[int]]]]:
    clues_out: list[str] = []
    meta_out: list[str] = []
    clue_idx: dict[str, int] = {}
    meta_idx: dict[str, int] = {}

    def intern_clue(s: str) -> int:
        if s not in clue_idx:
            clue_idx[s] = len(clues_out)
            clues_out.append(s)
        return clue_idx[s]

    def intern_meta(s: str) -> int:
        if s not in meta_idx:
            meta_idx[s] = len(meta_out)
            meta_out.append(s)
        return meta_idx[s]

    index: dict[str, list[list[int]]] = {}
    for ans_key, bucket in store.items():
        ranked = sorted(bucket.items(), key=lambda kv: (-kv[1], kv[0]))
        if max_per_answer > 0:
            ranked = ranked[:max_per_answer]
        rows: list[list[int]] = []
        for clue_text, _count in ranked:
            rows.append([intern_clue(clue_text), intern_meta(meta_map.get(clue_text, ""))])
        if rows:
            index[ans_key] = rows
    return clues_out, meta_out, index


def _json_payload_size(obj: dict) -> int:
    return len(json.dumps(obj, separators=(",", ":"), ensure_ascii=False).encode("utf-8"))


def _item_json_size(item) -> int:
    return len(json.dumps(item, separators=(",", ":"), ensure_ascii=False).encode("utf-8"))


def _split_array(arr: list, max_bytes: int) -> list[list]:
    chunks: list[list] = []
    current: list = []
    current_size = 2  # []
    for item in arr:
        item_size = _item_json_size(item) + (1 if current else 0)
        if current and current_size + item_size > max_bytes:
            chunks.append(current)
            current = [item]
            current_size = 2 + _item_json_size(item)
        else:
            current.append(item)
            current_size += item_size
    if current:
        chunks.append(current)
    return chunks


def _split_index(index: dict[str, list], max_bytes: int) -> list[dict]:
    chunks: list[dict] = []
    current: dict = {}
    current_size = 2  # {}
    for k in sorted(index.keys()):
        entry_size = _item_json_size(k) + 1 + _item_json_size(index[k])
        if current and current_size + entry_size > max_bytes:
            chunks.append(current)
            current = {k: index[k]}
            current_size = 2 + entry_size
        else:
            current[k] = index[k]
            current_size += entry_size
    if current:
        chunks.append(current)
    return chunks


def _part_payloads(
    clues: list[str], meta: list[str], index: dict, stats: dict
) -> list[dict]:
    budget = MAX_PART_BYTES - 512
    payloads: list[dict] = []
    clue_chunks = _split_array(clues, budget)
    meta_chunks = _split_array(meta, budget)
    index_chunks = _split_index(index, budget)
    for i, chunk in enumerate(clue_chunks):
        part: dict = {"clues": chunk}
        if i == 0:
            part["stats"] = stats
        payloads.append(part)
    for chunk in meta_chunks:
        payloads.append({"meta": chunk})
    for chunk in index_chunks:
        payloads.append({"index": chunk})
    return payloads


def write_parts(exet_dir: Path, clues: list[str], meta: list[str], index: dict, stats: dict) -> list[str]:
    out_dir = exet_dir / "wordlists" / "built"
    out_dir.mkdir(parents=True, exist_ok=True)
    payloads = _part_payloads(clues, meta, index, stats)
    rel_paths: list[str] = []
    try:
        rel_prefix = out_dir.resolve().relative_to(exet_dir.resolve()).as_posix()
    except ValueError:
        rel_prefix = out_dir.as_posix()

    for i, part in enumerate(payloads, start=1):
        name = f"prior-clues-part-{i:02d}.js"
        path = out_dir / name
        body = "exetPriorClues.loadPart(" + json.dumps(part, separators=(",", ":"), ensure_ascii=False) + ");\n"
        path.write_text(body, encoding="utf-8")
        size = path.stat().st_size
        rel = f"{rel_prefix}/{name}"
        rel_paths.append(rel)
        print(f"  wrote {rel} ({size / (1024 * 1024):.1f} MB)", flush=True)
        if size > MAX_PART_BYTES:
            print(f"  warning: {name} exceeds budget", flush=True)

    manifest_path = out_dir / "prior-clues-manifest.js"
    manifest_body = (
        "exetPriorCluesManifest = "
        + json.dumps({"version": 1, "parts": rel_paths}, indent=2)
        + ";\n"
    )
    manifest_path.write_text(manifest_body, encoding="utf-8")
    print(f"  wrote {rel_prefix}/prior-clues-manifest.js ({len(rel_paths)} parts)", flush=True)
    return rel_paths


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--exet-dir", type=Path, default=EXET)
    ap.add_argument("--out", type=Path, default=DEFAULT_OUT)
    ap.add_argument(
        "--max-per-answer",
        type=int,
        default=0,
        help="Max clues per answer (0 = all unique clues, default)",
    )
    args = ap.parse_args(argv)
    exet_dir = args.exet_dir.resolve()
    sources_dir = exet_dir / "wordlists" / "_sources"

    store: AnswerStore = {}
    meta_map: ClueMeta = {}
    t0 = time.time()

    gh_rows = ingest_georgeho(sources_dir / "georgeho-data.db", store, meta_map)
    xd_rows = ingest_xd(exet_dir / "wordlists" / "xd-clues.zip", store, meta_map)
    gb_rows = ingest_ginsberg(sources_dir / "ginsberg-cluedata", store, meta_map)

    if not store:
        print(
            "No clue data ingested. Run: python tools/fetch-prior-clues-data.py",
            flush=True,
        )
        return 1

    clues, meta, index = build_index(store, meta_map, args.max_per_answer)
    stats = {
        "built": time.strftime("%Y-%m-%d"),
        "answers": len(index),
        "uniqueClues": len(clues),
        "georgehoRows": gh_rows,
        "xdRows": xd_rows,
        "ginsbergRows": gb_rows,
        "maxPerAnswer": args.max_per_answer or None,
    }
    write_parts(exet_dir, clues, meta, index, stats)
    print(
        f"Index: {len(index):,} answers, {len(clues):,} unique clue strings",
        flush=True,
    )
    print(f"Done in {time.time() - t0:.1f}s", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
