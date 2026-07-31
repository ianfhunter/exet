#!/usr/bin/env node
/**
 * Light Exet .puz save server.
 *
 * POST   /api/puz              — save a .puz (raw body; X-Filename header)
 * GET    /api/puz              — list saved .puz files
 * GET    /api/puz/:name        — download a saved .puz
 * DELETE /api/puz/:name        — delete a saved .puz
 * GET    /api/health           — health check
 *
 * Also serves static files from STATIC_DIR (the Exet app root).
 */

const http = require('http');
const fs = require('fs');
const fsp = require('fs/promises');
const path = require('path');
const { URL } = require('url');

const PORT = Number(process.env.PORT || 3080);
const SAVE_DIR = path.resolve(process.env.SAVE_DIR || path.join(__dirname, '..', 'saved-puzzles'));
const STATIC_DIR = path.resolve(process.env.STATIC_DIR || path.join(__dirname, '..'));
const MAX_BYTES = Number(process.env.MAX_PUZ_BYTES || 2 * 1024 * 1024);

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

function sendJson(res, status, obj) {
  const body = JSON.stringify(obj);
  res.writeHead(status, {
    'Content-Type': 'application/json; charset=utf-8',
    'Content-Length': Buffer.byteLength(body),
    'Access-Control-Allow-Origin': '*',
    'Access-Control-Allow-Headers': 'Content-Type, X-Filename',
    'Access-Control-Allow-Methods': 'GET, POST, DELETE, OPTIONS',
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

async function ensureSaveDir() {
  await fsp.mkdir(SAVE_DIR, { recursive: true });
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

function safeJoinStatic(urlPath) {
  const decoded = decodeURIComponent(urlPath.split('?')[0]);
  const rel = decoded === '/' ? '/exet.html' : decoded;
  const full = path.normalize(path.join(STATIC_DIR, rel));
  if (!full.startsWith(STATIC_DIR + path.sep) && full !== STATIC_DIR) {
    return null;
  }
  return full;
}

async function handleApi(req, res, url) {
  if (req.method === 'OPTIONS') {
    res.writeHead(204, {
      'Access-Control-Allow-Origin': '*',
      'Access-Control-Allow-Headers': 'Content-Type, X-Filename',
      'Access-Control-Allow-Methods': 'GET, POST, DELETE, OPTIONS',
    });
    res.end();
    return;
  }

  if (url.pathname === '/api/health' && req.method === 'GET') {
    sendJson(res, 200, { ok: true, saveDir: SAVE_DIR });
    return;
  }

  if (url.pathname === '/api/puz' && req.method === 'GET') {
    const files = await listPuzFiles();
    sendJson(res, 200, { files });
    return;
  }

  if (url.pathname === '/api/puz' && req.method === 'POST') {
    const filename = sanitizePuzName(req.headers['x-filename'] || url.searchParams.get('filename'));
    if (!filename) {
      sendJson(res, 400, { error: 'Missing or invalid X-Filename (.puz required)' });
      return;
    }
    let body;
    try {
      body = await readBody(req, MAX_BYTES);
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
  await ensureSaveDir();
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
    console.log(`Exet puz server listening on http://localhost:${PORT}`);
    console.log(`  static: ${STATIC_DIR}`);
    console.log(`  saves:  ${SAVE_DIR}`);
  });
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});
