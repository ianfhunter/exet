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

# Semantic groups for clue words (colour-coded in abbreviations.html).
# Order matters: earlier = preferred when a word matches multiple rules.
CLUE_CATEGORIES: list[tuple[str, str, str, str]] = [
    ("chemicals", "Chemicals", "#e8f4fd", "#b8d4ee"),
    ("geography", "Geography", "#eef8ef", "#c8dfc9"),
    ("roman-numerals", "Roman numerals", "#fff0e6", "#f0c8a8"),
    ("music", "Music", "#f3ecff", "#d4c4f0"),
    ("military", "Military & navy", "#fde8e8", "#e8b4b4"),
    ("science", "Science & units", "#e6f7fa", "#a8dce8"),
    ("church", "Church & religion", "#fff8e6", "#f0dfa0"),
    ("politics", "Politics & government", "#fce8f3", "#e8b4d4"),
    ("honours", "Honours & titles", "#f0f0ff", "#c8c8f0"),
    ("language", "Language & grammar", "#eef3fb", "#d0dcee"),
    ("time", "Time & dates", "#f5f5f5", "#d8d8d8"),
    ("money", "Money & currency", "#fff6e6", "#f0d090"),
    ("sport", "Sport & games", "#e8fff0", "#b4e8c8"),
    ("chess", "Chess", "#f5f0e8", "#d8cbb0"),
    ("general", "General", "#f7f7f7", "#e0e0e0"),
]
CLUE_CATEGORY_SLUGS = [slug for slug, *_ in CLUE_CATEGORIES]
CLUE_CATEGORY_LABELS = {slug: label for slug, label, *_ in CLUE_CATEGORIES}
_CATEGORY_RANK = {slug: idx for idx, slug in enumerate(CLUE_CATEGORY_SLUGS)}

_CHEMICAL_WORDS = frozenset(
    """
    actinium aluminium aluminum antimony argon arsenic astatine barium
    beryllium bismuth boron bromine cadmium caesium calcium carbon cerium
    caesium cesium chlorine chromium cobalt copper curium dysprosium
    einsteinium erbium europium fluorine francium gadolinium gallium
    germanium gold hafnium helium holmium hydrogen indium iodine iridium
    iron krypton lanthanum lead lithium lutetium magnesium manganese
    mercury molybdenum neodymium neon neptunium nickel niobium nitrogen
    osmium oxygen palladium phosphorus platinum plutonium polonium
    potassium praseodymium promethium protactinium radium radon rhenium
    rhodium rubidium ruthenium samarium scandium selenium silicon silver
    sodium strontium sulphur sulfur tantalum technetium tellurium terbium
    thallium thorium thulium tin titanium tungsten uranium vanadium xenon
    ytterbium yttrium zinc zirconium
    chemical chemist chemistry nitrate nitre fertiliser fertilizer
    """.split()
)

_GEOGRAPHY_WORDS = frozenset(
    """
    africa america american australia australian austria belgium britain
    british california canada canadian china chinese city compass continent
    country county eastern english europe european france french georgia
    german germany iceland india indian ireland irish island israel italy
    japan japanese korea london northern ohio orient southern state states
    swiss switzerland texas uk ukraine united utah venezuela wales western
    yemen yugoslavia zaire zambia zimbabwe north south east west
    """.split()
)

_ROMAN_WORDS = frozenset(
    """
    five fifty four grand hundred hundred thousand one seven six ten
    thousand three thousand twelve twenty two eleven eight nine forty
    ninety thirty sixty fifteen sixteen seventeen eighteen nineteen
    """.split()
)

# ICAO/NATO phonetic alphabet (cryptic crosswords: word -> initial letter).
NATO_PHONETIC: list[tuple[str, str]] = [
    ("alfa", "A"),
    ("alpha", "A"),
    ("bravo", "B"),
    ("charlie", "C"),
    ("delta", "D"),
    ("echo", "E"),
    ("foxtrot", "F"),
    ("golf", "G"),
    ("hotel", "H"),
    ("india", "I"),
    ("juliet", "J"),
    ("juliett", "J"),
    ("kilo", "K"),
    ("lima", "L"),
    ("mike", "M"),
    ("november", "N"),
    ("oscar", "O"),
    ("papa", "P"),
    ("quebec", "Q"),
    ("romeo", "R"),
    ("sierra", "S"),
    ("tango", "T"),
    ("uniform", "U"),
    ("victor", "V"),
    ("whiskey", "W"),
    ("whisky", "W"),
    ("xray", "X"),
    ("x-ray", "X"),
    ("yankee", "Y"),
    ("zulu", "Z"),
]

