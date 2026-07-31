# Exet save server

A tiny zero-dependency Node.js HTTP server that:

- Serves the Exet static app
- Accepts `.puz` uploads and stores them on disk
- Mirrors browser `localStorage` (revisions, prefs, settings)

## Run with Docker Compose (from repo root)

```bash
docker compose up --build
```

Then open `http://localhost:3080/exet.html`.

## Run directly

```bash
node server.js
```

Environment variables:

| Variable | Default | Meaning |
|---|---|---|
| `PORT` | `3080` | Listen port |
| `SAVE_DIR` | `../saved-puzzles` | Where `.puz` files are written |
| `STORAGE_PATH` | `../saved-storage/localStorage.json` | localStorage mirror file |
| `STATIC_DIR` | `..` (repo root) | Static files to serve |
| `MAX_PUZ_BYTES` | `2097152` | Max `.puz` upload size |
| `MAX_STORAGE_BYTES` | `20971520` | Max storage snapshot size |

## API

### Health
- `GET /api/health`

### PUZ files
- `GET /api/puz`
- `POST /api/puz` (body = raw bytes, header `X-Filename: name.puz`)
- `GET /api/puz/:name`
- `DELETE /api/puz/:name`

### localStorage mirror
- `GET /api/storage` → `{ items: { key: stringValue, ... }, updatedAt, ... }`
- `PUT /api/storage` with `{ items: { ... } }` (full replace)
- `POST /api/storage/batch` with `{ put: { key: value }, delete: [key] }`
- `PUT /api/storage/item` with `{ key, value }`
- `DELETE /api/storage/item?key=...`
- `GET /api/storage/meta`
