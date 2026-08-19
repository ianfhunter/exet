# Prior clues (SQLite backend)

Exet tab **Prior clues** shows published crossword clues for the current
answer via the SQLite backend (`/api/prior-clues/{answer}`).

## Setup

1. Download source data (~250 MB total):

   ```bash
   python tools/fetch-prior-clues-data.py
   ```

   This fetches into:
   - `wordlists/_sources/georgeho-data.db` — cryptics.georgeho.org (~187 MB)
   - `wordlists/xd-clues.zip` — xd.saul.pw clue corpus (~67 MB)

2. Build the SQLite database (includes prior clues):

   ```powershell
   backend\.venv\Scripts\python backend\build\build_all.py --skip-lexicon --skip-wordnet
   ```

   Or build everything:

   ```powershell
   backend\.venv\Scripts\python backend\build\build_all.py
   ```

3. Run Exet via the backend:

   ```powershell
   .\backend\start_server.ps1
   ```

   Open `http://127.0.0.1:8000/`.

## Legacy JS index (optional)

`tools/build-prior-clues-index.py` can still emit sharded JS for offline
static hosting, but the repo no longer commits those files. Use the SQLite
backend instead.

Options for the legacy builder:

- `--max-per-answer N` — optional cap (default: **0** = all unique clues per answer)

## Attributions

- Cryptic clues: [cryptics.georgeho.org](https://cryptics.georgeho.org/) (ODbL v1.0)
- xd clues: [xd.saul.pw](https://xd.saul.pw/data)

## Implementation

- Tab config: `exet.html` → `exetConfig.extraTabs` → `prior-clues`
- UI: `exet.js` → `updatePriorClues`, `renderPriorCluesFromApi`
- Build: `backend/build/prior_clues.py`
- API: `GET /api/prior-clues/{answer}`
