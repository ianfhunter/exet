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

Notes:

- `.txt` is preferred over `.dict` when both share a stem.
- Archives (`.zip`, etc.) are ignored.
- Entries with non-letters (digits, `$`, …) are skipped, matching Lufz.
- English lists get identity stems (no Porter stemming / region swaps).
- Phones are empty unless you extend the importer later.
