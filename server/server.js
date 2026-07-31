#!/usr/bin/env node
/**
 * Light Exet save server.
 *
 * PUZ files:
 *   POST   /api/puz              — save a .puz (raw body; X-Filename header)
 *   GET    /api/puz              — list saved .puz files
 *   GET    /api/puz/:name        — download a saved .puz
 *   DELETE /api/puz/:name        — delete a saved .puz
 *
 * Browser localStorage mirror:
 *   GET    /api/storage          — full { items, updatedAt }
 *   PUT    /api/storage          — replace all items from { items }
 *   POST   /api/storage/batch    — { put: {key:value}, delete: [key] }
 *   PUT    /api/storage/item     — { key, value } set one item
 *   DELETE /api/storage/item?key= — delete one item
 *
 *   GET    /api/health           — health check
 *
 * Also serves static files from STATIC_DIR (the Exet app root).
 */

const http = require('http');
const fs = require('fs');
const fsp = require('fs/promises');
const path = require('path');
const { URL } = require('url');

const PORT = Number(process.env.PORT || 3080);
const SAVE_DIR = path.resolve(
    process.env.SAVE_DIR || path.join(__dirname, '..', 'saved-puzzles'));
const STORAGE_PATH = path.resolve(
    process.env.STORAGE_PATH ||
    path.join(__dirname, '..', 'saved-storage', 'localStorage.json'));
const STATIC_DIR = path.resolve(
    process.env.STATIC_DIR || path.join(__dirname, '..'));
const MAX_PUZ_BYTES = Number(process.env.MAX_PUZ_BYTES || 2 * 1024 * 1024);
const MAX_STORAGE_BYTES = Number(
    process.env.MAX_STORAGE_BYTES || 20 * 1024 * 1024);

const MIME = {
  '.html': 'text/html; charset=utf-8',
  '.js': 'text/javascript; charset=utf-8',
  '.css': 'text/css; charset=utf-8',
  '.png': 'image/png',
  '.ico': 'image/x-icon',
  '.txt': 'text/plain; charset=utf-8',
  '.json': 'application/json; charset=utf-8',
  '.svg': 'image/svg+xml',
  '.puz': 'application/x-crossword',
};

/** Serialize writes to the storage file. */
let storageChain = Promise.resolve();

function sendJson(res, status, obj) {
  const body = JSON.stringify(obj);
  res.writeHead(status, {
    'Content-Type': 'application/json; charset=utf-8',
    'Content-Length': Buffer.byteLength(body),
    'Access-Control-Allow-Origin': '*',
    'Access-Control-Allow-Headers': 'Content-Type, X-Filename',
    'Access-Control-Allow-Methods': 'GET, POST, PUT, DELETE, OPTIONS',
  });
  res.end(body);
}

function sendRaw(res, status, data, contentType, extraHeaders = {}) {
  const buf = Buffer.isBuffer(data) ? data : Buffer.from(data);
  res.writeHead(status, {
    'Content-Type': contentType,
    'Content-Length': buf.length,
    'Access-Control-Allow-Origin': '*',
    ...extraHeaders,
  });
  res.end(buf);
}

function sanitizePuzName(name) {
  if (!name || typeof name !== 'string') return null;
  let base = path.basename(name.trim());
  base = base.replace(/[^A-Za-z0-9._ -]/g, '_');
  base = base.replace(/\s+/g, '-');
  if (!base.toLowerCase().endsWith('.puz')) {
    base += '.puz';
  }
  if (base.length < 5 || base.length > 180) return null;
  if (base === '.puz' || base.startsWith('.')) return null;
  return base;
}

function isValidStorageKey(key) {
  return typeof key === 'string' && key.length > 0 && key.length <= 512;
}

async function ensureDirs() {
  await fsp.mkdir(SAVE_DIR, { recursive: true });
  await fsp.mkdir(path.dirname(STORAGE_PATH), { recursive: true });
}

function readBody(req, limit) {
  return new Promise((resolve, reject) => {
    const chunks = [];
    let size = 0;
    req.on('data', (chunk) => {
      size += chunk.length;
      if (size > limit) {
        reject(Object.assign(new Error('Payload too large'), { statusCode: 413 }));
        req.destroy();
        return;
      }
      chunks.push(chunk);
    });
    req.on('end', () => resolve(Buffer.concat(chunks)));
    req.on('error', reject);
  });
}

