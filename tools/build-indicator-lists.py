#!/usr/bin/env python3
"""Scrape cryptic crossword indicators and build offline Exet lists.

Outputs one set per indicator type under lists/:
  {slug}-indicators.json
  {slug}-indicators.html
  {slug}-indicators.txt

Run from exet/:
  python tools/build-indicator-lists.py          # all types
  python tools/build-indicator-lists.py hidden # one type
  python tools/build-indicator-lists.py alternation --from-json
                                        # re-render from the committed json,
                                        # without scraping the sources again
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

ODD_PARITY = "odd letters"
EVEN_PARITY = "even letters"

ANAGRAM_FUNCTIONS = (
    "Adjective",
    "Adverb",
    "Past participle",
    "Present participle",
    "Verb imperative",
    "Verb indicative",
    "Noun expression",
    "Context-dependent",
)

IRREGULAR_PAST_PARTICIPLES = frozenset(
    """
    bent blown broke broken built burst cast caught dealt done drawn driven
    drunk fallen fed fled flown forged gone ground hung hurt laid led left
    lost made meant met misshapen mixed outdone overcome put read rent risen
    run set shaken shot shown shrunk slain slid smitten spun split spread
    sprung stuck strewn struck strung swept swollen swung thrown torn upset
    woven withdrawn wrecked wrung
    """.split()
)

# Which parity an alternation indicator names. "uneven" is tested first so it
# is not read as the "even" sitting inside it.
PARITY_NAMES = (
    (ODD_PARITY, re.compile(r"\bunevenl?y?\b")),
    (ODD_PARITY, re.compile(r"\bodd(s|ly)?\b")),
    (ODD_PARITY, re.compile(r"\b(first|1st) (and|,) ?(third|3rd)\b")),
    (EVEN_PARITY, re.compile(r"\beven(s|ly)?\b")),
    (EVEN_PARITY, re.compile(r"\bseconds?\b")),
    (EVEN_PARITY, re.compile(r"\b(second|2nd) (and|,) ?(fourth|4th)\b")),
)

# Naming a parity is only half the story: an indicator that names letters in
# order to throw them away leaves the solver holding the other parity, which
# is why "oddly dropped" and "even letters" both point at the evens.
PARITY_DROP = re.compile(
    r"\b("
    r"abandoned|absent|avoid(ing|ed)?|away|banished|blanked|bypass(ing|ed)?|"
    r"cancel(led|lation|lations)?|clipp(ed|ing)|culled|cut|deficient|"
    r"delet(e|ed|ing)|detached|disappear(s|ing|ed)?|discard(ed|ing)?|"
    r"dismiss(ed|ing)?|disregard(ed|ing)?|ditch(ed|ing)?|drop(s|ped|ping)?|"
    r"eras(ed|ing)|excis(ed|ion|ions)|exception(s)?|exclud(ed|ing)|"
    r"expulsion(s)?|filleting|forget|forgetting|forgotten|gone|"
    r"ignor(e|ed|ing)|invisible|lack(s|ing)?|los(e|es|ing|s|ses|t)|"
    r"mislaid|mislaying|miss(ed|ing)?|neglected|no|not|nothing|off|"
    r"omit(ted|ting)?|out|overlooked|prohibited|pruned|regardless|"
    r"reject(ed|ing)?|releas(e|es|ed)|remov(e|ed|ing)|rid|scrapped|shunned|"
    r"skip(ped|ping)?|trim|unavailable|vanquished|wanting|wiping|without"
    r")\b"
)


def parity_of(indicator: str) -> str | None:
    """Which letters of the fodder an alternation indicator leaves you with.

    Returns None for the many indicators that signal alternation without
    committing to a parity at all -- the whole "regularly" family, for
    instance, is used by setters for either.
    """
    named = None
    for label, pattern in PARITY_NAMES:
        if pattern.search(indicator):
            named = label
            break
    if named is None:
        return None
    if PARITY_DROP.search(indicator):
        return EVEN_PARITY if named == ODD_PARITY else ODD_PARITY
    return named


HIDDEN_PRECEDING_HIDES = "Preceding text hides upcoming"
HIDDEN_UPCOMING_HIDES = "Upcoming text hides preceding"
HIDDEN_OTHERWISE = "Otherwise"
HIDDEN_DIRECTION_ORDER = (
    HIDDEN_PRECEDING_HIDES,
    HIDDEN_UPCOMING_HIDES,
    HIDDEN_OTHERWISE,
)

# Relative "in which" family: the fodder comes first, then the indicator,
# then the definition (THE CARNIVAL in which BRAT).
_HIDDEN_WHICH_RE = re.compile(
    r"\b((with)?in|inside)\s+which\b|\bwherein\b|\bas setting for\b"
)

# The container/fodder is named after the indicator (BRAT in CELEBRATION).
_HIDDEN_FOLLOWING_FODDER_RE = re.compile(
    r"("
    r"\((in|into|inside|within|from|among|amongst|amid|amidst|of|by)\)|"
    r"\b("
    r"in|into|inside|within|from|among|amongst|amid|amidst|"
    r"through|throughout|during|of|by"
    r")\s*$"
    r")"
)
_HIDDEN_FOLLOWING_TO_RE = re.compile(
    r"\b("
    r"contribut(?:e|es|ing|ion)|belonging|belongs|"
    r"native|intrinsic|inherent|internal|"
    r"admitted|tucking|enclosure"
    r")\s+to\s*$"
    r"|\bto\s*$"
)

# Sits equally well on either side, or names extent rather than a container.
_HIDDEN_ADVERB_RE = re.compile(
    r"("
    r"\b("
    r"partly|partially|somewhat|essentially|secretly|"
    r"internally|fundamentally|intrinsically|inherently|"
    r"innately|heartily|slightly|mostly|centrally|"
    r"apparently|evidently|selectively"
    r")\b|"
    r"to some (extent|degree)|in some measure|^in part$|"
    r"not (all|entirely|completely|fully|totally|wholly)|"
    r"to an extent|to a certain extent|in essence"
    r")"
)

_HIDDEN_SANDWICH_RE = re.compile(
    r"\b(between|betwixt|either side|flanked|flanking|links between)\b"
)

# Transitive hiding/showing: fodder first (CELEBRATION conceals BRAT).
_HIDDEN_PRECEDING_VERB_RE = re.compile(
    r"\b("
    r"conceal(?:s|ing|ed|ment)?|hid(?:e|es|ing|den)|"
    r"cover(?:s|ing|ed)?|contain(?:s|ing|ed)?|"
    r"hold(?:s|ing)?|stor(?:e|es|ing|ed)|"
    r"veil(?:s|ing|ed)?|includ(?:e|es|ing|ed)|"
    r"hous(?:e|es|ing|ed)|harbour(?:s|ing|ed)?|harbor(?:s|ing|ed)?|"
    r"show(?:s|ing|n|ed)?|featur(?:e|es|ing|ed)|"
    r"display(?:s|ing|ed)?|exhibit(?:s|ing|ed|ion)?|"
    r"demonstrat(?:e|es|ing|ed)|"
    r"\bhas\b|have|having|had|"
    r"smuggl(?:e|es|ing|ed)|secret(?:e|es|ing|ed)|"
    r"enclos(?:e|es|ing|ed|ure)|camouflag(?:e|es|ing|ed)|"
    r"withhold(?:s|ing)?|furnish(?:es|ing|ed)?|"
    r"giv(?:e|es|ing|en)|provid(?:e|es|ing|ed|ing)|"
    r"eclips(?:e|es|ing|ed)|keep(?:s|ing)|kept|"
    r"carr(?:y|ies|ying|ied)|wrap(?:s|ping|ped)?|"
    r"bur(?:y|ies|ying|ied)|bag(?:s|ging|ged)?|box(?:es|ing|ed)?|"
    r"pocket(?:s|ing|ed)?|swallow(?:s|ing|ed)?|"
    r"trap(?:s|ping|ped)?|lock(?:s|ing|ed)?|"
    r"embrac(?:e|es|ing|ed)|surround(?:s|ing|ed)?|"
    r"mask(?:s|ing|ed)?|cloak(?:s|ing|ed)?|"
    r"obscur(?:e|es|ing|ed)|screen(?:s|ing|ed)?|"
    r"shelter(?:s|ing|ed)?|shield(?:s|ing|ed)?|"
    r"fram(?:e|es|ing|ed)|"
    r"offer(?:s|ing|ed)?|yield(?:s|ing|ed)?|"
    r"reveal(?:s|ing|ed)?|expos(?:e|es|ing|ed)|"
    r"bear(?:s|ing)|"
    r"pack(?:s|ing|ed)|stuff(?:s|ing|ed)|"
    r"nest(?:s|ing|ed|les|ling)|host(?:s|ing|ed)|"
    r"absorb(?:s|ing|ed)|accept(?:s|ing|ed)|"
    r"accommodat(?:e|es|ing|ed)|admit(?:s|ting|ted)|"
    r"arrest(?:s|ing|ed)|besieg(?:e|es|ing|ed)|"
    r"captur(?:e|es|ing|ed)|catch(?:es|ing)?|caught|"
    r"circl(?:e|es|ing|ed)|clasp(?:s|ing|ed)|"
    r"cloth(?:e|es|ing|ed)|clutch(?:es|ing|ed)|"
    r"consum(?:e|es|ing|ed)|"
    r"describ(?:e|es|ing|ed)|"
    r"disguis(?:e|es|ing|ed)|"
    r"eat(?:s|ing)|eaten|"
    r"encapsulat(?:e|es|ing|ed)|"
    r"engulf(?:s|ing|ed)|envelop(?:e|es|ing|ed|s)?|"
    r"fill(?:s|ing|ed)|grasp(?:s|ing|ed)|grip(?:s|ping|ped)|"
    r"guard(?:s|ing|ed)|hug(?:s|ging|ged)|"
    r"imprison(?:s|ing|ed)|incorporat(?:e|es|ing|ed)|"
    r"involv(?:e|es|ing|ed)|"
    r"jail(?:s|ing|ed)|"
    r"nurs(?:e|es|ing|ed)|"
    r"pen(?:s|ning|ned)|"
    r"possess(?:es|ing|ed)|"
    r"restrict(?:s|ing|ed)|retain(?:s|ing|ed)|"
    r"sandwich(?:es|ing|ed)?|"
    r"suppress(?:es|ing|ed)?|"
    r"wear(?:s|ing)|wore|worn|"
    r"welcom(?:e|es|ing|ed)|"
    r"aboard|around|about|round|"
    r"bracket(?:s|ing|ed)?|"
    r"cag(?:e|es|ing|ed)|"
    r"dwell(?:s|ing)|"
    r"hoard(?:s|ing|ed)|"
    r"immers(?:e|es|ing|ed)|"
    r"interrupt(?:s|ing|ed)?|"
    r"net(?:s|ting|ted)|"
    r"shroud(?:s|ing|ed)|"
    r"stock(?:s|ing|ed)|stow(?:s|ing|ed)|"
    r"wall(?:s|ing|ed)"
    r")\b"
)

_HIDDEN_UPCOMING_START_RE = re.compile(
    r"^(some|a bit|a little|a hint|a touch|a trace|just a bit|get some|"
    r"found|appearing|appears|seen|visible|buried|hidden|lurking|"
    r"characters|letters)\b"
)


def hiding_of(indicator: str) -> str:
    """Which side of a hidden-word indicator holds the consecutive letters.

    Preceding text hides upcoming: fodder, then indicator, then definition
    (CELEBRATION conceals BRAT). Upcoming text hides preceding: definition,
    then indicator, then fodder (BRAT in CELEBRATION). Otherwise covers
    sandwiching, extent adverbs, and indicators that do not fix a direction.
    """
    s = re.sub(r"\s+", " ", indicator.lower()).strip()
    if _HIDDEN_SANDWICH_RE.search(s):
        return HIDDEN_OTHERWISE
    if _HIDDEN_WHICH_RE.search(s):
        return HIDDEN_PRECEDING_HIDES
    if _HIDDEN_FOLLOWING_FODDER_RE.search(s) or _HIDDEN_FOLLOWING_TO_RE.search(s):
        return HIDDEN_UPCOMING_HIDES
    if _HIDDEN_ADVERB_RE.search(s):
        return HIDDEN_OTHERWISE
    if _HIDDEN_PRECEDING_VERB_RE.search(s):
        return HIDDEN_PRECEDING_HIDES
    if _HIDDEN_UPCOMING_START_RE.search(s):
        return HIDDEN_UPCOMING_HIDES
    return HIDDEN_OTHERWISE


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

# Containment list split: container (outer holds inner) vs insertion (inner enters outer).
OUTER_CONTAINS_INNER_CATS = frozenset(
    {
        "containment",
        "container",
        "list of 150 container indicators",
        "most common container indicators",
    }
)
INNER_ENTERS_OUTER_CATS = frozenset(
    {
        "insertion",
        "contents",
        "list of 57 contents indicators",
        "most common contents indicators",
    }
)

CONTAINMENT_SPLIT_SPECS = (
    {
        "slug": "outer-contains-inner",
        "title": "Outer contains inner indicators",
        "blurb": (
            "Container wordplay: the outer letter run holds the inner one "
            "(around, holding, contains, accepts, …)."
        ),
        "bucket": "outer",
    },
    {
        "slug": "inner-enters-outer",
        "title": "Inner enters outer indicators",
        "blurb": (
            "Insertion wordplay: the inner letter run goes into the outer one "
            "(in, into, enters, inside, …)."
        ),
        "bucket": "inner",
    },
)

_INNER_INDICATOR_RE = re.compile(
    r"(^|\s)("
    r"in(?:to|side|ward)?|within|enter(?:s|ing|ed)?|insert(?:s|ing|ed|ion)?|"
    r"penetrates?|penetrating|invades?|invading|tucked|nested|embedded|"
    r"secreted|smuggled|packed|pushed|placed|put|set|slotted|threaded|"
    r"interrupt(?:s|ing|ed)?|pierced|split(?:s|ting)?"
    r")(\s|$)|"
    r"\b(?:into|inside|within)\b|"
    r"\bin\b$|"
    r"^in\b"
)

_OUTER_INDICATOR_RE = re.compile(
    r"\b("
    r"about|around|round|holding?|holds|contain(?:s|ing|ed)?|surround(?:s|ing|ed)?|"
    r"embrac(?:e|es|ing|ed)|wrap(?:s|ping|ped)?|enclos(?:e|es|ing|ed)|"
    r"cover(?:s|ing|ed)?|harbour(?:s|ing|ed)?|possess(?:es|ing|ed)?|"
    r"accept(?:s|ing|ed)?|admit(?:s|ting|ted)?|capture(?:s|d|ing)?|"
    r"swallow(?:s|ing|ed)?|devour(?:s|ing|ed)?|bear(?:s|ing)?|carry(?:ing|ies)?|"
    r"clothe(?:s|d|ing)?|dress(?:es|ed|ing)?|box(?:es|ed|ing)?|cag(?:e|es|ed|ing)|"
    r"trap(?:s|ped|ping)?|board(?:s|ed|ing)?|aboard|accommodat(?:e|es|ing|ed)|"
    r"housing|houses|pocket(?:s|ed|ing)?|sheath(?:s|ed|ing)?|coil(?:s|ed|ing)?|"
    r"ring(?:s|ed|ing)?|band(?:s|ed|ing)?|border(?:s|ing|ed)?|bound(?:s|ing|ed)?|"
    r"bracket(?:s|ed|ing)?|sandwich(?:es|ed|ing)?|bookend(?:s|ed|ing)?|"
    r"split(?:s|ting)? by|outside|without|beyond"
    r")\b"
)


def containment_buckets(entry: dict) -> set[str]:
    """Classify a merged containment entry for the split offline lists."""
    cats = {c.lower() for c in entry.get("categories") or []}
    buckets: set[str] = set()
    if cats & OUTER_CONTAINS_INNER_CATS:
        buckets.add("outer")
    if cats & INNER_ENTERS_OUTER_CATS:
        buckets.add("inner")
    if buckets:
        return buckets

    ind = entry["indicator"].lower()
    inner = bool(_INNER_INDICATOR_RE.search(ind))
    outer = bool(_OUTER_INDICATOR_RE.search(ind))
    if inner and not outer:
        return {"inner"}
    if outer and not inner:
        return {"outer"}
    if inner and outer:
        return {"inner", "outer"}
    # Cryptipedia's juxtaposition page lands in the merged list but is not containment.
    if "cryptipedia" in entry.get("sources", ()) and "juxtaposition" in cats:
        return set()
    return {"outer"}


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
    ],
    "juxtaposition": ["List_of_juxtaposition_indicators"],
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
    clue_clinic_alt_index: int | None = 1
    clue_clinic_function_index: int | None = None


INDICATOR_TYPES: list[IndicatorType] = [
    IndicatorType(
        slug="anagram",
        title="Anagram indicators",
        blurb="Candidates for rearrangement — grammar and context decide.",
        georgeho_wordplays=["anagram"],
        clue_clinic_ids=[461],
        clue_clinic_alt_index=None,
        clue_clinic_function_index=1,
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
        blurb=(
            "Signal that consecutive letters of the answer lurk in the clue "
            "text. Grouped by which side of the indicator holds those letters."
        ),
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
        clue_clinic_ids=[7176],
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
        clue_clinic_ids=[419],
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
        clue_clinic_ids=[370],
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
    IndicatorType(
        slug="juxtaposition",
        title="Juxtaposition indicators",
        blurb=(
            "Charade / beside: one letter run is placed before or after another "
            "(after, beside, next to, following, …)."
        ),
        clue_clinic_ids=[1563],
        curated_extras=[
            "and", "with", "plus", "beside", "besides", "next to", "next door",
            "alongside", "adjacent", "adjacent to", "adjoining", "against",
            "before", "after", "behind", "ahead of", "in front of", "following",
            "followed by", "preceding", "preceded by", "then", "then comes",
            "meeting", "meets", "joining", "joined by", "together with",
            "facing", "beside that", "by", "on", "upon", "over", "under",
            "above", "below", "beneath", "atop",
        ],
    ),
    IndicatorType(
        slug="replacement",
        title="Replacement indicators",
        blurb=(
            "One letter run is swapped for another inside the fodder "
            "(replacing, instead of, giving way to, turning into, …)."
        ),
        clue_clinic_ids=[3440],
        clue_clinic_alt_index=2,
        curated_extras=[
            "replacing", "replaced by", "instead of", "in place of",
            "in favour of", "giving way to", "yielding to", "turning into",
            "changed to", "transformed into", "standing in for", "swapping",
            "exchanging", "substituting", "substituted for", "superseding",
            "supplanting",             "ousting", "taking over from", "taking the place of",
        ],
    ),
    IndicatorType(
        slug="movement",
        title="Letter-movement indicators",
        blurb=(
            "A letter or chunk is shifted inside the fodder: first-to-last, "
            "cyclic, promoted/demoted, tips swapped (head to tail, cycling, …)."
        ),
        allow_digits=True,
        curated_extras=[
            "head to tail", "first to last", "cycled", "cycling",
            "with parts swapped", "swapping tips", "tail first",
            "x becoming leader", "x taking lead",
        ],
    ),
]


# ClueClinic cryptic lexicon "Can Indicate" labels -> offline list.
# Pun is ClueClinic's label for speech/soundalike indicators (homophone).
LEXICON_KIND_MATCH: dict[str, tuple[str, ...]] = {
    "anagram": ("anagram",),
    "hidden": ("hidden",),
    "reversal": ("reversal",),
    "homophone": ("homophone", "pun"),
    "deletion": ("expulsion", "departure", "remove", "reduction"),
    "containment": ("containment", "insertion"),
    "letter-selection": ("select",),
    "alternation": (
        "select: regular",
        "select: odd",
        "select: even",
        "select: alternate",
    ),
    "juxtaposition": ("after", "before"),
    "replacement": ("replacement",),
    "movement": ("shift",),
}


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


def section_id(label: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", label.lower()).strip("-")
    return f"sec-{slug}" if slug else "sec"


def jump_nav(items: list[tuple[str, str, int]]) -> str:
    """Links to each section, for pages long enough to need scrolling."""
    if len(items) < 2:
        return ""
    links = "\n".join(
        f'<a href="#{anchor}">{html_lib.escape(label)} '
        f'<span class="n">({count})</span></a>'
        for anchor, label, count in items
    )
    return f'<nav id="jump" aria-label="Jump to section">\n{links}\n</nav>'


def _wordnet_parts_of_speech() -> dict[str, set[str]]:
    """Return WordNet parts of speech for single-word indicator inference."""
    path = ROOT / "exet-wordnet.js"
    if not path.is_file():
        return {}
    text = path.read_text(encoding="utf-8")
    marker = "const DATA = "
    start = text.find(marker)
    if start < 0:
        return {}
    data, _ = json.JSONDecoder().raw_decode(text, start + len(marker))
    synsets = data.get("s") or []
    result: dict[str, set[str]] = {}
    for lemma, indices in (data.get("i") or {}).items():
        key = norm(lemma.replace("_", " "))
        if " " in key:
            continue
        result[key] = {
            synsets[index][0]
            for index in indices
            if 0 <= index < len(synsets) and synsets[index]
        }
    return result


def infer_anagram_function(
    indicator: str, wordnet_pos: dict[str, set[str]]
) -> str:
    """Conservatively infer an anagram indicator's wordplay function."""
    words = re.findall(r"[a-z]+(?:'[a-z]+)?", indicator.lower())
    if not words:
        return "Context-dependent"

    first, last = words[0], words[-1]
    if last.endswith("ly") or first in {
        "about", "above", "across", "afresh", "again", "along", "around",
        "aside", "astray", "away", "back", "differently", "otherwise",
    }:
        return "Adverb"
    if first in {
        "at", "by", "for", "in", "into", "off", "on", "out", "over",
        "through", "under", "with", "without",
    }:
        return "Adverb"
    if first in {"a", "an", "the"}:
        return "Noun expression"

    # In phrasal verbs the inflected first word determines the function.
    verb_word = first if len(words) > 1 else last
    if verb_word.endswith("ing"):
        return "Present participle"
    if (
        verb_word.endswith(("ed", "en"))
        or verb_word in IRREGULAR_PAST_PARTICIPLES
    ):
        return "Past participle"
    if len(words) > 1 and last == "of":
        return "Noun expression"
    if verb_word.endswith("s") and "v" in wordnet_pos.get(
        verb_word.removesuffix("s"), set()
    ):
        return "Verb indicative"

    pos = wordnet_pos.get(verb_word, set())
    if pos and pos <= {"a", "s"}:
        return "Adjective"
    if pos == {"r"}:
        return "Adverb"
    if "v" in pos:
        return "Verb imperative"
    if pos == {"n"}:
        return "Noun expression"

    # A final adjective often makes the whole multi-word indicator adjectival.
    last_pos = wordnet_pos.get(last, set())
    if len(words) > 1 and last_pos and last_pos <= {"a", "s"}:
        return "Adjective"
    return "Context-dependent"


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
        {
            "indicator": indicator,
            "sources": set(),
            "categories": set(),
            "notes": set(),
            "function": None,
            "function_inferred": False,
        },
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


