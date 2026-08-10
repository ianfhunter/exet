#!/usr/bin/env python3
"""Export Nediger / Lufz lexicon JS into word;score text for million-union."""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

EXET = Path(__file__).resolve().parent.parent


def parse_js_objects(text: str) -> list[dict]:
    objs: list[dict] = []
    # Backtick form used by Nediger / Lufz
    for m in re.finditer(r"JSON\.parse\(`([\s\S]*?)`\)", text):
        objs.append(json.loads(m.group(1)))
    # Quoted JSON.parse("...") form used by importer output
    for m in re.finditer(r'JSON\.parse\("((?:\\.|[^"\\])*)"\)', text):
        raw = json.loads(f'"{m.group(1)}"')
        objs.append(json.loads(raw))
    return objs


def load_lexicon(paths: list[Path]) -> tuple[list[str], list[float]]:
    lexicon: list[str] | None = None
    scores: list[float] | None = None
    for path in paths:
        text = path.read_text(encoding="utf-8", errors="replace")
        for obj in parse_js_objects(text):
            if "lexicon" in obj:
                lexicon = obj["lexicon"]
            if "scores" in obj:
                scores = [float(x) for x in obj["scores"]]
    if lexicon is None:
        raise SystemExit(f"No lexicon found in {[str(p) for p in paths]}")
    n = len(lexicon)
    if scores is None:
        # Lufz-style popularity: earlier = hotter
        scores = [0.0] + [100.0 * (1.0 - (i / (n - 1))) for i in range(1, n)]
    if len(scores) != n:
        raise SystemExit(f"scores length {len(scores)} != lexicon {n}")
    return lexicon, scores


def write_txt(lexicon: list[str], scores: list[float], out: Path) -> int:
    out.parent.mkdir(parents=True, exist_ok=True)
    count = 0
    with out.open("w", encoding="utf-8", newline="\n") as f:
        for w, s in zip(lexicon[1:], scores[1:]):
            if not w:
                continue
            if float(s) == int(float(s)):
                f.write(f"{w};{int(float(s))}\n")
            else:
                f.write(f"{w};{float(s):.5f}\n")
            count += 1
    return count


def main() -> int:
    out_dir = EXET / "wordlists" / "_sources"
    jobs = [
        (
            [EXET / "nediger-list-part-1.js", EXET / "nediger-list-part-2.js"],
            out_dir / "nediger.txt",
        ),
        ([EXET / "lufz-en-lexicon.js"], out_dir / "lufz-en.txt"),
    ]
    for paths, out in jobs:
        missing = [p for p in paths if not p.is_file()]
        if missing:
            print(f"skip {out.name}: missing {missing}", file=sys.stderr)
            continue
        lex, scores = load_lexicon(paths)
        n = write_txt(lex, scores, out)
        print(f"wrote {out} ({n:,} entries)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