async function listPuzFiles() {
  const names = await fsp.readdir(SAVE_DIR);
  const out = [];
  for (const name of names) {
    if (!name.toLowerCase().endsWith('.puz')) continue;
    const st = await fsp.stat(path.join(SAVE_DIR, name));
    if (!st.isFile()) continue;
    out.push({
      name,
      size: st.size,
      mtime: st.mtime.toISOString(),
    });
  }
  out.sort((a, b) => (a.mtime < b.mtime ? 1 : -1));
  return out;
}

async function readStorage() {
  try {
    const raw = await fsp.readFile(STORAGE_PATH, 'utf8');
    const parsed = JSON.parse(raw);
    if (!parsed || typeof parsed !== 'object' || !parsed.items ||
        typeof parsed.items !== 'object') {
      return { items: {}, updatedAt: null };
    }
    return {
      items: parsed.items,
      updatedAt: parsed.updatedAt || null,
    };
  } catch (err) {
    if (err.code === 'ENOENT') return { items: {}, updatedAt: null };
    throw err;
  }
}

async function writeStorage(items) {
  const payload = {
    items,
    updatedAt: new Date().toISOString(),
  };
  const json = JSON.stringify(payload);
  if (Buffer.byteLength(json) > MAX_STORAGE_BYTES) {
    const err = new Error('Storage snapshot too large');
    err.statusCode = 413;
    throw err;
  }
  const tmp = STORAGE_PATH + '.tmp';
  await fsp.writeFile(tmp, json, 'utf8');
  await fsp.rename(tmp, STORAGE_PATH);
  return payload;
}

function withStorageLock(fn) {
  const run = storageChain.then(fn, fn);
  storageChain = run.catch(() => {});
  return run;
}

function storageSummary(store) {
  const keys = Object.keys(store.items);
  let totalSize = 0;
  const keyInfo = keys.map((key) => {
    const value = store.items[key];
    const size = typeof value === 'string' ? value.length : 0;
    totalSize += size;
    return { key, size };
  });
  keyInfo.sort((a, b) => a.key.localeCompare(b.key));
  return {
    updatedAt: store.updatedAt,
    keyCount: keys.length,
    totalSize,
    keys: keyInfo,
  };
}

function safeJoinStatic(urlPath) {
  const decoded = decodeURIComponent(urlPath.split('?')[0]);
  const rel = decoded === '/' ? '/exet.html' : decoded;
  const full = path.normalize(path.join(STATIC_DIR, rel));
  if (!full.startsWith(STATIC_DIR + path.sep) && full !== STATIC_DIR) {
    return null;
  }
  return full;
}

