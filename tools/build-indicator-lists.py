#!/usr/bin/env python3
"""Scrape cryptic crossword indicators and build offline Exet lists.

Outputs one set per indicator type under lists/:
  {slug}-indicators.json
  {slug}-indicators.html
  {slug}-indicators.txt

Run from exet/:
  python tools/build-indicator-lists.py          # all types
  python tools/build-indicator-lists.py hidden # one type
"""

from __future__ import annotations

import html as html_lib
import json
import re
import ssl
import sys
import time
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from urllib.parse import quote
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parent.parent
OUT_DIR = ROOT / "lists"
SOURCES_DIR = OUT_DIR / "_sources"

UA = "exet-indicator-lists-builder/1.0"
CTX = ssl.create_default_context()
CTX_INSECURE = ssl._create_unverified_context()

SKIP_WORDS = frozenset(
    "abcdefghijklmnopqrstuvwxyz separator menu scroll".split()
)

WORDSUP_PAGES: dict[str, str] = {
    "anagram": "anagram-indicators.php",
    "hidden": "hidden-word-indicators.php",
    "homophone": "homophone-indicators.php",
    "reversal": "reversal-indicators.php",
    "deletion": "deleted-letter-indicators.php",
    "containment": "containment-indicators.php",
    "letter-selection": "selected-letter-indicators.php",
    "alternation": "sequence-indicators.php",
}

CRYPTIPEDIA_PAGES: dict[str, list[str]] = {
    "anagram": ["List_of_anagram_indicators"],
    "hidden": ["List_of_hidden_word_indicators"],
    "reversal": ["List_of_reversal_indicators"],
    "homophone": ["List_of_homophone_indicators"],
    "deletion": [
        "List_of_general_deletion_indicators",
        "List_of_letter_deletion_indicators",
    ],
    "containment": [
        "List_of_container_and_contents_indicators",
        "List_of_juxtaposition_indicators",
    ],
    "letter-selection": ["List_of_letter_selection_indicators"],
    "alternation": ["List_of_substitution_and_movement_indicators"],
}


@dataclass
class IndicatorType:
    slug: str
    title: str
    blurb: str
    georgeho_wordplays: list[str] = field(default_factory=list)
    clue_clinic_ids: list[int] = field(default_factory=list)
    crossword_unclued_path: str | None = None
    unscramblerer_path: str | None = None
    solve_the_crossword_slug: str | None = None
    daily_cryptic_anchor: str | None = None
    allow_digits: bool = False
    curated_extras: list[str] = field(default_factory=list)