_NUMBER_WORDS: dict[str, int] = {
    "zero": 0,
    "one": 1,
    "two": 2,
    "three": 3,
    "four": 4,
    "five": 5,
    "six": 6,
    "seven": 7,
    "eight": 8,
    "nine": 9,
    "ten": 10,
    "eleven": 11,
    "twelve": 12,
    "thirteen": 13,
    "fourteen": 14,
    "fifteen": 15,
    "sixteen": 16,
    "seventeen": 17,
    "eighteen": 18,
    "nineteen": 19,
    "twenty": 20,
    "thirty": 30,
    "forty": 40,
    "fifty": 50,
    "sixty": 60,
    "seventy": 70,
    "eighty": 80,
    "ninety": 90,
    "hundred": 100,
    "thousand": 1000,
    "grand": 1000,
}

_TENS = ("twenty", "thirty", "forty", "fifty", "sixty", "seventy", "eighty", "ninety")
_UNITS = (
    "one", "two", "three", "four", "five", "six", "seven", "eight", "nine",
)
_MULTIPLIERS = ("one", "two", "three", "four", "five", "six", "seven", "eight", "nine")


def int_to_roman(value: int) -> str:
    if value <= 0 or value > 3999:
        raise ValueError(value)
    numerals = [
        (1000, "M"), (900, "CM"), (500, "D"), (400, "CD"),
        (100, "C"), (90, "XC"), (50, "L"), (40, "XL"),
        (10, "X"), (9, "IX"), (5, "V"), (4, "IV"), (1, "I"),
    ]
    out: list[str] = []
    n = value
    for amount, symbol in numerals:
        while n >= amount:
            out.append(symbol)
            n -= amount
    return "".join(out)


def parse_number_phrase(phrase: str) -> int | None:
    """Parse common English number phrases used in cryptic Roman-numeral clues."""
    phrase = re.sub(r"\s+", " ", html_lib.unescape(phrase.strip())).lower()
    if not phrase:
        return None
    if phrase in _NUMBER_WORDS:
        return _NUMBER_WORDS[phrase]

    m = re.fullmatch(rf"({'|'.join(_MULTIPLIERS)}) hundred and ([a-z ]+)", phrase)
    if m:
        tail = parse_number_phrase(m.group(2))
        if tail is not None and 0 < tail < 100:
            return _NUMBER_WORDS[m.group(1)] * 100 + tail

    m = re.fullmatch(r"hundred and ([a-z ]+)", phrase)
    if m:
        tail = parse_number_phrase(m.group(1))
        if tail is not None and 0 < tail < 100:
            return 100 + tail

    m = re.fullmatch(r"one hundred and ([a-z ]+)", phrase)
    if m:
        tail = parse_number_phrase(m.group(1))
        if tail is not None and 0 < tail < 100:
            return 100 + tail

    m = re.fullmatch(rf"({'|'.join(_TENS)}) ({'|'.join(_UNITS)})", phrase)
    if m:
        return _NUMBER_WORDS[m.group(1)] + _NUMBER_WORDS[m.group(2)]

    m = re.fullmatch(rf"({'|'.join(_MULTIPLIERS)}) hundred(?: and ({'|'.join(_UNITS)}))?", phrase)
    if m:
        total = _NUMBER_WORDS[m.group(1)] * 100
        if m.group(2):
            total += _NUMBER_WORDS[m.group(2)]
        return total

    m = re.fullmatch(r"one thousand five hundred", phrase)
    if m:
        return 1500

    return None


