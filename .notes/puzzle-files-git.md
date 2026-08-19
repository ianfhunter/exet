# Git-backed puzzle storage (ipuz_files)

Exet can load and save puzzles through the [ipuz_files](https://github.com/ianfhunter/ipuz_files) git submodule, using the FastAPI backend.

## Setup

1. Initialize the submodule (already added at `exet/ipuz_files/`):

   ```bash
   git submodule update --init ipuz_files
   ```

2. Start Exet via the backend (not a plain static server):

   ```powershell
   .\backend\start_server.ps1
   ```

   Open `http://127.0.0.1:8000/`.

3. Git push auth must work from the machine running the backend (SSH keys for `git@github.com:ianfhunter/ipuz_files.git`).

## Layout

```
ipuz_files/
  drafts/    # work-in-progress puzzles
  puzzles/   # finished puzzles
```

Supported extensions: `.puz`, `.ipuz`, `.json` (Exet data dump).

## UI

- **Open → Open from ipuz_files (GitHub)…** — runs `git pull`, then lists **Drafts** and **Puzzles**.
- **Save → Save to ipuz_files (GitHub)…** — choose draft/puzzle folder, format, and filename; writes the file, `git commit`, and `git push`.

Menu items appear only when `/api/puzzles/status` reports the submodule is ready.

## API

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/puzzles/status` | Submodule / git health |
| POST | `/api/puzzles/sync` | `git pull --ff-only` |
| GET | `/api/puzzles/list` | Pull, then list `drafts` and `puzzles` |
| GET | `/api/puzzles/file?kind=&name=` | Pull, then return file (base64) |
| POST | `/api/puzzles/save` | Write file, commit, push |

JSON dumps use `format: "exet-json"` and include the current Exolve revision plus preflex/unpreflex lists.
