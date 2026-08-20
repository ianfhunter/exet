#!/usr/bin/env python3
"""Build offline Exet lists for clue glue words and spoonerism indicators.

Outputs under lists/:
  clue-glue.json / .html / .txt
  spoonerism-indicators.json / .html / .txt

Run from exet/:
  python tools/build-clue-lists.py
  python tools/build-clue-lists.py glue
  python tools/build-clue-lists.py spoonerism
"""

from __future__ import annotations

import html as html_lib
import json
import re
import sys
from dataclasses import dataclass
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT_DIR = ROOT / "lists"
SOURCES_DIR = OUT_DIR / "_sources"


@dataclass(frozen=True)
class GlueCategory:
    slug: str
    title: str
    blurb: str
    css_class: str


GLUE_CATEGORIES: list[GlueCategory] = [
    GlueCategory(
        slug="definition-linkers",
        title="Definition linkers",
        blurb=(
            "Words and phrases that join the definition to the wordplay without "
            "signaling an operation — e.g. is, means, becomes."
        ),
        css_class="cat-linker",
    ),
    GlueCategory(
        slug="neutral-glue",
        title="Neutral glue",
        blurb=(
            "Articles, prepositions, relatives, conjunctions, and common frames "
            "that usually make a clue read smoothly rather than indicate wordplay."
        ),
        css_class="cat-neutral",
    ),
    GlueCategory(
        slug="ambiguous",
        title="Ambiguous softeners",
        blurb=(
            "Hedge words often used as filler but sometimes weak indicators "
            "(perhaps, maybe, reportedly). Context decides."
        ),
        css_class="cat-ambiguous",
    ),
]

