# Exet .puz save server

A tiny zero-dependency Node.js HTTP server that:

- Serves the Exet static app
- Accepts `.puz` uploads and stores them on disk

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
| `STATIC_DIR` | `..` (repo root) | Static files to serve |
| `MAX_PUZ_BYTES` | `2097152` | Max upload size |

## API

- `GET /api/health`
- `GET /api/puz`
- `POST /api/puz` (body = raw bytes, header `X-Filename: name.puz`)
- `GET /api/puz/:name`
- `DELETE /api/puz/:name`
