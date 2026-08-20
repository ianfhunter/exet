#!/usr/bin/env python3
"""Build compound-indicators.sql from web sources and local wordlists.

Compound indicators are real words that embed a letter-selection indicator,
e.g. foxtail = tail of fox -> X, egghead = head of egg -> E.

Outputs lists/compound-indicators.sql

Run from exet/:
  python tools/build-compound-indicators.py
"""

from __future__ import annotations

import html as html_lib
import json
import re
import ssl
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parent.parent
OUT_DIR = ROOT / "lists"
OUT_SQL = OUT_DIR / "compound-indicators.sql"
OUT_HTML = OUT_DIR / "compound-indicators.html"
OUT_TXT = OUT_DIR / "compound-indicators.txt"
SOURCES_DIR = ROOT / "lists" / "_sources"
WORDLIST = ROOT / "wordlists" / "crossword_wordlist.txt"
WORDLIST_EXTRA = ROOT / "wordlists" / "spreadthewordlist.txt"

UA = "exet-compound-indicators-builder/1.0"
CTX = ssl.create_default_context()

# (word, letter) pairs cited in setter articles / primers (web-curated).
CURATED: list[tuple[str, str]] = [
    ("egghead", "E"),       # Alberich / Araucaria
    ("redhead", "R"),       # Alberich
    ("masthead", "M"),      # Alberich
    ("gateshead", "G"),     # Alberich (place name; lowercased in DB)
    ("horntail", "N"),      # Cryptipedia word-indicator compound example
    ("foxtail", "X"),
    ("sweetheart", "E"),
    ("oxtail", "X"),
    ("pigtail", "G"),
    ("rattail", "T"),
    ("warhead", "W"),
    ("pinhead", "P"),
    ("flathead", "F"),
    ("deadhead", "D"),
    ("bulkhead", "B"),
    ("figurehead", "F"),
    ("lionheart", "I"),
    ("braveheart", "A"),
    ("horsetail", "E"),
]

INDICATOR_SUFFIXES: list[tuple[str, str]] = [
    ("head", "first"),
    ("tail", "last"),
    ("heart", "middle"),
    ("end", "last"),
    ("top", "first"),
    ("back", "last"),
    ("front", "first"),
    ("start", "first"),
    ("bottom", "last"),
    ("tip", "last"),
    ("middle", "middle"),
    ("centre", "middle"),
    ("center", "middle"),
    ("core", "middle"),
]

# Secondary suffixes often match coincidentally (friend = fri+end).
MIN_FODDER_LEN: dict[str, int] = {
    "end": 4,
    "back": 4,
    "top": 4,
    "front": 4,
    "start": 4,
    "bottom": 4,
    "tip": 4,
    "middle": 4,
    "centre": 4,
    "center": 4,
    "core": 4,
}


@dataclass(frozen=True)
class Row:
    word: str
    letter: str


def fetch(url: str, timeout: int = 60) -> str:
    req = Request(url, headers={"User-Agent": UA})
    with urlopen(req, context=CTX, timeout=timeout) as resp:
        return resp.read().decode("utf-8", "replace")


def load_wordlist(path: Path) -> set[str]:
    words: set[str] = set()
    if not path.is_file():
        return words
    for line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
        w = line.split(";")[0].strip().lower()
        if w and w.isalpha():
            words.add(w)
    return words


