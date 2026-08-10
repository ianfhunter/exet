#!/usr/bin/env python3
"""Fetch extra wordlist sources into wordlists/_sources/."""

from __future__ import annotations

import re
import ssl
import sys
import tarfile
import zipfile
from pathlib import Path
from urllib.request import Request, urlopen

OUT = Path(__file__).resolve().parent.parent / "wordlists" / "_sources"
CTX = ssl.create_default_context()
# Broda / some mirrors ship expired certs; allow a fallback context.
CTX_INSECURE = ssl._create_unverified_context()


def fetch(url: str, dest: Path, timeout: int = 120, allow_html: bool = False) -> bool:
    dest.parent.mkdir(parents=True, exist_ok=True)
    print(f"GET {url}", flush=True)
    req = Request(url, headers={"User-Agent": "exet-wordlist-builder/1.0"})
    data = None
    err = None
    for ctx in (CTX, CTX_INSECURE):
        try:
            with urlopen(req, context=ctx, timeout=timeout) as r:
                data = r.read()
            break
        except Exception as e:
            err = e
            data = None
    if data is None:
        print(f"  FAIL {err}", flush=True)
        return False
    if len(data) < 50:
        print(f"  FAIL tiny response ({len(data)} bytes)", flush=True)
        return False
    looks_html = data[:200].lstrip().startswith(b"<!DOCTYPE") or b"<html" in data[:300].lower()
    if looks_html and not allow_html:
        print(f"  FAIL got HTML ({len(data)} bytes)", flush=True)
        dest.write_bytes(data)
        return False
    dest.write_bytes(data)
    print(f"  wrote {dest.name} ({len(data)/1e6:.2f} MB)", flush=True)
    return True


def gdrive(file_id: str, dest: Path) -> bool:
    # confirm download endpoint
    url = f"https://drive.google.com/uc?export=download&id={file_id}&confirm=t"
    return fetch(url, dest)


def extract_ukacd(archive: Path) -> Path | None:
    out = OUT / "ukacd.txt"
    if archive.suffix == ".zip":
        with zipfile.ZipFile(archive) as z:
            names = [n for n in z.namelist() if not n.endswith("/")]
            # prefer largest text-ish file
            names.sort(key=lambda n: z.getinfo(n).file_size, reverse=True)
            raw = z.read(names[0])
    elif archive.suffixes[-2:] == [".tar", ".gz"] or archive.suffix == ".tgz":
        with tarfile.open(archive, "r:gz") as t:
            members = [m for m in t.getmembers() if m.isfile()]
            members.sort(key=lambda m: m.size, reverse=True)
            raw = t.extractfile(members[0]).read()  # type: ignore
    else:
        return None
    text = raw.decode("latin-1", errors="replace")
    # UKACD is one word per line; assign default mid score
    lines = []
    for line in text.splitlines():
        w = line.strip()
        if not w or w.startswith("#"):
            continue
        lines.append(f"{w};45")
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"  extracted {out.name} ({len(lines):,} entries)", flush=True)
    return out


def normalize_ecnd(src: Path, dest: Path, score: float = 64.0) -> int:
    text = src.read_text(encoding="utf-8", errors="replace")
    # Drop HTML if any
    if "<html" in text[:500].lower():
        return 0
    n = 0
    with dest.open("w", encoding="utf-8", newline="\n") as f:
        for line in text.splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if ";" in line or "::" in line or "\t" in line:
                f.write(line + "\n")
            else:
                f.write(f"{line};{int(score)}\n")
            n += 1
    return n


def try_broda() -> None:
    # Probe common download locations; Broda site is flaky / expired cert.
    candidates: list[str] = []
    page = OUT / "broda-page.html"
    if fetch(
        "https://peterbroda.me/crosswords/wordlist/", page, allow_html=True
    ):
        html = page.read_text(encoding="utf-8", errors="replace")
        for m in re.finditer(r'href="([^"]+)"', html):
            href = m.group(1)
            low = href.lower()
            if any(low.endswith(ext) for ext in (".txt", ".dict", ".zip", ".csv")):
                if href.startswith("/"):
                    href = "https://peterbroda.me" + href
                elif not href.startswith("http"):
                    href = "https://peterbroda.me/crosswords/wordlist/" + href
                candidates.append(href)
    candidates.extend(
        [
            "https://peterbroda.me/crosswords/wordlist/Wordlist.txt",
            "https://peterbroda.me/crosswords/wordlist/wordlist.txt",
            "https://peterbroda.me/crosswords/wordlist/broda.txt",
            "https://peterbroda.me/crosswords/wordlist/grid_scored.txt",
            "https://peterbroda.me/crosswords/wordlist/gridtext_scored.txt",
            "https://peterbroda.me/wordlist.txt",
        ]
    )
    seen: set[str] = set()
    for url in candidates:
        if url in seen:
            continue
        seen.add(url)
        dest = OUT / "broda.txt"
        if fetch(url, dest):
            sample = dest.read_text(encoding="utf-8", errors="replace")[:400]
            if "<html" in sample.lower():
                continue
            if ";" in sample or sample[:1].isalpha():
                lines = sum(1 for _ in dest.open(encoding="utf-8", errors="replace"))
                print(f"  Broda OK ({lines:,} lines)", flush=True)
                return
    print("  Broda unavailable — skip", flush=True)


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)

    # ECND (Expanded Crossword Name Database)
    gdrive("1qedavK3qfjBRP0RILC8Ehb11p6QRq7AZ", OUT / "ecnd-names.raw")
    gdrive("1chKIYG8uqbyrzvvzHYH4oeN1AldfZP4w", OUT / "ecnd-places.raw")
    for raw, out in (
        (OUT / "ecnd-names.raw", OUT / "ecnd-names.txt"),
        (OUT / "ecnd-places.raw", OUT / "ecnd-places.txt"),
    ):
        if raw.is_file():
            n = normalize_ecnd(raw, out)
            print(f"  ECND {out.name}: {n:,} lines", flush=True)

    # Queer terms scored dict
    fetch(
        "https://raw.githubusercontent.com/maiamcc/xword_dicts/master/dictionaries/queer-scored.dict",
        OUT / "queer-scored.dict",
    )

    # UKACD
    for url, name in (
        ("https://cfajohnson.com/wordfinder/UKACD17.zip", "ukacd17.zip"),
        ("https://www.quinapalus.com/UKACD18.zip", "ukacd18.zip"),
        ("http://www.quinapalus.com/UKACD18.zip", "ukacd18.zip"),
    ):
        dest = OUT / name
        if fetch(url, dest):
            extract_ukacd(dest)
            break

    try_broda()
    print("done", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