async function handleStorageApi(req, res, url) {
  if (url.pathname === '/api/storage' && req.method === 'GET') {
    const store = await readStorage();
    sendJson(res, 200, {
      items: store.items,
      updatedAt: store.updatedAt,
      ...storageSummary(store),
    });
    return true;
  }

  if (url.pathname === '/api/storage/meta' && req.method === 'GET') {
    const store = await readStorage();
    sendJson(res, 200, storageSummary(store));
    return true;
  }

  if (url.pathname === '/api/storage' && req.method === 'PUT') {
    let body;
    try {
      body = await readBody(req, MAX_STORAGE_BYTES);
    } catch (err) {
      sendJson(res, err.statusCode || 400, { error: err.message || 'Bad request' });
      return true;
    }
    let parsed;
    try {
      parsed = JSON.parse(body.toString('utf8'));
    } catch (err) {
      sendJson(res, 400, { error: 'Invalid JSON' });
      return true;
    }
    if (!parsed || typeof parsed.items !== 'object' || Array.isArray(parsed.items)) {
      sendJson(res, 400, { error: 'Body must be { items: { key: stringValue, ... } }' });
      return true;
    }
    const items = {};
    for (const [key, value] of Object.entries(parsed.items)) {
      if (!isValidStorageKey(key)) {
        sendJson(res, 400, { error: 'Invalid storage key: ' + key });
        return true;
      }
      if (typeof value !== 'string') {
        sendJson(res, 400, { error: 'Values must be strings (key: ' + key + ')' });
        return true;
      }
      items[key] = value;
    }
    try {
      const saved = await withStorageLock(() => writeStorage(items));
      sendJson(res, 200, { ok: true, ...storageSummary(saved) });
    } catch (err) {
      sendJson(res, err.statusCode || 500, { error: err.message || 'Write failed' });
    }
    return true;
  }

  if (url.pathname === '/api/storage/item' && req.method === 'PUT') {
    let body;
    try {
      body = await readBody(req, MAX_STORAGE_BYTES);
    } catch (err) {
      sendJson(res, err.statusCode || 400, { error: err.message || 'Bad request' });
      return true;
    }
    let parsed;
    try {
      parsed = JSON.parse(body.toString('utf8'));
    } catch (err) {
      sendJson(res, 400, { error: 'Invalid JSON' });
      return true;
    }
    if (!parsed || !isValidStorageKey(parsed.key) || typeof parsed.value !== 'string') {
      sendJson(res, 400, { error: 'Body must be { key: string, value: string }' });
      return true;
    }
    try {
      const saved = await withStorageLock(async () => {
        const store = await readStorage();
        store.items[parsed.key] = parsed.value;
        return writeStorage(store.items);
      });
      sendJson(res, 200, { ok: true, key: parsed.key, ...storageSummary(saved) });
    } catch (err) {
      sendJson(res, err.statusCode || 500, { error: err.message || 'Write failed' });
    }
    return true;
  }

  if (url.pathname === '/api/storage/item' && req.method === 'DELETE') {
    const key = url.searchParams.get('key');
    if (!isValidStorageKey(key)) {
      sendJson(res, 400, { error: 'Missing or invalid key query parameter' });
      return true;
    }
    try {
      const saved = await withStorageLock(async () => {
        const store = await readStorage();
        const existed = Object.prototype.hasOwnProperty.call(store.items, key);
        delete store.items[key];
        const written = await writeStorage(store.items);
        return { existed, written };
      });
      sendJson(res, saved.existed ? 200 : 404, {
        ok: saved.existed,
        key,
        ...storageSummary(saved.written),
        error: saved.existed ? undefined : 'Not found',
      });
    } catch (err) {
      sendJson(res, err.statusCode || 500, { error: err.message || 'Write failed' });
    }
    return true;
  }

  if (url.pathname === '/api/storage/batch' && req.method === 'POST') {
    let body;
    try {
      body = await readBody(req, MAX_STORAGE_BYTES);
    } catch (err) {
      sendJson(res, err.statusCode || 400, { error: err.message || 'Bad request' });
      return true;
    }
    let parsed;
    try {
      parsed = JSON.parse(body.toString('utf8'));
    } catch (err) {
      sendJson(res, 400, { error: 'Invalid JSON' });
      return true;
    }
    const put = (parsed && parsed.put && typeof parsed.put === 'object' &&
                 !Array.isArray(parsed.put)) ? parsed.put : {};
    const del = (parsed && Array.isArray(parsed.delete)) ? parsed.delete : [];
    for (const [key, value] of Object.entries(put)) {
      if (!isValidStorageKey(key) || typeof value !== 'string') {
        sendJson(res, 400, { error: 'Invalid put entry for key: ' + key });
        return true;
      }
    }
    for (const key of del) {
      if (!isValidStorageKey(key)) {
        sendJson(res, 400, { error: 'Invalid delete key: ' + key });
        return true;
      }
    }
    try {
      const saved = await withStorageLock(async () => {
        const store = await readStorage();
        for (const key of del) {
          delete store.items[key];
        }
        for (const [key, value] of Object.entries(put)) {
          store.items[key] = value;
        }
        return writeStorage(store.items);
      });
      sendJson(res, 200, {
        ok: true,
        putCount: Object.keys(put).length,
        deleteCount: del.length,
        ...storageSummary(saved),
      });
    } catch (err) {
      sendJson(res, err.statusCode || 500, { error: err.message || 'Write failed' });
    }
    return true;
  }

  return false;
}