def extract_letter(fodder: str, kind: str) -> str | None:
    if not fodder:
        return None
    if kind == "first":
        return fodder[0].upper()
    if kind == "last":
        return fodder[-1].upper()
    n = len(fodder)
    if n % 2 == 0:
        return None
    return fodder[n // 2].upper()


def scrape_web_mentions() -> list[Row]:
    """Parse cached / live pages for quoted compound-indicator examples."""
    found: dict[str, str] = {}

    # Cryptipedia: horntail for "n" (last letter of horn)
    wiki = SOURCES_DIR / "cryptipedia-List_of_letter_selection_indicators.html"
    if not wiki.is_file():
        try:
            text = fetch(
                "https://cryptics.fandom.com/wiki/List_of_letter_selection_indicators"
            )
            wiki.parent.mkdir(parents=True, exist_ok=True)
            wiki.write_text(text, encoding="utf-8")
        except Exception:
            text = ""
    else:
        text = wiki.read_text(encoding="utf-8", errors="ignore")

    for m in re.finditer(
        r'word-indicator compound such as &quot;([a-z]+)&quot; for &quot;([a-z])&quot;',
        text,
        re.I,
    ):
        found[m.group(1).lower()] = m.group(2).upper()
    for m in re.finditer(
        r'word-indicator compound such as "([a-z]+)" for "([a-z])"',
        text,
        re.I,
    ):
        found[m.group(1).lower()] = m.group(2).upper()

    # Alberich: masthead, redhead, Gateshead, egghead
    alberich_url = "https://www.alberich-crosswords.com/articles/single-letter-indicators"
    alberich = SOURCES_DIR / "alberich-single-letter-indicators.html"
    if not alberich.is_file():
        try:
            text = fetch(alberich_url)
            alberich.write_text(text, encoding="utf-8")
        except Exception:
            text = ""
    else:
        text = alberich.read_text(encoding="utf-8", errors="ignore")

    for m in re.finditer(
        r'[“"]([a-z]+head)[”"] for the letters? ([A-Z])', text, re.I
    ):
        found[m.group(1).lower()] = m.group(2).upper()
    for m in re.finditer(
        r"use of things like [“\"]([a-z]+)[”\"] or [“\"]([a-z]+)[”\"] or [“\"]([a-z]+)[”\"]",
        text,
        re.I,
    ):
        for word in m.groups():
            if word and word.endswith("head"):
                found.setdefault(word.lower(), word[0].upper())

    # Crosshare intro: hor(n)tail pattern — fodder horn -> N
    crosshare = SOURCES_DIR / "crosshare-cryptic-intro.html"
    if not crosshare.is_file():
        try:
            text = fetch("https://crosshare.org/articles/cryptic-crossword-intro")
            crosshare.write_text(text, encoding="utf-8")
        except Exception:
            text = ""
    else:
        text = crosshare.read_text(encoding="utf-8", errors="ignore")

    if "hor(n)tail" in text.lower() or "horntail" in text.lower():
        found.setdefault("horntail", "N")

    rows = [Row(w, ch) for w, ch in sorted(found.items())]
    return rows


def generate_from_wordlists(
    words: set[str],
    *,
    extra_words: set[str] | None = None,
    suffixes: list[tuple[str, str]] | None = None,
) -> list[Row]:
    rows: list[Row] = []
    seen: set[str] = set()
    pool = extra_words if extra_words is not None else words
    use_suffixes = suffixes or INDICATOR_SUFFIXES

    for word in sorted(pool):
        best: Row | None = None
        best_suf_len = -1

        for suffix, kind in use_suffixes:
            if not word.endswith(suffix) or len(word) <= len(suffix):
                continue
            fodder = word[: -len(suffix)]
            min_len = MIN_FODDER_LEN.get(suffix, 2)
            if len(fodder) < min_len or len(fodder) > 14:
                continue
            if fodder not in words or suffix not in words:
                continue
            letter = extract_letter(fodder, kind)
            if not letter:
                continue
            if len(suffix) > best_suf_len:
                best = Row(word, letter)
                best_suf_len = len(suffix)

        if best and best.word not in seen:
            seen.add(best.word)
            rows.append(best)

    return rows


def merge_rows(*groups: list[Row]) -> list[Row]:
    merged: dict[str, str] = {}
    for group in groups:
        for row in group:
            merged[row.word] = row.letter
    return [Row(w, merged[w]) for w in sorted(merged)]


def sql_literal(s: str) -> str:
    return "'" + s.replace("'", "''") + "'"


def write_txt(rows: list[Row]) -> None:
    sorted_rows = sorted(rows, key=lambda r: (r.letter, r.word))
    lines = [f"{row.word}\t{row.letter}" for row in sorted_rows]
    OUT_TXT.write_text("\n".join(lines) + "\n", encoding="utf-8")


def render_html(rows: list[Row], meta: dict) -> str:
    count = len(rows)
    sorted_rows = sorted(rows, key=lambda r: (r.letter, r.word))
    by_letter: dict[str, list[Row]] = {}
    for row in sorted_rows:
        by_letter.setdefault(row.letter, []).append(row)

    def row_html(row: Row) -> str:
        w = html_lib.escape(row.word)
        ch = html_lib.escape(row.letter)
        return f'<tr class="row" data-word="{w}"><td class="letter">{ch}</td><td class="word">{w}</td></tr>'

    sections = []
    for letter in sorted(by_letter):
        items = by_letter[letter]
        body = "\n".join(row_html(r) for r in items)
        sections.append(
            f'<section class="cat"><h2>{html_lib.escape(letter)} '
            f'<span class="n">({len(items)})</span></h2>'
            f'<table class="tbl"><thead><tr><th>Letter</th><th>Word</th></tr></thead>'
            f"<tbody>\n{body}\n</tbody></table></section>"
        )

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>Compound indicators ({count}) — Exet offline list</title>
<meta name="viewport" content="width=device-width, initial-scale=1">
<style>
  :root {{
    --bg: #fafafa; --fg: #222; --muted: #666; --accent: #1a5fb4;
    --border: #ddd; --hi: #ffe082;
  }}
  body {{ font: 15px/1.45 system-ui, sans-serif; margin: 0; background: var(--bg); color: var(--fg); }}
  header {{ padding: 12px 16px; border-bottom: 1px solid var(--border); background: #fff; }}
  header h1 {{ margin: 0 0 4px; font-size: 1.2rem; }}
  header p {{ margin: 0; color: var(--muted); font-size: 0.85rem; }}
  #toolbar {{ padding: 10px 16px; background: #fff; border-bottom: 1px solid var(--border);
              position: sticky; top: 0; z-index: 2; display: flex; gap: 8px; flex-wrap: wrap; align-items: center; }}
  #q {{ flex: 1 1 200px; padding: 6px 10px; font: inherit; border: 1px solid var(--border); border-radius: 4px; }}
  #stats {{ color: var(--muted); font-size: 0.85rem; }}
  main {{ padding: 12px 16px 32px; }}
  .cat h2 {{ font-size: 1rem; margin: 20px 0 8px; color: var(--accent); }}
  .cat .n {{ color: var(--muted); font-weight: normal; }}
  .tbl {{ border-collapse: collapse; width: 100%; max-width: 420px; background: #fff; }}
  .tbl th, .tbl td {{ border: 1px solid var(--border); padding: 4px 10px; text-align: left; }}
  .tbl th {{ background: #eef3fb; font-weight: 600; }}
  .tbl .letter {{ font-weight: 700; width: 4em; text-align: center; }}
  tr.hide {{ display: none; }}
  tr.hi td {{ background: var(--hi); }}
</style>
</head>
<body>
<header>
  <h1>Compound indicators</h1>
  <p>{count} entries · built {meta["built"]} · {meta["curated"]} curated, {meta["wordlist"]} from wordlists</p>
  <p>Real words embedding a letter-selection indicator — e.g. <strong>foxtail</strong> → X (tail of fox).</p>
</header>
<div id="toolbar">
  <input type="search" id="q" placeholder="Filter words or letters…" autofocus>
  <span id="stats">{count} shown</span>
</div>
<main>
  {"".join(sections)}
</main>
<script>
(function() {{
  const q = document.getElementById('q');
  const stats = document.getElementById('stats');
  function apply() {{
    const term = q.value.trim().toLowerCase();
    let shown = 0;
    for (const row of document.querySelectorAll('tr.row')) {{
      const text = row.textContent.toLowerCase();
      const ok = !term || text.includes(term);
      row.classList.toggle('hide', !ok);
      row.classList.toggle('hi', ok && term.length > 0);
      if (ok) shown++;
    }}
    stats.textContent = shown + ' shown';
    for (const sec of document.querySelectorAll('.cat')) {{
      sec.style.display = sec.querySelectorAll('tr.row:not(.hide)').length ? '' : 'none';
    }}
  }}
  q.addEventListener('input', apply);
  apply();
}})();
</script>
</body>
</html>
"""


def write_html(rows: list[Row], meta: dict) -> None:
    OUT_HTML.write_text(render_html(rows, meta), encoding="utf-8")


def write_sql(rows: list[Row], *, meta: dict) -> None:
    lines = [
        "-- Compound indicators: words embedding a letter-selection indicator.",
        "-- e.g. foxtail -> X (tail of fox), egghead -> E (head of egg).",
        f"-- Built {meta['built']} by tools/build-compound-indicators.py",
        f"-- {len(rows)} entries "
        f"({meta['curated']} curated, {meta['wordlist']} from wordlists)",
        "",
        "CREATE TABLE IF NOT EXISTS compound_indicators (",
        "  word TEXT NOT NULL PRIMARY KEY,",
        "  letter TEXT NOT NULL CHECK(length(letter) = 1)",
        ");",
        "",
        "DELETE FROM compound_indicators;",
        "",
    ]
    for row in rows:
        lines.append(
            f"INSERT INTO compound_indicators (word, letter) "
            f"VALUES ({sql_literal(row.word)}, {sql_literal(row.letter)});"
        )
    lines.append("")
    OUT_SQL.parent.mkdir(parents=True, exist_ok=True)
    OUT_SQL.write_text("\n".join(lines), encoding="utf-8")
    write_html(rows, meta=meta)
    write_txt(rows)


def main() -> int:
    curated = [Row(w.lower(), ch.upper()) for w, ch in CURATED]
    scraped = scrape_web_mentions()

    words = load_wordlist(WORDLIST)
    spread = load_wordlist(WORDLIST_EXTRA)
    generated = generate_from_wordlists(words)
    # Supplement: head/tail/heart compounds present in spreadthewordlist but not
    # necessarily in the crossword wordlist, with parts validated against it.
    primary_suffixes = [
        (s, k) for s, k in INDICATOR_SUFFIXES if s in {"head", "tail", "heart"}
    ]
    generated_extra = generate_from_wordlists(
        words,
        extra_words=spread,
        suffixes=primary_suffixes,
    )
    generated = merge_rows(generated, generated_extra)

    rows = merge_rows(curated, scraped, generated)
    meta = {
        "built": date.today().isoformat(),
        "curated": len({r.word for r in curated}),
        "wordlist": len(generated),
        "scraped": len(scraped),
        "total": len(rows),
    }
    write_sql(rows, meta=meta)

    manifest = OUT_SQL.with_suffix(".json")
    manifest.write_text(json.dumps(meta, indent=2), encoding="utf-8")

    print(f"Wrote {OUT_SQL} ({len(rows)} entries)", flush=True)
    print(f"Wrote {OUT_HTML}", flush=True)
    print(f"  curated:  {len(curated)}", flush=True)
    print(f"  scraped:  {len(scraped)}", flush=True)
    print(f"  wordlist: {len(generated)}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