def build_roman_clue_index() -> dict[str, str]:
    """Validated clue phrase -> Roman abbreviation."""
    phrases = [
        "one", "two", "three", "four", "five", "six", "seven", "eight", "nine",
        "ten", "eleven", "twelve", "twenty", "thirty", "forty", "fifty",
        "sixty", "seventy", "eighty", "ninety", "hundred", "thousand", "grand",
        "five hundred", "five hundred and one", "two hundred", "three hundred",
        "four hundred", "hundred and one", "hundred and fifty", "hundred and sixty",
        "fifty one", "one hundred and fifty", "two hundred and fifty",
        "one thousand five hundred",
    ]
    for tens in _TENS:
        for unit in _UNITS:
            phrases.append(f"{tens} {unit}")
    for mult in _MULTIPLIERS:
        phrases.append(f"{mult} hundred")
        for unit in _UNITS:
            phrases.append(f"{mult} hundred and {unit}")
    phrases.extend(["hundred and one", "hundred and fifty", "hundred and sixty"])

    index: dict[str, str] = {}
    for phrase in phrases:
        value = parse_number_phrase(phrase)
        if value is None or value <= 0 or value > 3999:
            continue
        index[re.sub(r"\s+", " ", phrase.strip()).lower()] = int_to_roman(value)
    return index


def _norm_clue_phrase(phrase: str) -> str:
    return re.sub(r"\s+", " ", html_lib.unescape(phrase.strip())).lower()


ROMAN_CLUE_ABBREV: dict[str, str] = build_roman_clue_index()
NATO_PHONETIC_WORDS = frozenset(_norm_clue_phrase(word) for word, _letter in NATO_PHONETIC)

_MUSIC_WORDS = frozenset(
    """
    alto bass chord do fa key la mi note piano re sharp sol soh te ti
    violin flat semitone tone musical soprano contralto clef
    """.split()
)

_MILITARY_WORDS = frozenset(
    """
    admiral airborne airman army artillery battalion captain colonel
    commando corporal fleet forces general grenadier guards infantry
    marine marines midshipman military navy officer pilot private rank
    rating regiment rifle sailor sapper seaman soldier tar troops
    veteran volunteer warrant
    """.split()
)

_SCIENCE_WORDS = frozenset(
    """
    acceleration ampere angstrom atomic capacity current density
    dimension distance electric electrical electron energy entropy
    equation examination force frequency gravity impedance magnetic
    mass measure metre meter molecular physics pressure quantum radiation
    temperature velocity voltage volume weight wavelength
    """.split()
)

_CHURCH_WORDS = frozenset(
    """
    abbey altar angel apostle archbishop canon cathedral chapel
    chaplain choir church clergy cleric communion convent crucifix
    divine ecclesiastical faith gospel holy mass minister monastery
    monk nun parish pastor prayer priest religion religious reverend
    saint sermon spiritual synagogue temple theology vicar
    """.split()
)

_POLITICS_WORDS = frozenset(
    """
    ballot cabinet chancellor congress conservative council councillor
    democracy democrat diplomatic election embassy governor labour
    legislature liberal mayor member minister ministry parliament
    party political politician president prime republic senator
    socialist tory union unionist whig
    """.split()
)

_HONOURS_WORDS = frozenset(
    """
    baron baronet baroness barony cbe count countess dame decoration
    duchess duke earl esquire honour honor knighthood lady lord marquess
    medal mbe obe om peer peerage prince princess queen royal sir viscount
    """.split()
)

_LANGUAGE_WORDS = frozenset(
    """
    adjective adverb article consonant dialect french grammar greek
    language latin letter noun phrase plural prefix pronoun speech suffix
    syllable verb vowel word
    """.split()
)

_TIME_WORDS = frozenset(
    """
    afternoon annum century date day decade evening hour midday midnight
    minute month morning noon quarter second week weekday weekend year
    january february march april may june july august september october
    november december
    """.split()
)

_MONEY_WORDS = frozenset(
    """
    account bill cent coin credit currency debit debt dollar euro finance
    franc money payment penny pound price shilling sterling
    """.split()
)

_SPORT_WORDS = frozenset(
    """
    ace ball cricket football golf hockey match olympic race rugby score
    sport sports team tennis wicket
    """.split()
)

# Single-word piece names and chess-only phrases (exact match, not token scan).
_CHESS_PIECES = frozenset(
    """
    bishop king queen knight rook pawn chess
    """.split()
)

_CHESS_PHRASES = frozenset(
    {
        "chess piece",
        "chess pieces",
        "chessman",
        "chessmen",
        "chess board",
        "chessboard",
        "chess grandmaster",
        "chess master",
        "checkmate",
        "stalemate",
        "castling",
        "gambit",
        "white square",
        "black square",
    }
)

