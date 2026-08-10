#!/usr/bin/env python3
"""Fetch curated phrase/name packs recommended for Million Union."""

from __future__ import annotations

import json
import ssl
from pathlib import Path
from urllib.request import Request, urlopen

OUT = Path(__file__).resolve().parent.parent / "wordlists" / "_sources"
CTX = ssl.create_default_context()


def get(url: str, timeout: int = 180) -> bytes:
    req = Request(url, headers={"User-Agent": "exet-wordlist-builder/1.0"})
    with urlopen(req, context=CTX, timeout=timeout) as r:
        return r.read()


def write_bytes(name: str, data: bytes) -> Path:
    OUT.mkdir(parents=True, exist_ok=True)
    path = OUT / name
    path.write_bytes(data)
    nlines = data.count(b"\n")
    print(f"  wrote {name} ({len(data)/1e6:.2f} MB, {nlines} lines)")
    return path


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)

    # --- nzfeng curated crossword dataset ---
    print("nzfeng …", flush=True)
    api = json.loads(
        get("https://api.github.com/repos/nzfeng/crossword-dataset/contents/raw")
    )
    for x in api:
        if x.get("type") != "file":
            continue
        name = x["name"]
        if not name.endswith((".txt", ".dict", ".csv")):
            continue
        data = get(x["download_url"])
        write_bytes(f"nzfeng-{name}", data)

    # --- Solve The Crossword free scored list ---
    print("STC …", flush=True)
    for url in (
        "https://solvethecrossword.com/stc-wordlist.dict",
        "https://solvethecrossword.com/constructors/stc-wordlist.dict",
        "https://solvethecrossword.com/downloads/stc-wordlist.dict",
    ):
        try:
            data = get(url)
        except Exception as e:
            print(f"  fail {url}: {e}", flush=True)
            continue
        if data.lstrip()[:20].lower().startswith(b"<!doctype") or b"<html" in data[:200].lower():
            print(f"  html from {url}", flush=True)
            continue
        write_bytes("stc-wordlist.dict", data)
        break

    # --- Geo / phrase name packs (skip huge unfiltered Names.txt) ---
    print("BirdsAreFlyingCameras geo packs …", flush=True)
    base = "https://raw.githubusercontent.com/BirdsAreFlyingCameras/WordLists/main/"
    for name, score_default in (
        ("CityNames.txt", 55),
        ("CountryNames.txt", 60),
        ("States-Provinces.txt", 55),
        ("JobTitles.txt", 45),
        ("CommonWebsitePhrases.txt", 35),
    ):
        try:
            data = get(base + name)
        except Exception as e:
            print(f"  fail {name}: {e}", flush=True)
            continue
        # Convert plain lines to word;score
        out_lines = []
        for line in data.decode("utf-8", "replace").splitlines():
            w = line.strip()
            if not w or w.startswith("#"):
                continue
            if ";" in w or "::" in w or "\t" in w:
                out_lines.append(w)
            else:
                out_lines.append(f"{w};{score_default}")
        path = OUT / f"geo-{Path(name).stem.lower()}.txt"
        path.write_text("\n".join(out_lines) + "\n", encoding="utf-8")
        print(f"  wrote {path.name} ({len(out_lines):,} entries)", flush=True)

    # --- maiamcc specialty dicts ---
    print("maiamcc xword_dicts …", flush=True)
    try:
        api = json.loads(
            get("https://api.github.com/repos/maiamcc/xword_dicts/contents/dictionaries")
        )
        for x in api:
            if x.get("type") != "file" or not x["name"].endswith(".dict"):
                continue
            data = get(x["download_url"])
            write_bytes(f"maiamcc-{x['name']}", data)
    except Exception as e:
        print(f"  fail: {e}", flush=True)

    print("done", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
