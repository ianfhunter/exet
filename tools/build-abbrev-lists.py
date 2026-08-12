#!/usr/bin/env python3
"""Build offline Exet lists for cryptic abbreviations and abbreviation indicators.

Outputs under lists/:
  abbreviation-indicators.json / .html / .txt
  abbreviations.json / .html / .txt
  abbreviations-lookup.js

Run from exet/:
  python tools/build-abbrev-lists.py
  python tools/build-abbrev-lists.py indicators
  python tools/build-abbrev-lists.py abbreviations
"""

from __future__ import annotations

import html as html_lib
import json
import re
import ssl
import sys
from datetime import date
from pathlib import Path
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parent.parent
OUT_DIR = ROOT / "lists"
SOURCES_DIR = OUT_DIR / "_sources"

UA = "exet-abbrev-lists-builder/1.0"
CTX = ssl.create_default_context()
CTX_INSECURE = ssl._create_unverified_context()

INDICATOR_SKIP = frozenset(
    "abcdefghijklmnopqrstuvwxyz separator menu scroll".split()
)

INDICATOR_JUNK = re.compile(
    r"web-app|breadcrumb|viewport|mobile-web|currentcolor|"
    r"^(article|button|canonical|itemlist|listitem|website|yes|content|"
    r"summary|description|robots|theme-color|format-detection)$",
    re.I,
)

ABBREV_INDICATOR_CURATED = [
    "abbr", "abbrev", "abbreviated", "abbreviation",
    "brief", "briefly", "in brief",
    "for short", "in short", "short form", "shortened", "shortened form",
    "shortly", "in shortened form", "in abbreviated form",
    "informal", "informally", "informal version",
    "familiar", "familiarly",
    "casual", "casually",
    "colloquial", "colloquially",
    "slang", "in slang", "slang term", "slangily",
    "contracted", "clipped", "truncated", "compact", "compacted",
    "initialism", "acronym", "as an acronym",
    "summarized", "in summary", "condensed",
    "in shorthand", "shorthand",
    "telegraphic", "telegraphically",
    "inits", "initials",
    "symbolically", "as a symbol",
    "in code", "coded",
    "cue shortened",
    "in contracted form",
    "in compact form",
    "in telegraphic form",
    "popularly", "popular name",
    "nickname", "nicknamed",
    "so to abbreviate",
    "to abbreviate",
    "in abbreviated style",
    "in short hand",
    "inits.", "abbr.",
]


def fetch(url: str, timeout: int = 120) -> str:
    req = Request(url, headers={"User-Agent": UA})
    for ctx in (CTX, CTX_INSECURE):
        try:
            with urlopen(req, context=ctx, timeout=timeout) as resp:
                return resp.read().decode("utf-8", "replace")
        except Exception:
            continue
    raise RuntimeError(f"fetch failed: {url}")


def read_or_fetch(cache_name: str, url: str) -> str:
    cache = SOURCES_DIR / cache_name
    if cache.is_file():
        return cache.read_text(encoding="utf-8")
    SOURCES_DIR.mkdir(parents=True, exist_ok=True)
    text = fetch(url)
    cache.write_text(text, encoding="utf-8")
    return text


def norm_space(s: str) -> str:
    return re.sub(r"\s+", " ", html_lib.unescape(s.strip()))


def norm_headword(s: str) -> str:
    return norm_space(s).lower()


def expansion_sort_key(text: str) -> str:
    text = norm_space(text).lower()
    text = re.sub(r"^[^a-z0-9]+", "", text)
    return text


def split_expansions(text: str) -> list[str]:
    text = norm_space(text)
    if not text:
        return []
    text = re.sub(r"\s*\([^)]*\)", "", text)
    parts = re.split(r"\s*,\s*|\s+or\s+|\s*/\s*|\s*;\s*", text, flags=re.I)
    out: list[str] = []
    for part in parts:
        part = part.strip(" .")
        if part:
            out.append(part)
    return out


def add_indicator(store: dict[str, dict], phrase: str, source: str) -> bool:
    phrase = norm_space(phrase).lower()
    if not phrase or len(phrase) > 80:
        return False
    if phrase in INDICATOR_SKIP:
        return False
    if INDICATOR_JUNK.search(phrase):
        return False
    if len(phrase.split()) > 6:
        return False
    if re.search(r"[$#@0-9]", phrase):
        return False
    before = phrase not in store
    entry = store.setdefault(
        phrase,
        {"indicator": phrase, "sources": set(), "categories": set(), "notes": set()},
    )
    entry["sources"].add(source)
    return before