_CATEGORY_RULES: list[tuple[str, frozenset[str]]] = [
    ("chemicals", _CHEMICAL_WORDS),
    ("geography", _GEOGRAPHY_WORDS),
    ("music", _MUSIC_WORDS),
    ("military", _MILITARY_WORDS),
    ("science", _SCIENCE_WORDS),
    ("church", _CHURCH_WORDS),
    ("politics", _POLITICS_WORDS),
    ("honours", _HONOURS_WORDS),
    ("language", _LANGUAGE_WORDS),
    ("time", _TIME_WORDS),
    ("money", _MONEY_WORDS),
    ("sport", _SPORT_WORDS),
]

_WIKI_CATEGORY_HINTS: list[tuple[str, tuple[str, ...]]] = [
    ("chemicals", ("chemical symbol", "chemical element")),
    ("roman-numerals", ("roman numeral",)),
    ("music", ("musical note", "musical notes")),
    ("language", ("from the latin", "latin ")),
    ("geography", ("country code", "vehicle registration", "us state")),
    ("honours", ("in heraldry", "decoration")),
    ("church", ("church of england", "roman catholic")),
    ("military", ("nato phonetic", "phonetic alphabet")),
    ("science", ("electric current", "genetic code")),
    ("money", ("penny", "denarius", "cent")),
    ("chess", ("chess", "chess piece")),
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


def is_abbrev_like(text: str) -> bool:
    """True when *text* looks like a crossword abbreviation (not a clue phrase)."""
    text = norm_space(text)
    if not text:
        return False
    if len(text) == 1 and text.isalnum():
        return True
    if " " in text or len(text) > 8:
        return False
    letters = [c for c in text if c.isalpha()]
    if not letters:
        return bool(re.match(r"^[0-9.+]+$", text))
    upper = sum(c.isupper() for c in letters)
    if upper / len(letters) >= 0.5:
        return True
    if len(text) <= 3 and text.isalpha() and text.isupper():
        return True
    return False


def is_abbrev_form(headword: str) -> bool:
    """True when *headword* is itself an abbreviation token (e.g. ab, tt, RN)."""
    headword = norm_space(headword)
    if not headword or " " in headword:
        return False
    if len(headword) == 1:
        return True
    if len(headword) <= 3 and headword.isalpha() and headword.islower():
        return True
    if len(headword) <= 6 and headword.isupper():
        return True
    return bool(re.match(r"^[0-9]+$", headword))


def abbrev_merge_key(abbreviation: str) -> str:
    """Case-insensitive key for merging the same abbreviation."""
    abbreviation = norm_space(abbreviation)
    if is_abbrev_like(abbreviation) or is_abbrev_form(abbreviation):
        return abbreviation.upper()
    return abbreviation.lower()


def abbrev_display(abbreviation: str) -> str:
    """Preferred display form after merging case variants."""
    abbreviation = norm_space(abbreviation)
    if is_abbrev_like(abbreviation) or is_abbrev_form(abbreviation):
        return abbreviation.upper()
    return abbreviation


def abbrev_alpha(abbreviation: str) -> str:
    """First-letter bucket for A–Z navigation (non-letters -> '#')."""
    abbreviation = norm_space(abbreviation)
    if not abbreviation:
        return "#"
    ch = abbreviation[0].upper()
    return ch if "A" <= ch <= "Z" else "#"


def wikipedia_line_category(line: str) -> str | None:
    low = line.lower()
    for slug, phrases in _WIKI_CATEGORY_HINTS:
        if any(p in low for p in phrases):
            return slug
    return None


def classify_clue_word(clue_word: str, hint: str | None = None) -> str:
    if hint and hint in _CATEGORY_RANK:
        return hint
    text = norm_headword(clue_word)
    if not text:
        return "general"
    if text in ROMAN_CLUE_ABBREV:
        return "roman-numerals"
    if text in _CHESS_PHRASES or text in _CHESS_PIECES:
        return "chess"
    if re.search(r"\bchess\b", text):
        return "chess"
    tokens = re.findall(r"[a-z0-9]+", text)
    for slug, words in _CATEGORY_RULES:
        if text in words or any(t in words for t in tokens):
            return slug
    if text in NATO_PHONETIC_WORDS:
        return "military"
    if re.search(r"\b(element|oxide|isotope|radium|uranium)\b", text):
        return "chemicals"
    if re.search(r"\b(states?|province|republic|kingdom|capital)\b", text):
        return "geography"
    if re.search(r"\b(roman|numeral|numerals)\b", text):
        return "roman-numerals"
    if re.search(r"\b(church|bishop|saint|holy|mass)\b", text):
        return "church"
    if re.search(r"\b(army|navy|regiment|soldier|sailor|air force)\b", text):
        return "military"
    if re.search(r"\b(lord|lady|sir|dame|honour|honor|knighthood)\b", text):
        return "honours"
    if re.search(r"\b(latin|french|greek|grammar|adjective|adverb)\b", text):
        return "language"
    return "general"


def pick_clue_category(existing: str | None, new: str) -> str:
    if not existing or existing == "general":
        return new
    if new == "general":
        return existing
    return existing if _CATEGORY_RANK[existing] <= _CATEGORY_RANK[new] else new


def invert_abbrev_entries(entries: list[dict]) -> list[dict]:
    """Pivot headword->expansion rows into abbreviation->clue words."""
    buckets: dict[str, dict] = {}

    def bucket_for(abbrev: str) -> dict:
        key = abbrev_merge_key(abbrev)
        if key not in buckets:
            buckets[key] = {
                "abbreviation": abbrev_display(abbrev),
                "alpha": abbrev_alpha(key),
                "clue_categories": {},
                "sources": set(),
                "notes": set(),
            }
        return buckets[key]

    def add_clue(row: dict, clue_word: str, category_hint: str | None = None) -> None:
        clue_word = norm_headword(clue_word)
        if not clue_word:
            return
        cat = classify_clue_word(clue_word, category_hint)
        row["clue_categories"][clue_word] = pick_clue_category(
            row["clue_categories"].get(clue_word), cat
        )

    for entry in entries:
        headword = entry["headword"]
        expansions = entry["expansions"]
        sources = entry.get("sources") or []
        notes = entry.get("notes") or []
        head_cat = entry.get("category")
        abbrev_style = is_abbrev_form(headword) and not any(
            is_abbrev_like(exp) for exp in expansions
        )

        if abbrev_style:
            row = bucket_for(headword)
            for exp in expansions:
                add_clue(row, exp)
            row["sources"].update(sources)
            row["notes"].update(notes)
            continue

        for exp in expansions:
            if is_abbrev_like(exp):
                row = bucket_for(exp)
                add_clue(row, headword, head_cat)
                row["sources"].update(sources)
                row["notes"].update(notes)
            elif is_abbrev_form(headword):
                row = bucket_for(headword)
                add_clue(row, exp)
                row["sources"].update(sources)
                row["notes"].update(notes)

    ordered = sorted(
        buckets.values(),
        key=lambda row: (
            row["alpha"] if row["alpha"] != "#" else "{",
            expansion_sort_key(row["abbreviation"]),
            row["abbreviation"].lower(),
        ),
    )
    return [
        {
            "abbreviation": row["abbreviation"],
            "alpha": row["alpha"],
            "clue_categories": row["clue_categories"],
            "sources": sorted(row["sources"]),
            "notes": sorted(row["notes"]),
        }
        for row in ordered
    ]


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
    category: str | None = None,
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
        {
            "headword": headword,
            "expansions": set(),
            "sources": set(),
            "notes": set(),
            "category": None,
        },
    )
    entry["expansions"].add(expansion)
    entry["sources"].add(source)
    if category:
        entry["category"] = pick_clue_category(entry.get("category"), category)
    if note:
        entry["notes"].add(note)
    if adv:
        entry["notes"].add("advanced")
    if unsound:
        entry["notes"].add("disputed")
    return before


