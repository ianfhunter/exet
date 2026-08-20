#!/usr/bin/env python3
"""Local dev server for Exet + Exolve (serves exet/ and exolve/ on one port).

Usage (from exet/):  python tools/serve-dev.py
"""

from __future__ import annotations

import http.server
import os
import socketserver
import sys
import urllib.parse
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
EXET = ROOT
EXOLVE = ROOT.parent / "exolve"
PORT = 8765
CHUNK = 1024 * 1024


class Handler(http.server.BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        path = urllib.parse.unquote(
            urllib.parse.urlparse(self.path).path
        ).lstrip("/")
        if not path:
            path = "exet.html"
        for base in (EXET, EXOLVE):
            fp = os.path.join(base, path)
            if os.path.isfile(fp):
                self._send_file(fp)
                return
        self.send_error(404)

    def _send_file(self, fp: str) -> None:
        ctype = "application/octet-stream"
        if fp.endswith(".js"):
            ctype = "application/javascript"
        elif fp.endswith(".css"):
            ctype = "text/css"
        elif fp.endswith(".html"):
            ctype = "text/html"
        elif fp.endswith(".png"):
            ctype = "image/png"
        elif fp.endswith(".txt"):
            ctype = "text/plain"
        size = os.path.getsize(fp)
        try:
            self.send_response(200)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(size))
            self.end_headers()
            with open(fp, "rb") as f:
                while True:
                    chunk = f.read(CHUNK)
                    if not chunk:
                        break
                    self.wfile.write(chunk)
        except (BrokenPipeError, ConnectionAbortedError, ConnectionResetError):
            pass

    def log_message(self, fmt: str, *args) -> None:
        print(fmt % args)


class ThreadedServer(socketserver.ThreadingMixIn, socketserver.TCPServer):
    allow_reuse_address = True
    daemon_threads = True


def main() -> int:
    port = int(sys.argv[1]) if len(sys.argv) > 1 else PORT
    url = f"http://localhost:{port}/exet.html"
    print(f"Serving exet at {url}")
    with ThreadedServer(("", port), Handler) as httpd:
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\nStopped.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
