#!/usr/bin/env python3
"""Download source data for tools/build-prior-clues-index.py."""

from __future__ import annotations

import ssl
import sys
from pathlib import Path
from urllib.request import Request, urlopen

OUT = Path(__file__).resolve().parent.parent / "wordlists"
SOURCES = OUT / "_sources"
CTX = ssl.create_default_context()
CTX_INSECURE = ssl._create_unverified_context()

GEORGEHO_DB = "https://cryptics.georgeho.org/data.db"
XD_CLUES = "https://xd.saul.pw/xd-clues.zip"


def fetch(url: str, dest: Path, min_bytes: int = 1000) -> bool:
    dest.parent.mkdir(parents=True, exist_ok=True)
    print(f"GET {url}", flush=True)
    req = Request(url, headers={"User-Agent": "exet-prior-clues-fetch/1.0"})
    err = None
    for ctx in (CTX, CTX_INSECURE):
        try:
            with urlopen(req, context=ctx, timeout=600) as r, dest.open("wb") as out:
                while True:
                    chunk = r.read(1024 * 1024)
                    if not chunk:
                        break
                    out.write(chunk)
            break
        except Exception as e:
            err = e
            if dest.is_file():
                dest.unlink()
    if not dest.is_file() or dest.stat().st_size < min_bytes:
        print(f"  FAIL {err or 'tiny/missing file'}", flush=True)
        return False
    print(f"  wrote {dest} ({dest.stat().st_size/1e6:.1f} MB)", flush=True)
    return True


def main() -> int:
    ok = False
    if fetch(GEORGEHO_DB, SOURCES / "georgeho-data.db", min_bytes=1_000_000):
        ok = True
    if fetch(XD_CLUES, OUT / "xd-clues.zip", min_bytes=1_000_000):
        ok = True
    if not ok:
        print("No sources downloaded.", flush=True)
        return 1
    print("Run: python tools/build-prior-clues-index.py", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
