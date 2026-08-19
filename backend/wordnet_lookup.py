"""WordNet synonym lookup — mirrors exet-wordnet.js."""

from __future__ import annotations

import json
import re
import sqlite3

POS_LABEL = {"n": "noun", "v": "verb", "a": "adj", "r": "adv"}


def normalize(word: str) -> str:
    if not word:
        return ""
    return (
        str(word)
        .lower()
        .replace("\u2019", "'")
        .replace("'", "'")
        .replace("_", " ")
        .replace("\u2013", " ")
        .replace("\u2014", " ")
    )


def candidates(word: str) -> list[str]:
    w = re.sub(r"\s+", " ", normalize(word)).strip()
    if not w:
        return []
    out = [w]
    add = lambda x: out.append(x) if x and x != w and x not in out else None
    add(w.rstrip(".!?"))
    if w.endswith("ies") and len(w) > 4:
        add(w[:-3] + "y")
    if w.endswith("es") and len(w) > 3:
        add(w[:-2])
    if w.endswith("s") and not w.endswith("ss") and len(w) > 2:
        add(w[:-1])
    if w.endswith("ied") and len(w) > 4:
        add(w[:-3] + "y")
    if w.endswith("ed") and len(w) > 3:
        add(w[:-2])
        add(w[:-1])
    if w.endswith("ing") and len(w) > 4:
        add(w[:-3])
        add(w[:-3] + "e")
    if w.endswith("iest") and len(w) > 5:
        add(w[:-4] + "y")
    if w.endswith("er") and len(w) > 3:
        add(w[:-2])
    if w.endswith("est") and len(w) > 4:
        add(w[:-3])
    if w.endswith("ly") and len(w) > 3:
        add(w[:-2])
    return out


def lookup_synonyms(conn: sqlite3.Connection, word: str) -> list[dict]:
    if "?" in (word or ""):
        return []
    for key in candidates(word):
        row = conn.execute(
            "SELECT synset_ids_json FROM wordnet_lemma_index WHERE lemma = ?",
            (key,),
        ).fetchone()
        if not row:
            continue
        synset_ids = json.loads(row["synset_ids_json"])
        results = []
        seen: set[int] = set()
        for si in synset_ids:
            if si in seen:
                continue
            seen.add(si)
            syn = conn.execute(
                "SELECT pos, lemmas_json, gloss FROM wordnet_synsets WHERE id = ?",
                (si,),
            ).fetchone()
            if not syn:
                continue
            lemmas = json.loads(syn["lemmas_json"])
            pos = syn["pos"]
            gloss = syn["gloss"]
            synonyms = [lm for lm in lemmas if lm != key]
            results.append(
                {
                    "lemma": key,
                    "pos": pos,
                    "posLabel": POS_LABEL.get(pos, pos),
                    "synonyms": synonyms,
                    "gloss": gloss,
                    "synsetWords": lemmas[:],
                }
            )
        return results
    return []
