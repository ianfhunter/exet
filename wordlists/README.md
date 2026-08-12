# Wordlists

Drop crossword word-list files here, then rebuild:

```bash
python tools/import-wordlists.py
```

Supported line formats:

- `word;score`
- `word::score`
- `score<TAB>word`
- `word` (unscored)

The importer writes Exet lexicon JS under `built/` and updates
`built/lexicons-manifest.js`, which `exet.html` loads so the new lists
appear in the Word list menu.

## ComboList

To build / refresh the merged list:

```bash
python tools/extract-exet-lexicons.py      # Nediger + Lufz -> _sources/
python tools/fetch-extra-wordlists.py      # Broda / ECND / queer (best-effort)
python tools/fetch-recommended-packs.py    # nzfeng / geo / maiamcc packs
python tools/build-million-union.py        # merge + xd-clues frequency boost
python tools/import-wordlists.py --only combolist
```

Sources (when present under `wordlists/` / `_sources/`):

- Nediger List, Lufz English
- Crossword Nexus collaborative list (MIT)
- Peter Broda wordlist
- Spread the Wordlist, Matt’s list (CC BY-NC-SA), Chris Jones, Ettu
- nzfeng curated core / contemporary / idioms
- Expanded Crossword Name Database, maiamcc specialty dicts (queer, celebs, …)
- Geo packs (cities, countries, states, job titles, website phrases)
- UKACD18plus
- English OpenList (MIT), dwyl `words_alpha`
- Frequency boost / inserts from `xd-clues.zip`

No letter-length crop (jumbo / 21+ entries kept).

Score policy: crossword lists keep native scores (max on overlap);
xd published-answer frequency adds a small boost; OpenList defaults to 15;
general dict pad defaults to 5.

Notes:

- `.txt` is preferred over `.dict` when both share a stem.
- Archives (`.zip`, etc.) are ignored by the generic importer; `_sources/` is not auto-imported.
- Entries with non-letters (digits, `$`, …) are skipped, matching Lufz.
- English lists get identity stems (no Porter stemming / region swaps).
- Phones are empty unless you extend the importer later.
- The ComboList built JS is large (often 100MB+); fine for self-hosting.