def add_abbrev(
    store: dict[str, dict],
    headword: str,
    expansion: str,
    source: str,
    *,
    note: str | None = None,
) -> bool:
    headword = norm_headword(headword)
    expansion = norm_space(expansion)
    if not headword or not expansion or len(headword) > 80 or len(expansion) > 120:
        return False
    if headword in {"word", "indicator", "clue word", "abbreviation"}:
        return False

    adv = False
    unsound = False
    if expansion.endswith("*"):
        adv = True
        expansion = expansion[:-1].strip()
    if expansion.endswith("+"):
        unsound = True
        expansion = expansion[:-1].strip()
    if not expansion:
        return False

    before = headword not in store
    entry = store.setdefault(
        headword,
        {"headword": headword, "expansions": set(), "sources": set(), "notes": set()},
    )
    entry["expansions"].add(expansion)
    entry["sources"].add(source)
    if note:
        entry["notes"].add(note)
    if adv:
        entry["notes"].add("advanced")
    if unsound:
        entry["notes"].add("disputed")
    return before


def add_abbrev_text(
    store: dict[str, dict], headword: str, expansion_text: str, source: str
) -> int:
    count = 0
    for exp in split_expansions(expansion_text):
        if add_abbrev(store, headword, exp, source):
            count += 1
        elif norm_headword(headword) in store:
            before = len(store[norm_headword(headword)]["expansions"])
            add_abbrev(store, headword, exp, source)
            if len(store[norm_headword(headword)]["expansions"]) > before:
                count += 1
    return count


def load_clue_clinic_abbrev_html(page_id: int) -> str:
    cache_name = f"clueclinic-{page_id}-abbrev.html"
    cache = SOURCES_DIR / cache_name
    if cache.is_file():
        return cache.read_text(encoding="utf-8")
    url = f"https://clueclinic.com/index.php/wp-json/wp/v2/pages/{page_id}"
    html = json.loads(fetch(url))["content"]["rendered"]
    SOURCES_DIR.mkdir(parents=True, exist_ok=True)
    cache.write_text(html, encoding="utf-8")
    return html


def scrape_clue_clinic_abbrev(store: dict[str, dict], page_id: int) -> int:
    html = load_clue_clinic_abbrev_html(page_id)
    count = 0
    for row in re.findall(r'<tr class="row-[^"]*">(.*?)</tr>', html, re.S):
        cells = re.findall(r'<td class="column-(\d+)">([^<]*)</td>', row)
        if not cells:
            continue
        by_col = {int(col): norm_space(val) for col, val in cells}
        word = by_col.get(1, "")
        if not word or word.lower() in {"word", "clue word", "indicator", "text in clue"}:
            continue
        expansions = [by_col[i] for i in (2, 3, 4) if by_col.get(i)]
        if not expansions:
            continue
        for exp in expansions:
            count += add_abbrev_text(store, word, exp, "clue-clinic")
    return count


def scrape_mhl_yaml(store: dict[str, dict]) -> int:
    text = read_or_fetch(
        "mhl-indicators.yml",
        "https://raw.githubusercontent.com/mhl/"
        "cryptic-crossword-indicators-and-abbreviations/master/indicators.yml",
    )
    count = 0
    for line in text.splitlines():
        m = re.match(r"^\s*([a-z0-9][a-z0-9 .'-]*):\s*(.+)$", line, re.I)
        if m:
            count += add_abbrev_text(store, m.group(1), m.group(2), "mhl-yaml")
    return count


def scrape_longair(store: dict[str, dict]) -> int:
    text = read_or_fetch(
        "longair-indicators.html",
        "https://longair.net/mark/random/indicators/",
    )
    count = 0
    for line in text.splitlines():
        m = re.match(r"^\s{3}([a-z0-9][a-z0-9 .'-]*):\s*(.+)$", line, re.I)
        if m:
            count += add_abbrev_text(store, m.group(1), m.group(2), "longair")
    return count


def scrape_wikipedia_abbrev(store: dict[str, dict]) -> int:
    text = read_or_fetch(
        "wikipedia-crossword-abbreviations.html",
        "https://en.wikipedia.org/wiki/Crossword_abbreviations",
    )
    count = 0
    plain = re.sub(r"<script[^>]*>.*?</script>", " ", text, flags=re.I | re.S)
    plain = re.sub(r"<style[^>]*>.*?</style>", " ", plain, flags=re.I | re.S)
    for cell in re.findall(r"<li[^>]*>(.*?)</li>", plain, re.S):
        line = re.sub(r"<[^>]+>", " ", cell)
        line = norm_space(line)
        m = re.match(r"^(.+?)\s+[–—\-]\s+(.+)$", line)
        if m:
            count += add_abbrev_text(store, m.group(1), m.group(2), "wikipedia")
    return count