def _clue_clinic_table_rows(html: str) -> list[list[str]]:
    """TablePress (classed tds) or plain HTML tables from ClueClinic pages."""
    rows: list[list[str]] = []
    for row_html in re.findall(r"<tr class=\"row-[^\"]*\">(.*?)</tr>", html, re.S):
        cells = re.findall(r'<td class="column-\d+">([^<]*)</td>', row_html)
        if cells:
            rows.append([html_lib.unescape(c).strip() for c in cells])
    if rows:
        return rows
    for row_html in re.findall(r"<tr>(.*?)</tr>", html, re.S | re.I):
        if re.search(r"<th\b", row_html, re.I):
            continue
        cells = []
        for cell in re.findall(r"<td[^>]*>(.*?)</td>", row_html, re.S | re.I):
            plain = re.sub(r"<[^>]+>", " ", cell)
            cells.append(html_lib.unescape(re.sub(r"\s+", " ", plain)).strip())
        if cells:
            rows.append(cells)
    return rows


def scrape_clue_clinic(
    store: dict[str, dict],
    page_ids: list[int],
    *,
    allow_digits: bool = False,
    default_category: str | None = None,
    alt_index: int | None = 1,
    function_index: int | None = None,
) -> int:
    count = 0
    note_tokens = {
        "standard", "advanced", "before", "after", "either", "across", "down",
    }
    for page_id in page_ids:
        url = f"https://clueclinic.com/index.php/wp-json/wp/v2/pages/{page_id}"
        html = json.loads(fetch(url))["content"]["rendered"]
        cache = SOURCES_DIR / f"clueclinic-{page_id}.html"
        cache.parent.mkdir(parents=True, exist_ok=True)
        cache.write_text(html, encoding="utf-8")

        for cells in _clue_clinic_table_rows(html):
            if not cells or cells[0].strip().lower() in {
                "indicator", "word", "clue word",
            }:
                continue
            primary = cells[0].strip()
            category = default_category
            for cell in cells[2:]:
                c = cell.strip()
                if c and c not in {"Standard", "Advanced"} and not c.startswith("V*"):
                    if any(
                        k in c.lower()
                        for k in (
                            "reduction", "departure", "insertion", "containment",
                            "selection", "behead", "curtail", "hidden", "reversal",
                            "homophone", "alternat", "juxtapos",
                        )
                    ):
                        category = c.lower()
                        break
            notes = [
                c.strip().lower()
                for c in cells[2:]
                if c.strip().lower() in note_tokens
            ]
            if add_entry(
                store, primary, "clue-clinic", category=category, allow_digits=allow_digits
            ):
                count += 1
            key = norm(primary)
            if key in store:
                store[key]["notes"].update(notes)
                if (
                    function_index is not None
                    and len(cells) > function_index
                    and cells[function_index].strip() in ANAGRAM_FUNCTIONS
                ):
                    store[key]["function"] = cells[function_index].strip()
                    store[key]["function_inferred"] = False
                if (
                    alt_index is not None
                    and alt_index >= 2
                    and len(cells) > 1
                    and cells[1].strip()
                ):
                    store[key]["notes"].add(cells[1].strip().lower())
            if alt_index is not None and len(cells) > alt_index:
                for alt in split_alternatives(cells[alt_index]):
                    if add_entry(
                        store,
                        alt,
                        "clue-clinic",
                        category=category,
                        note="alternative",
                        allow_digits=allow_digits,
                    ):
                        count += 1
                    alt_key = norm(alt)
                    if alt_key in store:
                        store[alt_key]["notes"].update(notes)
    return count