GLUE_ENTRIES: dict[str, list[str]] = {
    "definition-linkers": [
        "is", "are", "was", "were", "be", "being", "been",
        "am", "'s", "'re", "'m",
        "means", "meaning", "meant",
        "becomes", "becoming", "became",
        "gets", "got", "getting",
        "turns", "turned", "turning",
        "goes", "went", "going",
        "comes", "came", "coming",
        "makes", "made", "making",
        "proves", "proved", "proving",
        "represents", "representing", "represented",
        "signifies", "signifying", "signified",
        "denotes", "denoting", "denoted",
        "stands for", "standing for", "stood for",
        "amounts to", "amounting to", "amounted to",
        "counts as", "counting as", "counted as",
        "passes for", "passing for", "passed for",
        "works as", "working as", "worked as",
        "serves as", "serving as", "served as",
        "could be", "can be", "may be", "might be", "must be", "should be",
        "would be", "will be", "shall be",
        "has to be", "had to be", "needs to be", "needed to be",
        "looks like", "looked like", "looking like",
        "seems", "seemed", "seeming", "seems to be", "seemed to be",
        "appears", "appeared", "appearing", "appears to be", "appeared to be",
        "sounds like", "sounded like", "sounding like",
        "that's", "that is", "that was", "that would be",
        "this is", "this was", "this would be",
        "here is", "here's", "here was", "here were",
        "there is", "there's", "there are", "there were",
        "what is", "what's", "what was", "what are", "what were",
        "i.e.", "ie", "viz", "namely", "or rather",
        "in other words", "to wit", "say", "says", "said",
        "defined as", "described as", "known as", "called",
        "termed", "labelled", "labeled", "named", "dubbed",
        "thought of as", "regarded as", "seen as", "taken as",
        "understood as", "considered", "deemed",
    ],
    "neutral-glue": [
        "a", "an", "the", "some", "any", "each", "every", "all", "both", "either",
        "one", "ones", "another", "other", "others",
        "few", "many", "several", "most", "much", "more", "less",
        "no", "not", "without", "with",
        "of", "in", "on", "at", "to", "for", "from", "by", "as", "into", "onto",
        "upon", "over", "under", "above", "below", "between", "among", "amid",
        "through", "throughout", "across", "around", "about", "against",
        "before", "after", "during", "since", "until", "while", "when", "where",
        "and", "or", "but", "nor", "yet", "so", "if", "unless", "though", "although",
        "because", "than", "like", "unlike", "besides", "except", "including",
        "who", "whom", "whose", "which", "that", "what", "whoever", "whatever",
        "this", "that", "these", "those", "such", "same",
        "here", "there", "now", "then", "once", "again", "still", "just", "only",
        "also", "even", "ever", "never", "always", "often", "sometimes",
        "very", "quite", "rather", "too", "so", "how", "why",
        "in the", "at the", "on the", "to the", "for the", "from the", "of the",
        "in a", "at a", "on a", "to a", "for a", "from a", "of a",
        "in an", "at an", "on an", "to an", "for an", "from an", "of an",
        "one who", "one that", "those who", "those that", "people who", "man who",
        "woman who", "thing that", "way to", "time to", "place to",
        "part of", "kind of", "sort of", "type of", "form of", "piece of",
        "bit of", "lot of", "number of", "group of", "set of", "pair of",
        "made of", "made from", "made by", "made in", "made for",
        "found in", "found at", "found on", "found by", "found among",
        "seen in", "seen at", "seen on", "seen by", "seen among",
        "having", "given", "given a", "given the", "given some",
        "being a", "being the", "being some",
        "used in", "used for", "used by", "used as", "used to",
        "known for", "known in", "known at", "known by",
        "associated with", "connected with", "related to", "linked to",
        "dealing with", "concerned with", "involved in", "involved with",
        "responsible for", "typical of", "characteristic of", "common in",
        "popular in", "famous for", "noted for", "renowned for",
        "leading to", "resulting in", "followed by", "preceded by",
        "along with", "together with", "as well as", "as far as",
        "in case of", "in view of", "in light of", "in spite of",
        "on account of", "by means of", "by way of", "in place of",
        "instead of", "as opposed to", "rather than", "more than", "less than",
        "up to", "down to", "out of", "off of", "inside", "outside",
        "near", "next to", "close to", "far from", "away from",
        "back to", "return to", "returning to", "going to", "coming to",
        "able to", "ready to", "likely to", "bound to", "due to",
        "according to", "thanks to", "owing to", "due to",
        "first", "second", "third", "last", "next", "previous",
        "new", "old", "young", "long", "short", "high", "low",
        "good", "bad", "great", "little", "big", "small", "large",
    ],
    "ambiguous": [
        "perhaps", "maybe", "possibly", "probably", "presumably", "apparently",
        "reportedly", "supposedly", "allegedly", "ostensibly", "seemingly",
        "evidently", "clearly", "obviously", "certainly", "definitely",
        "surely", "indeed", "actually", "really", "truly", "literally",
        "figuratively", "virtually", "practically", "essentially", "basically",
        "roughly", "approximately", "about", "around", "somehow", "somewhat",
        "rather", "quite", "fairly", "pretty", "very",
        "oddly", "curiously", "strangely", "interestingly", "remarkably",
        "notably", "significantly", "importantly", "critically",
        "ironically", "fittingly", "aptly", "appropriately",
        "arguably", "debatably", "conceivably", "plausibly",
        "partly", "partially", "somewhat", "more or less",
        "in a way", "in some way", "in a sense", "so to speak",
        "as it were", "as it happens", "as it turns out",
        "it seems", "it appears", "it looks", "it sounds",
        "they say", "we hear", "one hears", "rumour has it", "rumor has it",
        "word has it", "legend has it", "tradition has it",
        "some say", "many say", "critics say", "experts say",
        "supposed to be",         "said to be", "thought to be", "believed to be",
        "known to be", "rumoured to be", "rumored to be", "reported to be",
    ],
}

SPOONERISM_CURATED = [
    "Spooner's", "Spooner", "Rev Spooner's", "Rev. Spooner's",
    "the Rev Spooner's", "the Rev. Spooner's",
    "Reverend Spooner's", "Rev Spooner", "Rev. Spooner",
    "Reverend Spooner", "the Rev Spooner", "the Rev. Spooner",
    "after Spooner", "by Spooner", "from Spooner", "per Spooner",
    "according to Spooner", "courtesy of Spooner",
    "as Spooner would have it", "as Spooner might say", "as Spooner would say",
    "as Spooner had it", "as Spooner said", "as Spooner spoke",
    "as Spooner would speak", "as Spooner might speak",
    "Spooner would say", "Spooner might say", "Spooner had it", "Spooner said",
    "Spooner tells us", "Spooner has it", "Spooner gives us",
    "if Spooner spoke", "if Spooner had spoken", "if Spooner were speaking",
    "on Spooner's lips", "in Spooner's words", "in Spooner's mouth",
    "Spooner-style", "Spooner style", "Spooner-wise", "Spooner fashion",
    "in Spooner's manner", "in Spooner's style", "in the style of Spooner",
    "Spoonerised", "Spoonerized", "Spoonerised form of", "Spoonerized form of",
    "Spoonerised version of", "Spoonerized version of",
    "Spoonerism", "Spoonerism of", "a Spoonerism", "a Spoonerism of",
    "Spoonerian", "Spoonerian slip", "Spoonerian mix-up",
    "Spooner's slip", "Spooner's mistake", "Spooner's error",
    "Spooner's mix-up", "Spooner's confusion", "Spooner's version",
    "Spooner's reading", "Spooner's take", "Spooner's tale",
    "Spooner's twist", "Spooner's twist on", "with Spooner's twist",
    "mixing up Spooner's", "muddled by Spooner", "confused by Spooner",
    "switched by Spooner", "transposed by Spooner", "swapped by Spooner",
    "swapping tops", "starts to change",
    "Spooner's transposition", "Spooner's switch",
    "as misheard by Spooner", "as Spooner would hear it",
    "verbal slip", "slip of the tongue", "slip of Spooner's tongue",
    "Spooner's verbal slip", "Spooner's linguistic slip",
]