def scrape_cryptipedia_abbrev(store: dict[str, dict]) -> int:
    text = read_or_fetch(
        "cryptipedia-List_of_abbreviations.html",
        "https://cryptics.fandom.com/wiki/List_of_abbreviations",
    )
    body = text
    m = re.search(r'mw-parser-output"[^>]*>(.*)', text, re.S)
    if m:
        body = m.group(1)
        end = re.search(r'<div class="printfooter"', body)
        if end:
            body = body[: end.start()]

    count = 0
    for cell in re.findall(r"<li[^>]*>(.*?)</li>", body, re.S):
        line = norm_space(re.sub(r"<[^>]+>", " ", cell))
        if not line or line.startswith("#"):
            continue
        m = re.match(r"^(.+?)\s+[–—\-]\s+(.+)$", line)
        if m:
            count += add_abbrev_text(store, m.group(1), m.group(2), "cryptipedia")
    return count


def scrape_solve_the_crossword_indicators(store: dict[str, dict]) -> int:
    text = read_or_fetch(
        "solvethecrossword-clue-signals.html",
        "https://solvethecrossword.com/guide/crossword-clue-signals",
    )
    count = 0
    low = text.lower()
    start = low.find("abbreviation signal")
    if start < 0:
        start = low.find("abbreviation")
    section = text[start : start + 8000] if start >= 0 else text
    for m in re.finditer(r'"([a-z][a-z .\'-]{2,40})"', section, re.I):
        if add_indicator(store, m.group(1), "solve-the-crossword"):
            count += 1
    for phrase in (
        "briefly",
        "for short",
        "informally",
        "abbr.",
        "in short",
        "shortly",
        "in brief",
        "familiarly",
        "colloquially",
        "abbreviated",
    ):
        if add_indicator(store, phrase, "solve-the-crossword"):
            count += 1
    return count


def build_abbreviation_indicators() -> dict[str, dict]:
    store: dict[str, dict] = {}
    steps = [
        ("curated", lambda s: sum(
            add_indicator(s, x, "curated") for x in ABBREV_INDICATOR_CURATED
        )),
        ("solve-the-crossword", scrape_solve_the_crossword_indicators),
    ]
    print("\n=== Abbreviation indicators ===", flush=True)
    for name, fn in steps:
        try:
            before = len(store)
            raw = fn(store)
            print(
                f"  {name}: +{raw} raw / {len(store) - before} new ({len(store)} unique)",
                flush=True,
            )
        except Exception as exc:
            print(f"  {name}: FAIL — {exc}", flush=True)
    return store


def build_abbreviations() -> dict[str, dict]:
    store: dict[str, dict] = {}
    steps = [
        ("clue-clinic-all", lambda s: scrape_clue_clinic_abbrev(s, 365)),
        ("clue-clinic-standard", lambda s: scrape_clue_clinic_abbrev(s, 340)),
        ("mhl-yaml", scrape_mhl_yaml),
        ("longair", scrape_longair),
        ("wikipedia", scrape_wikipedia_abbrev),
        ("cryptipedia", scrape_cryptipedia_abbrev),
    ]
    print("\n=== Abbreviations (clue word -> expansion) ===", flush=True)
    for name, fn in steps:
        try:
            before = len(store)
            raw = fn(store)
            print(
                f"  {name}: +{raw} raw / {len(store) - before} new "
                f"({len(store)} unique headwords)",
                flush=True,
            )
        except Exception as exc:
            print(f"  {name}: FAIL — {exc}", flush=True)
    return store


