# Exet SQLite data backend

Serves Exet’s large datasets (lexicons, prior clues, WordNet) from a single
SQLite database instead of multi‑megabyte JavaScript bundles.

The backend lives at `exet/backend/` (same repo as the app).

## Setup

```powershell
cd path\to\exet
python -m venv backend\.venv
backend\.venv\Scripts\pip install -r backend\requirements.txt
```

## Build the database

From the **exet** repo root:

```powershell
# Everything (all wordlists in wordlists/*.txt, prior clues, WordNet)
backend\.venv\Scripts\python backend\build\build_all.py

# One lexicon only (faster)
backend\.venv\Scripts\python backend\build\build_all.py --only-lexicon combolist --skip-prior-clues --skip-wordnet
```

**Prior clues** need source data:

```powershell
python tools\fetch-prior-clues-data.py
```

**WordNet** needs `exet-wordnet.js` (built via `tools/build-exet-wordnet.py`
if missing).

Output: `backend/data/exet.sqlite` (gitignored; often 1+ GB with ComboList +
prior clues).

## Run the server

```powershell
.\backend\start_server.ps1
```

Or on Git Bash / WSL:

```bash
./backend/start_server.sh
```

Manual start:

```powershell
backend\.venv\Scripts\python -m uvicorn backend.main:app --reload --host 127.0.0.1 --port 8000
```

## API (read-only)

| Endpoint | Description |
|----------|-------------|
| `GET /health` | DB path and row counts |
| `GET /api/datasets` | Lexicon list + build stats |
| `GET /api/lexicons` | Lexicon catalog |
| `GET /api/lexicons/{slug}/fill?pattern=???A?&limit=200` | Grid-fill candidates |
| `GET /api/lexicons/{slug}/anagrams?q=created&limit=200` | Anagram lookup |
| `GET /api/prior-clues/{answer}` | Published clues for an answer |
| `GET /api/prior-clues/stats` | Prior-clues build metadata |
| `GET /api/synonyms?word=piano` | WordNet synsets |

`{slug}` is the lexicon slug (e.g. `combolist`, `ettulist`) or full id
(e.g. `ComboList-imported`).

### Examples

```text
http://127.0.0.1:8000/api/lexicons/combolist/fill?pattern=CREATED&limit=10
http://127.0.0.1:8000/api/prior-clues/PIANO
http://127.0.0.1:8000/api/synonyms?word=share
```

## Schema

- **lexicons** / **lexicon_entries** / **lexicon_pattern** — word lists with
  Exet-compatible pattern index (same algorithm as `tools/import-wordlists.py`)
- **prior_clues** — answer → clue rows with metadata
- **wordnet_synsets** / **wordnet_lemma_index** — synonym lookup

## Frontend integration

When Exet is served from this backend (`http://127.0.0.1:8000/`), `exet-data-server.js`
probes `/health` and automatically:

- **Prior clues** — fetches `/api/prior-clues/{answer}` (no JS shards)
- **Synonyms (WordNet)** — fetches `/api/synonyms?word=…` (no `exet-wordnet.js` download)
- **Lexicons** — any word list present in SQLite loads instantly; fill/anagram
  lookups go to `/api/lexicons/{slug}/…` instead of downloading `*-part-*.js`

Lexicons not in the database (e.g. Lufz/Nediger if not built) still load from JS files.
Without the backend, WordNet falls back to lazy-loading `exet-wordnet.js`; prior clues
show a message to start the server.

Set `exetConfig.dataServer = false` in `exet.html` to disable API mode.

## Not included yet

- Autofill / theme LLM / cloud storage
- Auth

Build logic lives under `backend/build/`; lookup mirrors `exet-lexicon.js` and
`exet-prior-clues.js` behaviour.