def add_abbrev_text(
    store: dict[str, dict],
    headword: str,
    expansion_text: str,
    source: str,
    *,
    category: str | None = None,
) -> int:
    count = 0
    for exp in split_expansions(expansion_text):
        if add_abbrev(store, headword, exp, source, category=category):
            count += 1
        elif norm_headword(headword) in store:
            before = len(store[norm_headword(headword)]["expansions"])
            add_abbrev(store, headword, exp, source, category=category)
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
            cat = wikipedia_line_category(line)
            count += add_abbrev_text(store, m.group(1), m.group(2), "wikipedia", category=cat)
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


def sanitize_roman_numerals(store: dict[str, dict]) -> int:
    """Drop scraped number-phrase mappings that are not valid Roman numerals."""
    removed = 0
    for entry in store.values():
        headword = entry["headword"]
        for expansion in list(entry["expansions"]):
            clue: str | None = None
            abbrev: str | None = None
            if is_abbrev_form(headword) and not is_abbrev_like(expansion):
                abbrev, clue = headword, expansion
            elif is_abbrev_like(expansion) and not is_abbrev_form(headword):
                abbrev, clue = expansion, headword
            if not clue or not abbrev:
                continue
            value = parse_number_phrase(clue)
            if value is None or value <= 0 or value > 3999:
                continue
            expected = int_to_roman(value)
            if abbrev_merge_key(abbrev) != abbrev_merge_key(expected):
                entry["expansions"].discard(expansion)
                removed += 1
    return removed