INDICATOR_TYPES: list[IndicatorType] = [
    IndicatorType(
        slug="anagram",
        title="Anagram indicators",
        blurb="Candidates for rearrangement — grammar and context decide.",
        georgeho_wordplays=["anagram"],
        clue_clinic_ids=[461, 3503],
        crossword_unclued_path="2008/09/anagram-indicators.html",
        unscramblerer_path="anagram-indicators/",
        solve_the_crossword_slug="anagram-indicators",
        daily_cryptic_anchor="Anagram Indicators",
        curated_extras=[
            "kerfuffled", "discombobulated", "after a makeover", "given a makeover",
            "squiffy", "trolleyed", "doctored", "fiddled with", "tampered with",
            "in a state", "in a bind", "on the rampage", "out of whack",
            "stewed", "devilled", "pickled", "fermented", "marinated", "tenderised",
            "topsy-turvy", "every which way", "all over the shop", "in a tizzy",
            "in a whirl", "in commotion", "in uproar", "in a flutter", "in a heap",
            "brahms and liszt", "merry", "sozzled", "legless", "paralytic",
            "monkeyed with", "mucked up", "mucked about", "played with", "toyed with",
            "refurbished", "overhauled", "reimagined", "reconfigured", "revamped",
        ],
    ),
    IndicatorType(
        slug="hidden",
        title="Hidden word indicators",
        blurb="Signal that consecutive letters of the answer lurk in the clue text.",
        georgeho_wordplays=["hidden"],
        clue_clinic_ids=[449],
        crossword_unclued_path="2009/03/hidden-word-indicators.html",
        unscramblerer_path="hidden-word-indicators/",
        solve_the_crossword_slug="hidden-word-clues",
        daily_cryptic_anchor="Hidden Word Indicators",
        curated_extras=[
            "from", "out of", "segment of", "fragment of", "piece of", "bit of",
            "passage from", "stretch of", "run of", "string of", "snatch of",
            "glimpse of", "flash of", "trace of", "hint of", "touch of",
            "contained in", "embedded in", "nested in", "packed in", "stored in",
            "lying in", "resting in", "sitting in", "lying within", "to be found in",
            "discoverable in", "identifiable in", "detectable in", "visible in",
            "essentially", "fundamentally", "character in", "characters in",
            "clue to", "key to", "secreted in", "smuggled in", "camouflaged in",
            "tucked away in", "nestling in", "lurking in", "hidden away in",
            "a bit of", "a little of", "a touch of", "a hint of", "a trace of",
            "sample from", "extract from", "slice from", "cut from", "clip from",
        ],
    ),
    IndicatorType(
        slug="reversal",
        title="Reversal indicators",
        blurb="Signal reading a word or phrase backwards. Directional cues match grid orientation.",
        georgeho_wordplays=["reversal"],
        clue_clinic_ids=[441, 2797],
        crossword_unclued_path="2009/07/reversal-indicators.html",
        unscramblerer_path="reversal-indicators/",
        solve_the_crossword_slug="reversal-clues",
        daily_cryptic_anchor="Reversal Indicators",
        curated_extras=[
            "going west", "heading west", "westbound", "from the east", "leftwards",
            "going north", "northbound", "southbound", "eastbound", "going east",
            "going south", "skyward", "northward", "southward", "eastward", "westward",
            "the wrong way", "in reverse", "retrograde", "recurrent", "back to front",
            "whichever way you look at it", "to and fro", "up or down",
            "backslide", "brought about", "come back", "flipped over", "knocked over",
            "held up", "lifted", "sent back", "turned back", "turned around",
            "running back", "looking back", "in retreat", "in reverse order",
            "counter-clockwise", "anticlockwise", "clockwise",
        ],
    ),
    IndicatorType(
        slug="homophone",
        title="Homophone indicators",
        blurb="Signal that clued material sounds like the answer.",
        georgeho_wordplays=["homophone"],
        clue_clinic_ids=[455],
        crossword_unclued_path="2009/02/homophone-indicators.html",
        unscramblerer_path="homophone-indicators/",
        solve_the_crossword_slug="homophone-clues",
        daily_cryptic_anchor="Homophone Indicators",
        curated_extras=[
            "audibly", "when spoken", "in speech", "pronounced", "in pronunciation",
            "to the ear", "on the phone", "on television", "on stage", "on air",
            "as pronounced", "phonetically", "in dialect", "with an accent",
            "by the sound of it", "so they say", "orally", "vocally", "out loud",
            "on the radio", "in a podcast", "for the mic", "for the listener",
            "recited", "declared", "uttered", "announced", "it's said",
            "we're told", "one hears", "did you say", "so to speak",
        ],
    ),
    IndicatorType(
        slug="deletion",
        title="Deletion indicators",
        blurb="Signal removing letter(s) from fodder — head, tail, middle, or named letters.",
        georgeho_wordplays=["deletion"],
        clue_clinic_ids=[7176, 3440],
        crossword_unclued_path="2009/04/deletion-indicators.html",
        unscramblerer_path="deletion-indicators/",
        solve_the_crossword_slug="deletion-clues",
        daily_cryptic_anchor="Deletion Indicators",
        curated_extras=[
            "beheaded", "decapitated", "head removed", "losing its head", "losing head",
            "curtailed", "tail removed", "docked", "clipped", "trimmed", "shortened",
            "gutted", "hollowed out", "without middle", "middle removed", "heart removed",
            "excised", "expunged", "elided", "omitted", "stripped", "pared",
            "deprived of", "stripped of", "bereft of", "shorn of", "robbed of",
            "excluding", "exclusive of", "less", "minus", "save", "except",
            "not including", "bar", "barring", "outside", "apart from",
            "cut short", "cut off", "chopped off", "broken off", "nipped off",
            "losing heart", "losing its heart", "losing centre", "losing middle",
            "unopened", "unstarted", "unfinished", "incomplete", "almost entirely",
        ],
    ),
    IndicatorType(
        slug="containment",
        title="Containment indicators",
        blurb="Container, contents, and insertion — one letter run placed inside another.",
        georgeho_wordplays=["container", "insertion"],
        clue_clinic_ids=[419, 1563],
        crossword_unclued_path="2009/02/container-and-content-indicators.html",
        unscramblerer_path="container-contents-indicators/",
        solve_the_crossword_slug="container-clues",
        daily_cryptic_anchor="Container Indicators",
        curated_extras=[
            "wrapping", "wrapped around", "enclosing", "enclosed by", "encasing",
            "packing", "packed into", "stuffed into", "pushed into", "slotted into",
            "inserted into", "placed in", "put in", "put into", "set in",
            "sandwiched", "sandwiching", "bracketed", "framed by", "bounded by",
            "split by", "splitting", "pierced by", "penetrated by", "threaded through",
            "swallowing", "swallows", "swallowed by", "devouring", "devoured by",
            "grabbing", "grabs", "embracing", "embraced by", "embraces",
            "harbouring", "harbours", "sheltering", "shelters", "housing", "houses",
            "covering", "covers", "covered by", "surrounding", "surrounds",
            "caught in", "stuck in", "trapped in", "pinned in", "wedged in",
            "invading", "invades", "penetrating", "penetrates", "interrupting",
            "acquiring", "keeping", "possessing", "occupying", "getting into",
        ],
    ),
    IndicatorType(
        slug="letter-selection",
        title="Letter-selection indicators",
        blurb="Initial, final, alternate, and other letter-picking wordplay.",
        georgeho_wordplays=[],
        clue_clinic_ids=[370, 1614],
        crossword_unclued_path="2009/04/letter-sequence-indicators.html",
        unscramblerer_path="selection-indicators/",
        allow_digits=True,
        curated_extras=[
            "initially", "at first", "to begin with", "from the start", "from the outset",
            "primarily", "opening", "opening letters", "first letters", "first of all",
            "starts of", "beginnings of", "heads of", "leaders of", "leading letters",
            "ultimately", "at last", "in the end", "finally", "lastly", "eventually",
            "end of", "ends of", "tails of", "final letters", "closing letters",
            "oddly", "evenly", "regularly", "every other", "alternate letters",
            "second letters", "third letters", "fourth letters", "middle of", "centre of",
            "heart of", "core of", "extracting", "taking from", "selecting from",
            "50%", "half of", "one half of", "alpha and omega in", "beginning and end of",
            "outside of", "edges of", "borders of", "sides of", "insides of",
            "every second letter", "every third letter", "every fourth letter",
            "primarily", "principally", "mainly", "mostly", "chiefly",
            "capitals of", "initials of", "abbreviations of",
        ],
    ),
    IndicatorType(
        slug="alternation",
        title="Alternation indicators",
        blurb="Signal taking alternate letters or every Nth letter from fodder.",
        georgeho_wordplays=["alternation"],
        clue_clinic_ids=[4278],
        daily_cryptic_anchor=None,
        curated_extras=[
            "every other letter", "alternate letters", "alternating letters",
            "odd letters", "even letters", "odd ones", "even ones",
            "second and fourth", "first and third", "every second",
            "alternate bits of", "alternately", "at intervals",
            "dropping every second", "even bits of", "odd bits of",
            "every other", "every alternate", "alternate characters",
            "selected letters", "regular intervals",
        ],
    ),
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


def norm(s: str) -> str:
    s = html_lib.unescape(s.strip())
    s = re.sub(r"\s+", " ", s)
    return s.lower()


def add_entry(
    store: dict[str, dict],
    indicator: str,
    source: str,
    *,
    category: str | None = None,
    note: str | None = None,
    allow_digits: bool = False,
) -> bool:
    indicator = norm(indicator)
    if not indicator or len(indicator) > 80:
        return False
    if not allow_digits and re.search(r"[0-9$#@]", indicator):
        return False
    if allow_digits and re.search(r"[$#@]", indicator):
        return False
    if indicator in SKIP_WORDS:
        return False
    if indicator.startswith(("http", "www.")):
        return False
    if re.fullmatch(r"[^a-z0-9%\-' ]+", indicator):
        return False
    before = indicator not in store
    entry = store.setdefault(
        indicator,
        {"indicator": indicator, "sources": set(), "categories": set(), "notes": set()},
    )
    entry["sources"].add(source)
    if category:
        entry["categories"].add(category)
    if note:
        entry["notes"].add(note)
    return before


def split_alternatives(text: str) -> list[str]:
    text = html_lib.unescape(text.strip())
    if not text:
        return []
    parts = re.split(r"\s*[,;/|]\s*|\s+or\s+", text, flags=re.I)
    return [p.strip() for p in parts if p.strip()]


def scrape_clue_clinic(store: dict[str, dict], page_ids: list[int], *, allow_digits: bool = False) -> int:
    count = 0
    for page_id in page_ids:
        url = f"https://clueclinic.com/index.php/wp-json/wp/v2/pages/{page_id}"
        html = json.loads(fetch(url))["content"]["rendered"]
        cache = SOURCES_DIR / f"clueclinic-{page_id}.html"
        cache.parent.mkdir(parents=True, exist_ok=True)
        cache.write_text(html, encoding="utf-8")

        for row_html in re.findall(r"<tr class=\"row-[^\"]*\">(.*?)</tr>", html, re.S):
            cells = re.findall(r'<td class="column-\d+">([^<]*)</td>', row_html)
            if not cells or cells[0].strip().lower() == "indicator":
                continue
            primary = cells[0].strip()
            category = None
            for cell in cells[2:5]:
                c = cell.strip()
                if c and c not in {"Standard", "Advanced"} and not c.startswith("V*"):
                    if any(
                        k in c.lower()
                        for k in (
                            "reduction", "departure", "insertion", "containment",
                            "selection", "behead", "curtail", "hidden", "reversal",
                            "homophone", "alternat",
                        )
                    ):
                        category = c.lower()
                        break
            if add_entry(
                store, primary, "clue-clinic", category=category, allow_digits=allow_digits
            ):
                count += 1
            if len(cells) > 1:
                for alt in split_alternatives(cells[1]):
                    if add_entry(
                        store,
                        alt,
                        "clue-clinic",
                        category=category,
                        note="alternative",
                        allow_digits=allow_digits,
                    ):
                        count += 1

        for m in re.finditer(
            r'<td class="column-1">([^<]+)</td><td class="column-2">[^<]*</td>'
            r'<td class="column-3">(Standard|Advanced)</td>',
            html,
        ):
            ind = norm(m.group(1))
            if ind in store:
                store[ind]["notes"].add(m.group(2).lower())
    return count


def scrape_crossword_unclued(store: dict[str, dict], path: str) -> int:
    url = f"https://www.crosswordunclued.com/{path}"
    text = fetch(url)
    slug = path.rsplit("/", 1)[-1].replace(".html", "")
    (SOURCES_DIR / f"crossword-unclued-{slug}.html").write_text(text, encoding="utf-8")
    count = 0
    for cell in re.findall(r"<td[^>]*>(.*?)</td>", text, re.S):
        if "Starting With" in cell or "<a " in cell:
            continue
        plain = re.sub(r"<br\s*/?>", " ", cell, flags=re.I)
        plain = re.sub(r"<[^>]+>", " ", plain)
        for token in re.split(r"\s{2,}|\s+(?=[A-Z'-])", plain):
            token = token.strip(" ,.")
            if not token:
                continue
            if re.match(r"^[A-Z][A-Z' -]+$", token) or re.match(
                r"^[A-Z][a-z]+(?: [A-Z][a-z'-]+)*$", token
            ):
                if add_entry(store, token.lower(), "crossword-unclued"):
                    count += 1
    return count


def scrape_solve_the_crossword(store: dict[str, dict], slug: str) -> int:
    url = f"https://solvethecrossword.com/guide/{slug}"
    text = fetch(url)
    (SOURCES_DIR / f"solvethecrossword-{slug}.html").write_text(text, encoding="utf-8")
    count = 0
    for m in re.finditer(r">([a-z][a-z0-9' -]{1,50})</li>", text):
        if add_entry(store, m.group(1), "solve-the-crossword"):
            count += 1
    return count


def scrape_unscramblerer(store: dict[str, dict], path: str) -> int:
    url = f"https://www.unscramblerer.com/{path}"
    text = fetch(url)
    slug = path.strip("/").replace("/", "-")
    (SOURCES_DIR / f"unscramblerer-{slug}.html").write_text(text, encoding="utf-8")
    count = 0
    category = None
    for chunk in re.split(r"(<h2[^>]*>.*?</h2>)", text, flags=re.I | re.S):
        hm = re.match(r"<h2[^>]*>(.*?)</h2>", chunk, re.I | re.S)
        if hm:
            category = re.sub(r"<[^>]+>", "", hm.group(1)).strip().lower()
            continue
        for m in re.finditer(
            r'/unscramble-word/([a-z][a-z-]*)">([^<]*)</a>', chunk, re.I
        ):
            word = m.group(1).replace("-", " ")
            if add_entry(store, word, "unscramblerer", category=category):
                count += 1
            link_text = m.group(2).strip()
            if link_text and norm(link_text) != norm(word):
                if add_entry(store, link_text, "unscramblerer", category=category):
                    count += 1
        for m in re.finditer(r"<li><b>\d+\.</b>\s*([^<]+)</li>", chunk):
            if add_entry(store, m.group(1), "unscramblerer", category=category):
                count += 1
        for block in re.findall(r'class="words1"[^>]*>(.*?)</ul>', chunk, re.S):
            for m in re.finditer(r"<li>([^<]+)</li>", block):
                token = re.sub(r"<[^>]+>", "", m.group(1)).strip()
                token = re.sub(r"^\d+\.\s*", "", token)
                if add_entry(store, token, "unscramblerer", category=category):
                    count += 1
    return count


def _fetch_georgeho_prefix(wordplay: str, prefix: str) -> tuple[list[str], bool]:
    sql = (
        "select distinct indicator from indicators "
        f'where "wordplay" = "{wordplay}" and indicator like "{prefix}%" '
        "order by indicator limit 1000"
    )
    url = f"https://cryptics.georgeho.org/data.json?sql={quote(sql)}"
    payload = json.loads(fetch(url))
    if not payload.get("ok"):
        return [], False
    rows = [row[0] for row in payload.get("rows") or [] if row and row[0]]
    truncated = bool(payload.get("truncated")) or len(rows) >= 1000
    return rows, truncated


def scrape_georgeho(store: dict[str, dict], wordplays: list[str]) -> int:
    if not wordplays:
        return 0
    count = 0
    for wordplay in wordplays:
        cache = SOURCES_DIR / f"georgeho-{wordplay}.json"
        all_rows: set[str] = set()
        if cache.is_file():
            all_rows.update(json.loads(cache.read_text(encoding="utf-8")))

        for letter in "abcdefghijklmnopqrstuvwxyz":
            try:
                rows, truncated = _fetch_georgeho_prefix(wordplay, letter)
                all_rows.update(rows)
                if truncated:
                    for letter2 in "abcdefghijklmnopqrstuvwxyz":
                        rows2, _ = _fetch_georgeho_prefix(wordplay, letter + letter2)
                        all_rows.update(rows2)
                        time.sleep(0.2)
                time.sleep(0.25)
            except Exception:
                continue

        if all_rows:
            cache.parent.mkdir(parents=True, exist_ok=True)
            cache.write_text(
                json.dumps(sorted(all_rows), indent=2), encoding="utf-8"
            )
        for ind in sorted(all_rows):
            if add_entry(store, ind, "cryptics-georgeho"):
                count += 1
    return count


def scrape_minute_cryptic_anagram(store: dict[str, dict]) -> int:
    url = "https://minutecryptic.org/anagram-indicators-complete-list"
    try:
        text = fetch(url)
    except Exception:
        return 0
    (SOURCES_DIR / "minute-cryptic-anagram.html").write_text(text, encoding="utf-8")
    count = 0
    for m in re.finditer(r'class="indicator-tag">([^<]+)</span>', text):
        if add_entry(store, m.group(1), "minute-cryptic"):
            count += 1
    for m in re.finditer(
        r'<td[^>]*>\s*([a-z][a-z0-9 \'-]{1,50}?)\s*</td>', text, re.I
    ):
        if add_entry(store, m.group(1), "minute-cryptic"):
            count += 1
    return count


def scrape_daily_cryptic(store: dict[str, dict], anchor: str) -> int:
    url = "https://dailycryptic.org/cryptic-indicators"
    try:
        text = fetch(url)
    except Exception:
        return 0
    (SOURCES_DIR / "daily-cryptic-indicators.html").write_text(text, encoding="utf-8")
    count = 0
    target = anchor.strip().lower()
    for m in re.finditer(
        r"<h2[^>]*>([^<]+)</h2>(.*?)(?=<h2[^>]*>|$)", text, re.I | re.S
    ):
        if m.group(1).strip().lower() != target:
            continue
        section = m.group(2)
        for token in re.findall(
            r"rounded-full border px-3 py-1[^>]*>([^<]+)</span>", section
        ):
            if add_entry(store, token, "daily-cryptic"):
                count += 1
        for token in re.findall(r">([a-z][a-z0-9' -]{1,40})<", section):
            if add_entry(store, token, "daily-cryptic"):
                count += 1
        break
    return count


def _clean_wiki_indicator(text: str) -> str:
    text = html_lib.unescape(text.strip())
    text = re.sub(r"[*+]+$", "", text).strip()
    return text


def scrape_cryptipedia(
    store: dict[str, dict], pages: list[str], *, allow_digits: bool = False
) -> int:
    count = 0
    for page in pages:
        url = f"https://cryptics.fandom.com/wiki/{page}"
        text = fetch(url)
        cache = SOURCES_DIR / f"cryptipedia-{page}.html"
        cache.parent.mkdir(parents=True, exist_ok=True)
        cache.write_text(text, encoding="utf-8")

        body = text
        m = re.search(
            r'class="mw-content-ltr mw-parser-output"[^>]*>(.*)',
            text,
            re.S,
        )
        if m:
            body = m.group(1)
            end = re.search(r'<div class="printfooter"', body)
            if end:
                body = body[: end.start()]

        for lm in re.finditer(r"<li>([^<]{2,80})</li>", body, re.I):
            ind = _clean_wiki_indicator(lm.group(1))
            if add_entry(store, ind, "cryptipedia", allow_digits=allow_digits):
                count += 1
        time.sleep(0.5)
    return count


def scrape_wordsup(
    store: dict[str, dict], path: str, *, allow_digits: bool = False
) -> int:
    url = f"https://wordsup.co.uk/{path}"
    text = fetch(url)
    slug = path.replace(".php", "")
    cache = SOURCES_DIR / f"wordsup-{slug}.html"
    cache.parent.mkdir(parents=True, exist_ok=True)
    cache.write_text(text, encoding="utf-8")
    count = 0
    for m in re.finditer(
        r'class="col-md-3 col-sm-4 col-xs-6">([^<]+)</div>', text
    ):
        if add_entry(store, m.group(1), "wordsup", allow_digits=allow_digits):
            count += 1
    return count


def build_type(cfg: IndicatorType) -> dict[str, dict]:
    store: dict[str, dict] = {}
    steps: list[tuple[str, callable]] = []

    if cfg.clue_clinic_ids:
        steps.append(
            (
                "clue-clinic",
                lambda s: scrape_clue_clinic(
                    s, cfg.clue_clinic_ids, allow_digits=cfg.allow_digits
                ),
            )
        )
    if cfg.solve_the_crossword_slug:
        steps.append(
            (
                "solve-the-crossword",
                lambda s: scrape_solve_the_crossword(s, cfg.solve_the_crossword_slug),
            )
        )
    if cfg.crossword_unclued_path:
        steps.append(
            (
                "crossword-unclued",
                lambda s: scrape_crossword_unclued(s, cfg.crossword_unclued_path),
            )
        )
    if cfg.georgeho_wordplays:
        steps.append(
            ("cryptics-georgeho", lambda s: scrape_georgeho(s, cfg.georgeho_wordplays))
        )
    if cfg.unscramblerer_path:
        steps.append(
            (
                "unscramblerer",
                lambda s: scrape_unscramblerer(s, cfg.unscramblerer_path),
            )
        )
    if cfg.slug == "anagram":
        steps.append(("minute-cryptic", scrape_minute_cryptic_anagram))
    if cfg.daily_cryptic_anchor:
        steps.append(
            (
                "daily-cryptic",
                lambda s: scrape_daily_cryptic(s, cfg.daily_cryptic_anchor),
            )
        )
    if cfg.slug in WORDSUP_PAGES:
        path = WORDSUP_PAGES[cfg.slug]
        steps.append(
            (
                "wordsup",
                lambda s, p=path: scrape_wordsup(
                    s, p, allow_digits=cfg.allow_digits
                ),
            )
        )
    if cfg.slug in CRYPTIPEDIA_PAGES:
        pages = CRYPTIPEDIA_PAGES[cfg.slug]
        steps.append(
            (
                "cryptipedia",
                lambda s, pages=pages: scrape_cryptipedia(
                    s, pages, allow_digits=cfg.allow_digits
                ),
            )
        )
    if cfg.curated_extras:
        steps.append(
            (
                "curated-extras",
                lambda s: sum(
                    add_entry(
                        s, x, "curated-extras", allow_digits=cfg.allow_digits
                    )
                    for x in cfg.curated_extras
                ),
            )
        )

    print(f"\n=== {cfg.title} ({cfg.slug}) ===", flush=True)
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


def write_outputs(cfg: IndicatorType, store: dict[str, dict]) -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    base = f"{cfg.slug}-indicators"
    ordered = sorted(store.values(), key=lambda e: e["indicator"])

    serializable = [
        {
            "indicator": e["indicator"],
            "sources": sorted(e["sources"]),
            "categories": sorted(e["categories"]),
            "notes": sorted(e["notes"]),
        }
        for e in ordered
    ]

    meta = {
        "type": cfg.slug,
        "title": cfg.title,
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

    by_cat: dict[str, list[dict]] = defaultdict(list)
    for e in serializable:
        if e["categories"]:
            for cat in e["categories"]:
                by_cat[cat].append(e)

    (OUT_DIR / f"{base}.html").write_text(
        render_html(cfg, meta, by_cat), encoding="utf-8"
    )
    return len(serializable)


def render_html(cfg: IndicatorType, meta: dict, by_cat: dict[str, list[dict]]) -> str:
    count = meta["count"]
    sources = ", ".join(meta["sources"])

    def chip(entry: dict) -> str:
        src = html_lib.escape(", ".join(entry["sources"]))
        return (
            f'<span class="ind" title="Sources: {src}">'
            f"{html_lib.escape(entry['indicator'])}</span>"
        )

    cat_sections = []
    for cat in sorted(by_cat):
        items = sorted(by_cat[cat], key=lambda e: e["indicator"])
        chips = "\n".join(chip(e) for e in items)
        cat_sections.append(
            f'<section class="cat"><h2>{html_lib.escape(cat.title())} '
            f'<span class="n">({len(items)})</span></h2>'
            f'<div class="grid">\n{chips}\n</div></section>'
        )

    all_chips = "\n".join(chip(e) for e in meta["entries"])

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>{html_lib.escape(cfg.title)} ({count}) — Exet offline list</title>
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
              position: sticky; top: 0; z-index: 2; display: flex; gap: 8px; flex-wrap: wrap; align-items: center; }}
  #q {{ flex: 1 1 200px; padding: 6px 10px; font: inherit; border: 1px solid var(--border); border-radius: 4px; }}
  #stats {{ color: var(--muted); font-size: 0.85rem; }}
  main {{ padding: 12px 16px 32px; }}
  .cat h2 {{ font-size: 1rem; margin: 20px 0 8px; color: var(--accent); }}
  .cat .n {{ color: var(--muted); font-weight: normal; }}
  .grid {{ display: flex; flex-wrap: wrap; gap: 6px; }}
  .ind {{ background: var(--chip); border: 1px solid #d0dcee; border-radius: 4px;
          padding: 3px 8px; font-size: 0.92rem; cursor: default; }}
  .ind.hide {{ display: none; }}
  .ind.hi {{ background: var(--chip-hi); border-color: #f0c040; }}
  #all h2 {{ font-size: 1rem; margin: 0 0 8px; }}
</style>
</head>
<body>
<header>
  <h1>{html_lib.escape(cfg.title)}</h1>
  <p>{count} entries · built {meta["built"]} · merged from: {html_lib.escape(sources)}</p>
  <p>{html_lib.escape(cfg.blurb)}</p>
</header>
<div id="toolbar">
  <input type="search" id="q" placeholder="Filter indicators…" autofocus>
  <span id="stats">{count} shown</span>
</div>
<main>
  {"".join(cat_sections)}
  <section id="all">
    <h2>All indicators <span class="n">({count})</span></h2>
    <div class="grid" id="grid">
{all_chips}
    </div>
  </section>
</main>
<script>
(function() {{
  const q = document.getElementById('q');
  const stats = document.getElementById('stats');
  function apply() {{
    const term = q.value.trim().toLowerCase();
    let shown = 0;
    for (const el of document.querySelectorAll('.ind')) {{
      const ok = !term || el.textContent.toLowerCase().includes(term);
      el.classList.toggle('hide', !ok);
      el.classList.toggle('hi', ok && term.length > 0);
      if (ok) shown++;
    }}
    stats.textContent = shown + ' shown';
    for (const sec of document.querySelectorAll('.cat')) {{
      sec.style.display = sec.querySelectorAll('.ind:not(.hide)').length ? '' : 'none';
    }}
  }}
  q.addEventListener('input', apply);
  apply();
}})();
</script>
</body>
</html>
"""


def main(argv: list[str]) -> int:
    wanted = {a.lower() for a in argv[1:]}
    types = INDICATOR_TYPES
    if wanted:
        types = [t for t in INDICATOR_TYPES if t.slug in wanted]
        if not types:
            print(f"Unknown type(s): {', '.join(sorted(wanted))}", file=sys.stderr)
            print("Known:", ", ".join(t.slug for t in INDICATOR_TYPES), file=sys.stderr)
            return 1

    summary: list[tuple[str, int]] = []
    for cfg in types:
        store = build_type(cfg)
        n = write_outputs(cfg, store)
        summary.append((cfg.slug, n))

    print("\n--- Summary ---", flush=True)
    for slug, n in summary:
        print(f"  {slug}: {n} indicators -> lists/{slug}-indicators.html", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
