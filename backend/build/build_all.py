#!/usr/bin/env python3
"""Build backend/data/exet.sqlite from exet source datasets."""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

# Allow running as `python backend/build/build_all.py` from the exet repo root.
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.build.lexicon import build_all_lexicons, build_lexicon
from backend.build.prior_clues import build_prior_clues
from backend.build.wordnet import build_wordnet
from backend.config import DB_PATH, WORDLISTS_DIR
from backend.db import connect, set_meta


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--only-lexicon",
        metavar="STEM",
        help="Build one wordlist (stem substring match, e.g. combolist)",
    )
    ap.add_argument("--skip-lexicons", action="store_true")
    ap.add_argument("--skip-prior-clues", action="store_true")
    ap.add_argument("--skip-wordnet", action="store_true")
    ap.add_argument(
        "--max-per-answer",
        type=int,
        default=0,
        help="Cap prior clues per answer (0 = all)",
    )
    ap.add_argument(
        "--db",
        type=Path,
        default=DB_PATH,
        help=f"Output SQLite path (default: {DB_PATH})",
    )
    args = ap.parse_args(argv)

    t0 = time.time()
    conn = connect(args.db)
    summary: dict = {}

    if not args.skip_lexicons:
        if args.only_lexicon:
            sources = [
                p
                for p in WORDLISTS_DIR.iterdir()
                if p.is_file() and args.only_lexicon.lower() in p.stem.lower()
            ]
            if not sources:
                print(f"No wordlist matching {args.only_lexicon!r}", flush=True)
                return 1
            summary["lexicons"] = [build_lexicon(conn, sources[0])]
        else:
            summary["lexicons"] = build_all_lexicons(conn)

    if not args.skip_prior_clues:
        summary["prior_clues"] = build_prior_clues(
            conn, max_per_answer=args.max_per_answer
        )

    if not args.skip_wordnet:
        summary["wordnet"] = build_wordnet(conn)

    set_meta(conn, "build_summary", json.dumps(summary, indent=2))
    conn.commit()
    conn.close()

    size_mb = args.db.stat().st_size / (1024 * 1024)
    print(f"\nWrote {args.db} ({size_mb:.1f} MB) in {time.time() - t0:.1f}s", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