def scrape_clue_clinic_whimsical_anagrams(store: dict[str, dict]) -> int:
    """Keep only rows explicitly labelled Anagram on the whimsical page."""
    url = "https://clueclinic.com/index.php/wp-json/wp/v2/pages/3503"
    html = json.loads(fetch(url))["content"]["rendered"]
    count = 0
    for cells in _clue_clinic_table_rows(html):
        if len(cells) < 2 or cells[1].strip().lower() != "anagram":
            continue
        if add_entry(store, cells[0], "clue-clinic"):
            count += 1
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
        category = wordplay.lower()
        for ind in sorted(all_rows):
            if add_entry(store, ind, "cryptics-georgeho", category=category):
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
            if add_entry(
                store,
                ind,
                "cryptipedia",
                category=page.replace("List_of_", "").replace("_", " ").lower(),
                allow_digits=allow_digits,
            ):
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


def _lexicon_kind_hits(kind: str, prefixes: tuple[str, ...]) -> bool:
    k = re.sub(r"\s+", " ", kind.strip().lower())
    for p in prefixes:
        if k == p or k.startswith(p + ":") or k.startswith(p + " :"):
            return True
        if k.startswith(p + " ") or k.startswith(p + "("):
            return True
    return False


def load_cryptic_lexicon_rows() -> list[tuple[str, str, str]]:
    cache = SOURCES_DIR / "clueclinic-4538-lexicon.html"
    if cache.is_file():
        html = cache.read_text(encoding="utf-8")
    else:
        url = "https://clueclinic.com/index.php/wp-json/wp/v2/pages/4538"
        html = json.loads(fetch(url))["content"]["rendered"]
        cache.parent.mkdir(parents=True, exist_ok=True)
        cache.write_text(html, encoding="utf-8")
    rows: list[tuple[str, str, str]] = []
    for row_html in re.findall(r'<tr class="row-[^"]*">(.*?)</tr>', html, re.S):
        cells = re.findall(r'<td class="column-\d+">([^<]*)</td>', row_html)
        if not cells or cells[0].strip().lower() == "text":
            continue
        text = html_lib.unescape(cells[0]).strip()
        represent = html_lib.unescape(cells[1]).strip() if len(cells) > 1 else ""
        indicate = html_lib.unescape(cells[2]).strip() if len(cells) > 2 else ""
        rows.append((text, represent, indicate))
    return rows