async function handleApi(req, res, url) {
  if (req.method === 'OPTIONS') {
    res.writeHead(204, {
      'Access-Control-Allow-Origin': '*',
      'Access-Control-Allow-Headers': 'Content-Type, X-Filename',
      'Access-Control-Allow-Methods': 'GET, POST, PUT, DELETE, OPTIONS',
    });
    res.end();
    return;
  }

  if (url.pathname === '/api/health' && req.method === 'GET') {
    const store = await readStorage();
    sendJson(res, 200, {
      ok: true,
      saveDir: SAVE_DIR,
      storagePath: STORAGE_PATH,
      storage: storageSummary(store),
    });
    return;
  }

  if (await handleStorageApi(req, res, url)) {
    return;
  }

  if (url.pathname === '/api/puz' && req.method === 'GET') {
    const files = await listPuzFiles();
    sendJson(res, 200, { files });
    return;
  }

  if (url.pathname === '/api/puz' && req.method === 'POST') {
    const filename = sanitizePuzName(
        req.headers['x-filename'] || url.searchParams.get('filename'));
    if (!filename) {
      sendJson(res, 400, { error: 'Missing or invalid X-Filename (.puz required)' });
      return;
    }
    let body;
    try {
      body = await readBody(req, MAX_PUZ_BYTES);
    } catch (err) {
      sendJson(res, err.statusCode || 400, { error: err.message || 'Bad request' });
      return;
    }
    if (!body.length) {
      sendJson(res, 400, { error: 'Empty body' });
      return;
    }
    const dest = path.join(SAVE_DIR, filename);
    const existed = fs.existsSync(dest);
    await fsp.writeFile(dest, body);
    sendJson(res, existed ? 200 : 201, {
      ok: true,
      name: filename,
      size: body.length,
      overwritten: existed,
      url: `/api/puz/${encodeURIComponent(filename)}`,
    });
    return;
  }

  const match = url.pathname.match(/^\/api\/puz\/([^/]+)$/);
  if (match) {
    const filename = sanitizePuzName(decodeURIComponent(match[1]));
    if (!filename) {
      sendJson(res, 400, { error: 'Invalid filename' });
      return;
    }
    const dest = path.join(SAVE_DIR, filename);
    if (req.method === 'GET') {
      try {
        const data = await fsp.readFile(dest);
        sendRaw(res, 200, data, 'application/x-crossword', {
          'Content-Disposition': `attachment; filename="${filename}"`,
        });
      } catch (err) {
        if (err.code === 'ENOENT') sendJson(res, 404, { error: 'Not found' });
        else throw err;
      }
      return;
    }
    if (req.method === 'DELETE') {
      try {
        await fsp.unlink(dest);
        sendJson(res, 200, { ok: true, name: filename });
      } catch (err) {
        if (err.code === 'ENOENT') sendJson(res, 404, { error: 'Not found' });
        else throw err;
      }
      return;
    }
  }

  sendJson(res, 404, { error: 'Not found' });
}

async function handleStatic(req, res, url) {
  if (req.method !== 'GET' && req.method !== 'HEAD') {
    sendJson(res, 405, { error: 'Method not allowed' });
    return;
  }
  const filePath = safeJoinStatic(url.pathname);
  if (!filePath) {
    sendJson(res, 403, { error: 'Forbidden' });
    return;
  }
  try {
    const st = await fsp.stat(filePath);
    if (st.isDirectory()) {
      sendJson(res, 404, { error: 'Not found' });
      return;
    }
    const ext = path.extname(filePath).toLowerCase();
    const type = MIME[ext] || 'application/octet-stream';
    if (req.method === 'HEAD') {
      res.writeHead(200, {
        'Content-Type': type,
        'Content-Length': st.size,
        'Access-Control-Allow-Origin': '*',
      });
      res.end();
      return;
    }
    const data = await fsp.readFile(filePath);
    sendRaw(res, 200, data, type);
  } catch (err) {
    if (err.code === 'ENOENT') sendJson(res, 404, { error: 'Not found' });
    else throw err;
  }
}

async function main() {
  await ensureDirs();
  const server = http.createServer(async (req, res) => {
    try {
      const url = new URL(req.url || '/', `http://${req.headers.host || 'localhost'}`);
      if (url.pathname.startsWith('/api/')) {
        await handleApi(req, res, url);
      } else {
        await handleStatic(req, res, url);
      }
    } catch (err) {
      console.error(err);
      if (!res.headersSent) {
        sendJson(res, 500, { error: 'Internal server error' });
      }
    }
  });
  server.listen(PORT, () => {
    console.log(`Exet save server listening on http://localhost:${PORT}`);
    console.log(`  static:  ${STATIC_DIR}`);
    console.log(`  puz:     ${SAVE_DIR}`);
    console.log(`  storage: ${STORAGE_PATH}`);
  });
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});