def write_indicator_outputs(store: dict[str, dict]) -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    base = "abbreviation-indicators"
    ordered = sorted(store.values(), key=lambda e: e["indicator"])
    serializable = [
        {
            "indicator": e["indicator"],
            "sources": sorted(e["sources"]),
            "notes": sorted(e["notes"]),
        }
        for e in ordered
    ]
    meta = {
        "type": "abbreviation-indicators",
        "title": "Abbreviation indicators",
        "blurb": (
            "Signal words that the answer (or part of it) should be abbreviated, "
            "shortened, or informal — e.g. briefly, for short, informally."
        ),
        "built": date.today().isoformat(),
        "count": len(serializable),
        "sources": sorted({s for e in serializable for s in e["sources"]}),
        "entries": serializable,
    }
    (OUT_DIR / f"{base}.json").write_text(
        json.dumps(meta, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    (OUT_DIR / f"{base}.txt").write_text(
        "\n".join(e["indicator"] for e in serializable) + "\n", encoding="utf-8"
    )
    (OUT_DIR / f"{base}.html").write_text(render_indicator_html(meta), encoding="utf-8")
    return len(serializable)


def write_abbrev_outputs(store: dict[str, dict]) -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    base = "abbreviations"
    ordered = sorted(
        store.values(),
        key=lambda e: (
            min(expansion_sort_key(x) for x in e["expansions"]),
            e["headword"],
        ),
    )
    serializable = [
        {
            "headword": e["headword"],
            "expansions": sorted(e["expansions"]),
            "sources": sorted(e["sources"]),
            "notes": sorted(e["notes"]),
        }
        for e in ordered
    ]
    meta = {
        "type": "abbreviations",
        "title": "Cryptic abbreviations",
        "blurb": (
            "Clue words and phrases that commonly abbreviate to letters or short "
            "forms in cryptic crosswords (bits-and-pieces)."
        ),
        "built": date.today().isoformat(),
        "count": len(serializable),
        "sources": sorted({s for e in serializable for s in e["sources"]}),
        "entries": serializable,
    }
    (OUT_DIR / f"{base}.json").write_text(
        json.dumps(meta, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    (OUT_DIR / f"{base}.txt").write_text(
        "\n".join(
            f"{e['headword']} -> {', '.join(e['expansions'])}"
            for e in serializable
        )
        + "\n",
        encoding="utf-8",
    )
    (OUT_DIR / f"{base}.html").write_text(render_abbrev_html(meta), encoding="utf-8")
    lookup = {e["headword"]: e["expansions"] for e in serializable}
    (OUT_DIR / "abbreviations-lookup.js").write_text(
        "var exetAbbrevLookup="
        + json.dumps(lookup, ensure_ascii=False, separators=(",", ":"))
        + ";\n",
        encoding="utf-8",
    )
    return len(serializable)


def render_indicator_html(meta: dict) -> str:
    count = meta["count"]
    sources = ", ".join(meta["sources"])
    chips = []
    for e in meta["entries"]:
        src = html_lib.escape(", ".join(e["sources"]))
        chips.append(
            f'<span class="ind" title="Sources: {src}">'
            f"{html_lib.escape(e['indicator'])}</span>"
        )
    all_chips = "\n".join(chips)
    blurb = html_lib.escape(meta["blurb"])
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>Abbreviation indicators ({count}) — Exet offline list</title>
<meta name="viewport" content="width=device-width, initial-scale=1">
<style>
  :root {{
    --bg: #fafafa; --fg: #222; --muted: #666; --accent: #1a5fb4;
    --chip: #eef3fb; --chip-hi: #ffe082; --border: #ddd;
  }}
  body {{ font: 15px/1.45 system-ui, sans-serif; margin: 0; background: var(--bg); color: var(--fg); }}
  header {{ padding: 12px 16px; border-bottom: 1px solid var(--border); background: #fff; }}
  header h1 {{ margin: 0 0 4px; font-size: 1.2rem; }}
  header p {{ margin: 0; color: var(--muted); font-size: 0.85rem; }}
  #toolbar {{ padding: 10px 16px; background: #fff; border-bottom: 1px solid var(--border);
              position: sticky; top: 0; z-index: 2; display: flex; gap: 8px; align-items: center; }}
  #q {{ flex: 1 1 200px; padding: 6px 10px; font: inherit; border: 1px solid var(--border); border-radius: 4px; }}
  #stats {{ color: var(--muted); font-size: 0.85rem; }}
  main {{ padding: 12px 16px 32px; }}
  .grid {{ display: flex; flex-wrap: wrap; gap: 6px; }}
  .ind {{ background: var(--chip); border: 1px solid #d0dcee; border-radius: 4px;
          padding: 3px 8px; font-size: 0.92rem; }}
  .ind.hide {{ display: none; }}
  .ind.hi {{ background: var(--chip-hi); border-color: #f0c040; }}
</style>
</head>
<body>
<header>
  <h1>Abbreviation indicators</h1>
  <p>{count} entries · built {meta["built"]} · merged from: {html_lib.escape(sources)}</p>
  <p>{blurb}</p>
</header>
<div id="toolbar">
  <input type="search" id="q" placeholder="Filter indicators…" autofocus>
  <span id="stats">{count} shown</span>
</div>
<main>
  <div class="grid" id="grid">
{all_chips}
  </div>
</main>
<script>
(function() {{
  const q = document.getElementById('q');
  const stats = document.getElementById('stats');
  q.addEventListener('input', () => {{
    const term = q.value.trim().toLowerCase();
    let shown = 0;
    for (const el of document.querySelectorAll('.ind')) {{
      const ok = !term || el.textContent.toLowerCase().includes(term);
      el.classList.toggle('hide', !ok);
      el.classList.toggle('hi', ok && term.length > 0);
      if (ok) shown++;
    }}
    stats.textContent = shown + ' shown';
  }});
}})();
</script>
</body>
</html>
"""


def render_abbrev_html(meta: dict) -> str:
    count = meta["count"]
    sources = ", ".join(meta["sources"])
    rows = []
    for e in meta["entries"]:
        src = html_lib.escape(", ".join(e["sources"]))
        hw = html_lib.escape(e["headword"])
        exps = html_lib.escape(", ".join(e["expansions"]))
        note = html_lib.escape(", ".join(e["notes"]))
        title = f"Sources: {src}" + (f" · Notes: {note}" if note else "")
        rows.append(
            f'<tr class="row" title="{title}">'
            f'<td class="hw">{hw}</td><td class="exp">{exps}</td></tr>'
        )
    body_rows = "\n".join(rows)
    blurb = html_lib.escape(meta["blurb"])
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>Cryptic abbreviations ({count}) — Exet offline list</title>
<meta name="viewport" content="width=device-width, initial-scale=1">
<style>
  :root {{
    --bg: #fafafa; --fg: #222; --muted: #666; --accent: #1a5fb4;
    --hi: #ffe082; --border: #ddd;
  }}
  body {{ font: 15px/1.45 system-ui, sans-serif; margin: 0; background: var(--bg); color: var(--fg); }}
  header {{ padding: 12px 16px; border-bottom: 1px solid var(--border); background: #fff; }}
  header h1 {{ margin: 0 0 4px; font-size: 1.2rem; }}
  header p {{ margin: 0; color: var(--muted); font-size: 0.85rem; }}
  #toolbar {{ padding: 10px 16px; background: #fff; border-bottom: 1px solid var(--border);
              position: sticky; top: 0; z-index: 2; display: flex; gap: 8px; align-items: center; }}
  #q {{ flex: 1 1 240px; padding: 6px 10px; font: inherit; border: 1px solid var(--border); border-radius: 4px; }}
  #stats {{ color: var(--muted); font-size: 0.85rem; }}
  main {{ padding: 12px 16px 32px; }}
  table {{ width: 100%; border-collapse: collapse; background: #fff; }}
  th, td {{ text-align: left; padding: 6px 10px; border-bottom: 1px solid var(--border); vertical-align: top; }}
  th {{ background: #f5f7fb; color: var(--accent); position: sticky; top: 52px; }}
  tr.hide {{ display: none; }}
  tr.hi {{ background: var(--hi); }}
  .hw {{ font-weight: 600; width: 34%; }}
  .exp {{ color: #333; }}
</style>
</head>
<body>
<header>
  <h1>Cryptic abbreviations</h1>
  <p>{count} headwords · built {meta["built"]} · merged from: {html_lib.escape(sources)}</p>
  <p>{blurb}</p>
</header>
<div id="toolbar">
  <input type="search" id="q" placeholder="Filter headword or expansion…" autofocus>
  <span id="stats">{count} shown</span>
</div>
<main>
  <table>
    <thead><tr><th>Clue word</th><th>Expansions</th></tr></thead>
    <tbody id="rows">
{body_rows}
    </tbody>
  </table>
</main>
<script>
(function() {{
  const q = document.getElementById('q');
  const stats = document.getElementById('stats');
  q.addEventListener('input', () => {{
    const term = q.value.trim().toLowerCase();
    let shown = 0;
    for (const row of document.querySelectorAll('#rows tr')) {{
      const text = row.textContent.toLowerCase();
      const ok = !term || text.includes(term);
      row.classList.toggle('hide', !ok);
      row.classList.toggle('hi', ok && term.length > 0);
      if (ok) shown++;
    }}
    stats.textContent = shown + ' shown';
  }});
}})();
</script>
</body>
</html>
"""


def main(argv: list[str]) -> int:
    wanted = {a.lower() for a in argv[1:]}
    do_indicators = not wanted or "indicators" in wanted or "abbreviation-indicators" in wanted
    do_abbrev = not wanted or "abbreviations" in wanted or "abbrev" in wanted

    summary: list[tuple[str, int]] = []
    if do_indicators:
        n = write_indicator_outputs(build_abbreviation_indicators())
        summary.append(("abbreviation-indicators", n))
    if do_abbrev:
        n = write_abbrev_outputs(build_abbreviations())
        summary.append(("abbreviations", n))

    print("\n--- Summary ---", flush=True)
    for slug, n in summary:
        print(f"  {slug}: {n} entries -> lists/{slug}.html", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
