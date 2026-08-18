# Prior clues (offline lookup)

Exet tab **Prior clues** shows published crossword clues for the current
answer from a local index (`exet-prior-clues.js`).

## Quick start (sample)

The repo includes a small sample index (answers `CREATED`, `PIANO`, `SHARE`).
Open Exet, fill a light, click **Prior clues**.

## Full index

1. Download source data (~250 MB total):

   ```bash
   python tools/fetch-prior-clues-data.py
   ```

   This fetches into:
   - `wordlists/_sources/georgeho-data.db` — cryptics.georgeho.org (~187 MB)
   - `wordlists/xd-clues.zip` — xd.saul.pw clue corpus (~67 MB)

2. Build the lookup file:

   ```bash
   python tools/build-prior-clues-index.py
   ```

   Writes sharded data under wordlists/built/ and
   wordlists/built/prior-clues-manifest.js. The small core loader is
   exet-prior-clues.js (committed separately).

Options:

- `--max-per-answer N` — optional cap (default: **0** = all unique clues per answer)
- `--out path/to/exet-prior-clues.js`

## Attributions

- Cryptic clues: [cryptics.georgeho.org](https://cryptics.georgeho.org/) (ODbL v1.0)
- xd clues: [xd.saul.pw](https://xd.saul.pw/data)

## Implementation

- Tab config: `exet.html` → `exetConfig.extraTabs` → `prior-clues`
- UI: `exet.js` → `updatePriorClues`, `renderPriorClues`
- Index builder: `tools/build-prior-clues-index.py`
- Lazy-loaded script: `exet-prior-clues.js` (same pattern as WordNet)