def apply_curated_extras(store: dict[str, dict]) -> int:
    """Add validated Roman numerals and the full NATO phonetic alphabet."""
    added = 0
    for clue, abbrev in ROMAN_CLUE_ABBREV.items():
        added += add_abbrev(
            store, clue, abbrev, "curated", category="roman-numerals"
        )
    for word, letter in NATO_PHONETIC:
        added += add_abbrev(
            store, word, letter, "curated", category="military"
        )
    return added


def build_abbreviations() -> dict[str, dict]:
    store: dict[str, dict] = {}
    steps = [
        ("clue-clinic-all", lambda s: scrape_clue_clinic_abbrev(s, 365)),
        ("clue-clinic-standard", lambda s: scrape_clue_clinic_abbrev(s, 340)),
        ("mhl-yaml", scrape_mhl_yaml),
        ("longair", scrape_longair),
        ("wikipedia", scrape_wikipedia_abbrev),
        ("cryptipedia", scrape_cryptipedia_abbrev),
        ("sanitize-roman", lambda s: sanitize_roman_numerals(s)),
        ("curated-extras", apply_curated_extras),
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


def render_clue_cell(clue_categories: dict[str, str]) -> str:
    parts: list[str] = []
    for word in sorted(clue_categories, key=str.lower):
        cat = clue_categories[word]
        label = CLUE_CATEGORY_LABELS.get(cat, cat)
        parts.append(
            f'<span class="clue cat-{cat}" title="{html_lib.escape(label)}">'
            f"{html_lib.escape(word)}</span>"
        )
    return ", ".join(parts)


def render_abbrev_html(meta: dict) -> str:
    inverted = invert_abbrev_entries(meta["entries"])
    count = len(inverted)
    sources = ", ".join(meta["sources"])
    rows = []
    for entry in inverted:
        src = html_lib.escape(", ".join(entry["sources"]))
        abbrev = html_lib.escape(entry["abbreviation"])
        alpha = html_lib.escape(entry["alpha"])
        clues = render_clue_cell(entry["clue_categories"])
        note = html_lib.escape(", ".join(entry["notes"]))
        title = f"Sources: {src}" + (f" · Notes: {note}" if note else "")
        rows.append(
            f'<tr class="row" data-alpha="{alpha}" title="{title}">'
            f'<td class="abbrev">{abbrev}</td>'
            f'<td class="clues">{clues}</td></tr>'
        )
    body_rows = "\n".join(rows)
    blurb = (
        "Letters and short forms used in cryptic crosswords, with the clue words "
        "and phrases that commonly stand for each abbreviation (bits-and-pieces). "
        "Clue words are colour-coded by topic."
    )
    alpha_btns = "".join(
        f'<button type="button" class="alpha" data-letter="{ch}">{ch}</button>'
        for ch in "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
    )
    cat_css = "\n".join(
        f"  .cat-{slug} {{ background: {bg}; border: 1px solid {border}; "
        f"border-radius: 3px; padding: 1px 4px; }}"
        for slug, _label, bg, border in CLUE_CATEGORIES
    )
    legend = "".join(
        f'<span><i class="sw cat-{slug}"></i> {html_lib.escape(label)}</span>'
        for slug, label, bg, border in CLUE_CATEGORIES
        if slug != "general"
    )
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>Cryptic abbreviations ({count}) — Exet offline list</title>
<meta name="viewport" content="width=device-width, initial-scale=1">
<style>
  :root {{
    --bg: #fafafa; --fg: #222; --muted: #666; --accent: #1a5fb4;
    --hi: #ffe082; --border: #ddd; --chip: #eef3fb;
  }}
  body {{ font: 15px/1.45 system-ui, sans-serif; margin: 0; background: var(--bg); color: var(--fg); }}
  header {{ padding: 12px 16px; border-bottom: 1px solid var(--border); background: #fff; }}
  header h1 {{ margin: 0 0 4px; font-size: 1.2rem; }}
  header p {{ margin: 0; color: var(--muted); font-size: 0.85rem; }}
  .legend {{ display: flex; gap: 10px 14px; flex-wrap: wrap; margin-top: 8px;
              font-size: 0.82rem; color: var(--muted); }}
  .legend span {{ display: inline-flex; align-items: center; gap: 4px; }}
  .legend i.sw {{ display: inline-block; width: 12px; height: 12px; border-radius: 3px; }}
{cat_css}
  #toolbar {{ padding: 10px 16px; background: #fff; border-bottom: 1px solid var(--border);
              position: sticky; top: 0; z-index: 2; }}
  #toolbar-row {{ display: flex; gap: 8px; align-items: center; flex-wrap: wrap; }}
  #q {{ flex: 1 1 240px; padding: 6px 10px; font: inherit; border: 1px solid var(--border); border-radius: 4px; }}
  #stats {{ color: var(--muted); font-size: 0.85rem; white-space: nowrap; }}
  #alpha {{ display: flex; flex-wrap: wrap; gap: 4px; margin-top: 8px; }}
  #alpha button {{
    font: inherit; font-size: 0.82rem; min-width: 1.8em; padding: 3px 6px;
    border: 1px solid #d0dcee; border-radius: 4px; background: var(--chip); cursor: pointer;
  }}
  #alpha button:hover {{ border-color: var(--accent); }}
  #alpha button.active {{ background: var(--accent); color: #fff; border-color: var(--accent); }}
  #alpha button.all {{ font-weight: 600; }}
  main {{ padding: 12px 16px 32px; }}
  table {{ width: 100%; border-collapse: collapse; background: #fff; }}
  th, td {{ text-align: left; padding: 6px 10px; border-bottom: 1px solid var(--border); vertical-align: top; }}
  th {{ background: #f5f7fb; color: var(--accent); position: sticky; top: 118px; }}
  tr.hide {{ display: none; }}
  tr.hi {{ background: var(--hi); }}
  tr.hi .clue {{ opacity: 0.92; }}
  .abbrev {{ font-weight: 600; width: 12%; white-space: nowrap; }}
  .clues {{ color: #333; line-height: 1.65; }}
</style>
</head>
<body>
<header>
  <h1>Cryptic abbreviations</h1>
  <p>{count} abbreviations · built {meta["built"]} · merged from: {html_lib.escape(sources)}</p>
  <p>{html_lib.escape(blurb)}</p>
  <div class="legend">{legend}</div>
</header>
<div id="toolbar">
  <div id="toolbar-row">
    <input type="search" id="q" placeholder="Filter abbreviation or clue word…" autofocus>
    <span id="stats">{count} shown</span>
  </div>
  <div id="alpha">
    <button type="button" class="alpha all active" data-letter="">All</button>
{alpha_btns}
  </div>
</div>
<main>
  <table>
    <thead><tr><th>Abbreviation</th><th>Clue words</th></tr></thead>
    <tbody id="rows">
{body_rows}
    </tbody>
  </table>
</main>
<script>
(function() {{
  const q = document.getElementById('q');
  const stats = document.getElementById('stats');
  const alpha = document.getElementById('alpha');
  let letter = '';

  function applyFilter() {{
    const term = q.value.trim().toLowerCase();
    let shown = 0;
    for (const row of document.querySelectorAll('#rows tr')) {{
      const okLetter = !letter || row.dataset.alpha === letter;
      const text = row.textContent.toLowerCase();
      const okTerm = !term || text.includes(term);
      const ok = okLetter && okTerm;
      row.classList.toggle('hide', !ok);
      row.classList.toggle('hi', ok && term.length > 0);
      if (ok) shown++;
    }}
    stats.textContent = shown + ' shown';
  }}

  q.addEventListener('input', applyFilter);

  alpha.addEventListener('click', (ev) => {{
    const btn = ev.target.closest('button[data-letter]');
    if (!btn) return;
    letter = btn.dataset.letter;
    for (const b of alpha.querySelectorAll('button')) {{
      b.classList.toggle('active', b === btn);
    }}
    applyFilter();
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