def scrape_cryptic_lexicon(
    store: dict[str, dict],
    prefixes: tuple[str, ...],
    *,
    allow_digits: bool = False,
) -> int:
    count = 0
    for text, _represent, indicate in load_cryptic_lexicon_rows():
        if not indicate:
            continue
        kinds = [k.strip() for k in re.split(r"\s*,\s*", indicate) if k.strip()]
        matched = [k for k in kinds if _lexicon_kind_hits(k, prefixes)]
        if not matched:
            continue
        category = matched[0].lower()
        if add_entry(
            store,
            text,
            "clue-clinic-lexicon",
            category=category,
            allow_digits=allow_digits,
        ):
            count += 1
    return count


def build_type(cfg: IndicatorType) -> dict[str, dict]:
    store: dict[str, dict] = {}
    steps: list[tuple[str, callable]] = []
    previous_entries: list[dict] = []
    previous_path = OUT_DIR / f"{cfg.slug}-indicators.json"
    if previous_path.is_file():
        try:
            previous_entries = json.loads(
                previous_path.read_text(encoding="utf-8")
            ).get("entries", [])
        except (OSError, ValueError):
            pass

    if cfg.clue_clinic_ids:
        steps.append(
            (
                "clue-clinic",
                lambda s: scrape_clue_clinic(
                    s,
                    cfg.clue_clinic_ids,
                    allow_digits=cfg.allow_digits,
                    default_category=cfg.slug,
                    alt_index=cfg.clue_clinic_alt_index,
                    function_index=cfg.clue_clinic_function_index,
                ),
            )
        )
    if cfg.slug == "anagram":
        steps.append(
            ("clue-clinic-whimsical", scrape_clue_clinic_whimsical_anagrams)
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
    prefixes = LEXICON_KIND_MATCH.get(cfg.slug)
    if prefixes:
        steps.append(
            (
                "clue-clinic-lexicon",
                lambda s, p=prefixes: scrape_cryptic_lexicon(
                    s, p, allow_digits=cfg.allow_digits
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
            restored = 0
            # Fandom regularly blocks automated requests. Keep its committed
            # entries rather than silently shrinking the list on every build.
            if name == "cryptipedia":
                for old in previous_entries:
                    if name not in (old.get("sources") or []):
                        continue
                    if add_entry(
                        store,
                        old["indicator"],
                        name,
                        allow_digits=cfg.allow_digits,
                    ):
                        restored += 1
                    key = norm(old["indicator"])
                    if key in store and old.get("function"):
                        store[key]["function"] = old["function"]
                        store[key]["function_inferred"] = bool(
                            old.get("function_inferred")
                        )
            suffix = f"; restored {restored} prior entries" if restored else ""
            print(f"  {name}: FAIL — {exc}{suffix}", flush=True)
    return store


def write_outputs(
    cfg: IndicatorType, store: dict[str, dict], built: str | None = None
) -> tuple[int, list[tuple[str, int]]]:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    base = f"{cfg.slug}-indicators"
    ordered = sorted(store.values(), key=lambda e: e["indicator"])
    wordnet_pos = _wordnet_parts_of_speech() if cfg.slug == "anagram" else {}

    serializable = []
    for e in ordered:
        function = e.get("function")
        function_inferred = bool(e.get("function_inferred"))
        if cfg.slug == "anagram" and not function:
            function = infer_anagram_function(e["indicator"], wordnet_pos)
            function_inferred = True
        item = {
            "indicator": e["indicator"],
            "sources": sorted(e["sources"]),
            "categories": (
                [] if cfg.slug == "anagram" else sorted(e["categories"])
            ),
            "notes": sorted(e["notes"]),
        }
        if cfg.slug == "anagram":
            item["function"] = function
            item["function_inferred"] = function_inferred
        if cfg.slug == "alternation":
            item["parity"] = parity_of(e["indicator"])
        if cfg.slug == "hidden":
            item["hiding"] = hiding_of(e["indicator"])
        serializable.append(item)

    meta = {
        "type": cfg.slug,
        "title": cfg.title,
        "built": built or date.today().isoformat(),
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
    if cfg.slug == "anagram":
        for e in serializable:
            by_cat[e["function"]].append(e)
    elif cfg.slug != "hidden":
        for e in serializable:
            if e["categories"]:
                for cat in e["categories"]:
                    by_cat[cat].append(e)

    by_parity: dict[str, list[dict]] = defaultdict(list)
    for e in serializable:
        if e.get("parity"):
            by_parity[e["parity"]].append(e)

    by_hiding: dict[str, list[dict]] = defaultdict(list)
    for e in serializable:
        if e.get("hiding"):
            by_hiding[e["hiding"]].append(e)

    (OUT_DIR / f"{base}.html").write_text(
        render_html(cfg, meta, by_cat, by_parity, by_hiding), encoding="utf-8"
    )
    if cfg.slug == "containment":
        split_summary = write_containment_splits(store, built=built or meta["built"])
    else:
        split_summary = []
    return len(serializable), split_summary


def write_containment_splits(
    store: dict[str, dict], *, built: str
) -> list[tuple[str, int]]:
    """Offline lists for container vs insertion wordplay (subset of merged containment)."""
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    ordered = sorted(store.values(), key=lambda e: e["indicator"])
    summary: list[tuple[str, int]] = []

    for spec in CONTAINMENT_SPLIT_SPECS:
        bucket = spec["bucket"]
        picked = [e for e in ordered if bucket in containment_buckets(e)]
        serializable = []
        for e in picked:
            serializable.append(
                {
                    "indicator": e["indicator"],
                    "sources": sorted(e["sources"]),
                    "categories": sorted(e["categories"]),
                    "notes": sorted(e["notes"]),
                }
            )

        split_cfg = IndicatorType(
            slug=spec["slug"],
            title=spec["title"],
            blurb=spec["blurb"],
        )
        base = f"{spec['slug']}-indicators"
        meta = {
            "type": spec["slug"],
            "title": spec["title"],
            "built": built,
            "count": len(serializable),
            "sources": sorted({s for e in serializable for s in e["sources"]}),
            "entries": serializable,
        }
        (OUT_DIR / f"{base}.json").write_text(
            json.dumps(meta, indent=2, ensure_ascii=False), encoding="utf-8"
        )
        (OUT_DIR / f"{base}.txt").write_text(
            "\n".join(e["indicator"] for e in serializable) + "\n",
            encoding="utf-8",
        )

        by_cat: dict[str, list[dict]] = defaultdict(list)
        for e in serializable:
            if e["categories"]:
                for cat in e["categories"]:
                    by_cat[cat].append(e)

        (OUT_DIR / f"{base}.html").write_text(
            render_html(split_cfg, meta, by_cat, {}, {}), encoding="utf-8"
        )
        summary.append((spec["slug"], len(serializable)))

    return summary


def render_html(
    cfg: IndicatorType,
    meta: dict,
    by_cat: dict[str, list[dict]],
    by_parity: dict[str, list[dict]],
    by_hiding: dict[str, list[dict]],
) -> str:
    count = meta["count"]
    sources = ", ".join(meta["sources"])

    def chip(entry: dict) -> str:
        src = html_lib.escape(", ".join(entry["sources"]))
        function = entry.get("function")
        inferred = " (inferred)" if entry.get("function_inferred") else ""
        function_title = (
            f"; Function: {html_lib.escape(function)}{inferred}" if function else ""
        )
        return (
            f'<span class="ind" title="Sources: {src}{function_title}">'
            f"{html_lib.escape(entry['indicator'])}</span>"
        )

    nav_items: list[tuple[str, str, int]] = []
    used_ids: set[str] = set()

    def unique_section_id(label: str) -> str:
        """Near-duplicate category labels must still get their own anchor."""
        base = section_id(label)
        anchor = base
        suffix = 2
        while anchor in used_ids:
            anchor = f"{base}-{suffix}"
            suffix += 1
        used_ids.add(anchor)
        return anchor

    parity_sections = []
    for label in (ODD_PARITY, EVEN_PARITY):
        items = sorted(by_parity.get(label, []), key=lambda e: e["indicator"])
        if not items:
            continue
        anchor = unique_section_id(label)
        nav_items.append((anchor, label.title(), len(items)))
        chips = "\n".join(chip(e) for e in items)
        parity_sections.append(
            f'<section class="cat" id="{anchor}">'
            f'<h2>{html_lib.escape(label.title())} '
            f'<span class="n">({len(items)})</span></h2>'
            f'<div class="grid">\n{chips}\n</div></section>'
        )
    parity_block = ""
    if parity_sections:
        parity_block = (
            '<div id="parity">'
            '<p class="note">Grouped by the letters you are left holding. An '
            "indicator that names one parity in order to discard it, such as "
            "&ldquo;oddly dropped&rdquo;, therefore sits under the other. "
            "Indicators that signal alternation without fixing a parity, such "
            "as the &ldquo;regularly&rdquo; family, are listed only under "
            "<em>All indicators</em>.</p>"
            f'{"".join(parity_sections)}</div>'
        )

    hiding_sections = []
    for label in HIDDEN_DIRECTION_ORDER:
        items = sorted(by_hiding.get(label, []), key=lambda e: e["indicator"])
        if not items:
            continue
        anchor = unique_section_id(label)
        nav_items.append((anchor, label, len(items)))
        chips = "\n".join(chip(e) for e in items)
        hiding_sections.append(
            f'<section class="cat" id="{anchor}">'
            f'<h2>{html_lib.escape(label)} '
            f'<span class="n">({len(items)})</span></h2>'
            f'<div class="grid">\n{chips}\n</div></section>'
        )
    hiding_block = ""
    if hiding_sections:
        hiding_block = (
            '<div id="hiding">'
            '<p class="note">Grouped by how the consecutive letters are hidden. '
            "<em>Preceding text hides upcoming</em> when the fodder comes first "
            "(conceals, holds, covers, &hellip;). "
            "<em>Upcoming text hides preceding</em> when the fodder follows "
            "(in, from, part of, &hellip;). "
            "Adverbs of extent, sandwiching, and indicators that do not fix a "
            "direction sit under <em>Otherwise</em>.</p>"
            f'{"".join(hiding_sections)}</div>'
        )

    cat_sections = []
    category_order = (
        ANAGRAM_FUNCTIONS if cfg.slug == "anagram" else sorted(by_cat)
    )
    for cat in category_order:
        items = sorted(by_cat[cat], key=lambda e: e["indicator"])
        anchor = unique_section_id(cat)
        nav_items.append((anchor, cat.title(), len(items)))
        chips = "\n".join(chip(e) for e in items)
        cat_sections.append(
            f'<section class="cat" id="{anchor}">'
            f'<h2>{html_lib.escape(cat.title())} '
            f'<span class="n">({len(items)})</span></h2>'
            f'<div class="grid">\n{chips}\n</div></section>'
        )

    all_chips = "\n".join(chip(e) for e in meta["entries"])
    category_note = ""
    all_block = (
        '<section id="all">'
        f'<h2>All indicators <span class="n">({count})</span></h2>'
        f'<div class="grid" id="grid">\n{all_chips}\n</div></section>'
    )
    if cfg.slug == "anagram":
        exact = sum(not e.get("function_inferred") for e in meta["entries"])
        category_note = (
            '<p class="note">Grouped by grammatical function in the wordplay. '
            f'{exact} functions come from ClueClinic; the remainder are '
            'conservative grammatical inferences. Hover over an indicator to '
            'see whether its function was inferred.</p>'
        )
        # Each indicator already occurs once in a function section.
        all_block = ""
    if cfg.slug == "hidden":
        # Each indicator already occurs once in a hiding-direction section.
        all_block = ""
    if all_block:
        nav_items.append(("all", "All indicators", count))
    nav_block = jump_nav(nav_items)
    main_blocks = "\n".join(
        block
        for block in (
            parity_block,
            hiding_block,
            category_note,
            "".join(cat_sections),
            all_block,
        )
        if block
    )

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
  #jump {{ padding: 8px 16px; background: #fff; border-bottom: 1px solid var(--border);
           display: flex; flex-wrap: wrap; gap: 4px 14px; font-size: 0.85rem; }}
  #jump a {{ color: var(--accent); text-decoration: none; }}
  #jump a:hover {{ text-decoration: underline; }}
  #jump a.hide {{ display: none; }}
  #jump .n {{ color: var(--muted); }}
  main {{ padding: 12px 16px 32px; }}
  /* Clear the sticky toolbar when jumping to a section. */
  .cat, #all {{ scroll-margin-top: 64px; }}
  .cat h2 {{ font-size: 1rem; margin: 20px 0 8px; color: var(--accent); }}
  .cat .n {{ color: var(--muted); font-weight: normal; }}
  .note {{ margin: 0 0 4px; color: var(--muted); font-size: 0.85rem; max-width: 68ch; }}
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
{nav_block}
<div id="toolbar">
  <input type="search" id="q" placeholder="Filter indicators…" autofocus>
  <span id="stats">{count} shown</span>
</div>
<main>
{main_blocks}
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
    const parity = document.getElementById('parity');
    if (parity) {{
      parity.style.display =
          parity.querySelectorAll('.ind:not(.hide)').length ? '' : 'none';
    }}
    const hiding = document.getElementById('hiding');
    if (hiding) {{
      hiding.style.display =
          hiding.querySelectorAll('.ind:not(.hide)').length ? '' : 'none';
    }}
    for (const link of document.querySelectorAll('#jump a')) {{
      const target = document.getElementById(link.hash.slice(1));
      link.classList.toggle('hide', !!target && target.style.display === 'none');
    }}
  }}
  q.addEventListener('input', apply);
  apply();
}})();
</script>
</body>
</html>
"""


def load_store(cfg: IndicatorType) -> tuple[dict[str, dict], str]:
    """Reload a previous build so outputs can be re-rendered without scraping.

    Presentation changes should not have to hit the upstream sites again, nor
    silently churn the entry set while doing it.
    """
    data = json.loads(
        (OUT_DIR / f"{cfg.slug}-indicators.json").read_text(encoding="utf-8")
    )
    store = {
        e["indicator"]: {
            "indicator": e["indicator"],
            "sources": set(e["sources"]),
            "categories": set(e.get("categories") or []),
            "notes": set(e.get("notes") or []),
            "function": e.get("function"),
            "function_inferred": bool(e.get("function_inferred")),
        }
        for e in data["entries"]
    }
    return store, data["built"]


def main(argv: list[str]) -> int:
    args = argv[1:]
    from_json = "--from-json" in args
    wanted = {a.lower() for a in args if not a.startswith("-")}
    types = INDICATOR_TYPES
    if wanted:
        types = [t for t in INDICATOR_TYPES if t.slug in wanted]
        if not types:
            print(f"Unknown type(s): {', '.join(sorted(wanted))}", file=sys.stderr)
            print("Known:", ", ".join(t.slug for t in INDICATOR_TYPES), file=sys.stderr)
            return 1

    summary: list[tuple[str, int]] = []
    for cfg in types:
        if from_json and (OUT_DIR / f"{cfg.slug}-indicators.json").is_file():
            store, built = load_store(cfg)
            prefixes = LEXICON_KIND_MATCH.get(cfg.slug)
            if prefixes:
                print(f"\n=== {cfg.title} ({cfg.slug}) [from-json + lexicon] ===", flush=True)
                n = scrape_cryptic_lexicon(
                    store, prefixes, allow_digits=cfg.allow_digits
                )
                print(f"  clue-clinic-lexicon: +{n} new ({len(store)} unique)", flush=True)
        else:
            store, built = build_type(cfg), None
        n, splits = write_outputs(cfg, store, built=built)
        summary.append((cfg.slug, n))
        summary.extend(splits)

    print("\n--- Summary ---", flush=True)
    for slug, n in summary:
        print(f"  {slug}: {n} indicators -> lists/{slug}-indicators.html", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