def norm_phrase(s: str) -> str:
    s = html_lib.unescape(s.strip())
    s = re.sub(r"\s+", " ", s)
    return s.lower()


def dedupe_phrases(phrases: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for raw in phrases:
        phrase = norm_phrase(raw)
        if not phrase or phrase in seen:
            continue
        seen.add(phrase)
        out.append(phrase)
    return sorted(out, key=lambda x: (len(x.split()), x))


def scrape_cryptipedia_spoonerism() -> list[str]:
    cache = SOURCES_DIR / "cryptipedia-List_of_substitution_and_movement_indicators.html"
    if not cache.is_file():
        return []
    text = cache.read_text(encoding="utf-8")
    m = re.search(
        r'id="Spoonerization".*?<ul>(.*?)</ul>',
        text,
        re.I | re.S,
    )
    if not m:
        return []
    items = re.findall(r"<li>([^<]+)</li>", m.group(1))
    return [norm_phrase(x) for x in items if norm_phrase(x)]


def build_glue_entries() -> list[dict]:
    entries: list[dict] = []
    for cat in GLUE_CATEGORIES:
        for phrase in dedupe_phrases(GLUE_ENTRIES[cat.slug]):
            note = ""
            if cat.slug == "ambiguous":
                note = "May also weakly indicate wordplay in some contexts."
            entries.append(
                {
                    "phrase": phrase,
                    "category": cat.slug,
                    "sources": ["curated"],
                    "notes": [note] if note else [],
                }
            )
    return entries


def build_spoonerism_entries() -> list[dict]:
    store: dict[str, set[str]] = {}

    def add(phrase: str, source: str) -> None:
        key = norm_phrase(phrase)
        if not key or len(key) < 2:
            return
        store.setdefault(key, set()).add(source)

    for phrase in SPOONERISM_CURATED:
        add(phrase, "curated")
    for phrase in scrape_cryptipedia_spoonerism():
        add(phrase, "cryptipedia")

    return [
        {
            "indicator": phrase,
            "sources": sorted(sources),
            "notes": [],
        }
        for phrase, sources in sorted(store.items(), key=lambda kv: kv[0])
    ]


def render_glue_html(meta: dict) -> str:
    count = meta["count"]
    blurb = html_lib.escape(meta["blurb"])
    cat_meta = {c["slug"]: c for c in meta["categories"]}

    sections: list[str] = []
    for cat in meta["categories"]:
        slug = cat["slug"]
        items = [e for e in meta["entries"] if e["category"] == slug]
        chips = []
        for e in items:
            note = html_lib.escape(", ".join(e["notes"]))
            title = "Sources: curated" + (f" · {note}" if note else "")
            chips.append(
                f'<span class="glue {cat_meta[slug]["css_class"]}" '
                f'data-cat="{html_lib.escape(slug)}" title="{title}">'
                f"{html_lib.escape(e['phrase'])}</span>"
            )
        sections.append(
            f'<section class="cat" data-cat="{html_lib.escape(slug)}">'
            f"<h2>{html_lib.escape(cat['title'])} "
            f'<span class="n">({len(items)})</span></h2>'
            f"<p class=\"cat-blurb\">{html_lib.escape(cat['blurb'])}</p>"
            f'<div class="grid">\n' + "\n".join(chips) + "\n</div></section>"
        )

    all_chips = []
    for e in meta["entries"]:
        css = cat_meta[e["category"]]["css_class"]
        note = html_lib.escape(", ".join(e["notes"]))
        title = "Sources: curated" + (f" · {note}" if note else "")
        all_chips.append(
            f'<span class="glue {css}" data-cat="{html_lib.escape(e["category"])}" '
            f'title="{title}">'
            f"{html_lib.escape(e['phrase'])}</span>"
        )

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>Clue glue words ({count}) — Exet offline list</title>
<meta name="viewport" content="width=device-width, initial-scale=1">
<style>
  :root {{
    --bg: #fafafa; --fg: #222; --muted: #666; --accent: #1a5fb4;
    --chip-hi: #ffe082; --border: #ddd;
    --linker-bg: #eef3fb; --linker-border: #d0dcee;
    --neutral-bg: #eef8ef; --neutral-border: #c8dfc9;
    --ambiguous-bg: #fff6e6; --ambiguous-border: #f0d090;
  }}
  body {{ font: 15px/1.45 system-ui, sans-serif; margin: 0; background: var(--bg); color: var(--fg); }}
  header {{ padding: 12px 16px; border-bottom: 1px solid var(--border); background: #fff; }}
  header h1 {{ margin: 0 0 4px; font-size: 1.2rem; }}
  header p {{ margin: 0; color: var(--muted); font-size: 0.85rem; }}
  #toolbar {{ padding: 10px 16px; background: #fff; border-bottom: 1px solid var(--border);
              position: sticky; top: 0; z-index: 2; display: flex; gap: 8px; flex-wrap: wrap; align-items: center; }}
  #q {{ flex: 1 1 200px; padding: 6px 10px; font: inherit; border: 1px solid var(--border); border-radius: 4px; }}
  #cat {{ padding: 6px 10px; font: inherit; border: 1px solid var(--border); border-radius: 4px; }}
  #stats {{ color: var(--muted); font-size: 0.85rem; }}
  main {{ padding: 12px 16px 32px; }}
  .cat h2 {{ font-size: 1rem; margin: 20px 0 6px; color: var(--accent); }}
  .cat .n {{ color: var(--muted); font-weight: normal; }}
  .cat-blurb {{ margin: 0 0 8px; color: var(--muted); font-size: 0.88rem; }}
  .grid {{ display: flex; flex-wrap: wrap; gap: 6px; }}
  .glue {{ border-radius: 4px; padding: 3px 8px; font-size: 0.92rem; cursor: default; }}
  .glue.hide {{ display: none; }}
  .glue.hi {{ background: var(--chip-hi) !important; border-color: #f0c040 !important; }}
  .cat-linker {{ background: var(--linker-bg); border: 1px solid var(--linker-border); }}
  .cat-neutral {{ background: var(--neutral-bg); border: 1px solid var(--neutral-border); }}
  .cat-ambiguous {{ background: var(--ambiguous-bg); border: 1px solid var(--ambiguous-border); }}
  #all h2 {{ font-size: 1rem; margin: 24px 0 8px; }}
  .legend {{ display: flex; gap: 12px; flex-wrap: wrap; margin-top: 8px; font-size: 0.82rem; color: var(--muted); }}
  .legend span {{ display: inline-flex; align-items: center; gap: 4px; }}
  .legend i {{ display: inline-block; width: 12px; height: 12px; border-radius: 3px; border: 1px solid #ccc; }}
</style>
</head>
<body>
<header>
  <h1>Clue glue words</h1>
  <p>{count} entries · built {meta["built"]} · curated for smooth clue surfaces</p>
  <p>{blurb}</p>
  <div class="legend">
    <span><i style="background:var(--linker-bg);border-color:var(--linker-border)"></i> Definition linkers</span>
    <span><i style="background:var(--neutral-bg);border-color:var(--neutral-border)"></i> Neutral glue</span>
    <span><i style="background:var(--ambiguous-bg);border-color:var(--ambiguous-border)"></i> Ambiguous softeners</span>
  </div>
</header>
<div id="toolbar">
  <input type="search" id="q" placeholder="Filter glue words…" autofocus>
  <select id="cat">
    <option value="">All categories</option>
    <option value="definition-linkers">Definition linkers</option>
    <option value="neutral-glue">Neutral glue</option>
    <option value="ambiguous">Ambiguous softeners</option>
  </select>
  <span id="stats">{count} shown</span>
</div>
<main>
  {"".join(sections)}
  <section id="all">
    <h2>All glue words <span class="n">({count})</span></h2>
    <div class="grid" id="grid">
{chr(10).join(all_chips)}
    </div>
  </section>
</main>
<script>
(function() {{
  const q = document.getElementById('q');
  const cat = document.getElementById('cat');
  const stats = document.getElementById('stats');
  function apply() {{
    const term = q.value.trim().toLowerCase();
    const catVal = cat.value;
    let shown = 0;
    for (const sec of document.querySelectorAll('.cat')) {{
      let secShown = 0;
      for (const el of sec.querySelectorAll('.glue')) {{
        const ok = (!term || el.textContent.toLowerCase().includes(term))
          && (!catVal || sec.dataset.cat === catVal);
        el.classList.toggle('hide', !ok);
        el.classList.toggle('hi', ok && term.length > 0);
        if (ok) {{ shown++; secShown++; }}
      }}
      sec.style.display = catVal && sec.dataset.cat !== catVal ? 'none' : '';
    }}
    for (const el of document.querySelectorAll('#all .glue')) {{
      const ok = (!term || el.textContent.toLowerCase().includes(term))
        && (!catVal || el.dataset.cat === catVal);
      el.classList.toggle('hide', !ok);
      el.classList.toggle('hi', ok && term.length > 0);
    }}
    if (catVal) {{
      shown = document.querySelectorAll('.cat:not([style*=\"display: none\"]) .glue:not(.hide)').length;
    }}
    stats.textContent = shown + ' shown';
  }}
  q.addEventListener('input', apply);
  cat.addEventListener('change', apply);
}})();
</script>
</body>
</html>
"""


def render_spoonerism_html(meta: dict) -> str:
    count = meta["count"]
    sources = ", ".join(meta["sources"])
    blurb = html_lib.escape(meta["blurb"])
    chips = []
    for e in meta["entries"]:
        src = html_lib.escape(", ".join(e["sources"]))
        chips.append(
            f'<span class="ind" title="Sources: {src}">'
            f"{html_lib.escape(e['indicator'])}</span>"
        )
    all_chips = "\n".join(chips)
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>Spoonerism indicators ({count}) — Exet offline list</title>
<meta name="viewport" content="width=device-width, initial-scale=1">
<style>
  :root {{
    --bg: #fafafa; --fg: #222; --muted: #666; --accent: #1a5fb4;
    --chip: #f3eefb; --chip-hi: #ffe082; --border: #ddd;
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
  .ind {{ background: var(--chip); border: 1px solid #d8cce8; border-radius: 4px;
          padding: 3px 8px; font-size: 0.92rem; }}
  .ind.hide {{ display: none; }}
  .ind.hi {{ background: var(--chip-hi); border-color: #f0c040; }}
</style>
</head>
<body>
<header>
  <h1>Spoonerism indicators</h1>
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


def write_glue() -> int:
    entries = build_glue_entries()
    meta = {
        "type": "clue-glue",
        "title": "Clue glue words",
        "blurb": (
            "Words and phrases that help cryptic clues read smoothly. "
            "They are not wordplay indicators — though some ambiguous entries "
            "can occasionally double as weak signals."
        ),
        "built": date.today().isoformat(),
        "count": len(entries),
        "sources": ["curated"],
        "categories": [
            {
                "slug": c.slug,
                "title": c.title,
                "blurb": c.blurb,
                "css_class": c.css_class,
            }
            for c in GLUE_CATEGORIES
        ],
        "entries": entries,
    }
    base = "clue-glue"
    (OUT_DIR / f"{base}.json").write_text(
        json.dumps(meta, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    (OUT_DIR / f"{base}.txt").write_text(
        "\n".join(f"[{e['category']}] {e['phrase']}" for e in entries) + "\n",
        encoding="utf-8",
    )
    (OUT_DIR / f"{base}.html").write_text(render_glue_html(meta), encoding="utf-8")
    return len(entries)


def write_spoonerism() -> int:
    entries = build_spoonerism_entries()
    meta = {
        "type": "spoonerism",
        "title": "Spoonerism indicators",
        "blurb": (
            "Signal that adjacent word sounds should be swapped (Spoonerised) "
            "to form the answer — e.g. Spooner's, after Spooner, swapping tops."
        ),
        "built": date.today().isoformat(),
        "count": len(entries),
        "sources": sorted({s for e in entries for s in e["sources"]}),
        "entries": entries,
    }
    base = "spoonerism-indicators"
    (OUT_DIR / f"{base}.json").write_text(
        json.dumps(meta, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    (OUT_DIR / f"{base}.txt").write_text(
        "\n".join(e["indicator"] for e in entries) + "\n", encoding="utf-8"
    )
    (OUT_DIR / f"{base}.html").write_text(render_spoonerism_html(meta), encoding="utf-8")
    return len(entries)


def main(argv: list[str]) -> None:
    targets = argv[1:] or ["glue", "spoonerism"]
    if "glue" in targets:
        n = write_glue()
        print(f"  clue-glue: {n} entries -> lists/clue-glue.html", flush=True)
    if "spoonerism" in targets:
        n = write_spoonerism()
        print(f"  spoonerism: {n} indicators -> lists/spoonerism-indicators.html", flush=True)


if __name__ == "__main__":
    main(sys.argv)
