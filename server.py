#!/usr/bin/env python3
"""Agent Trail server: serves the viewer and streams trail files over SSE.

Trail files are append-only JSONL (one event per line) living in ./trails/.
Live mode is just "tail a file that a capture script is appending to": the
capture layer and the viewer never talk to each other directly.

Endpoints:
    GET /                     viewer app
    GET /api/sessions         [{name, size, mtime, live}]
    GET /api/trail/<name>     full trail file (application/x-ndjson)
    GET /api/stream/<name>    SSE: replays existing events, then streams appends

Usage:  server.py [--port 7845] [--trails DIR]
"""
import argparse
import json
import os
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import unquote

ROOT = os.path.dirname(os.path.abspath(__file__))
LIVE_WINDOW = 15  # file modified within N seconds counts as "live"


def make_handler(trails_dir):
    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def log_message(self, fmt, *args):
            pass  # keep the console quiet

        def _send(self, code, body, ctype="application/json"):
            data = body if isinstance(body, bytes) else body.encode()
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(data)

        def _trail_path(self, name):
            name = os.path.basename(unquote(name))  # no traversal
            path = os.path.join(trails_dir, name)
            return path if os.path.isfile(path) else None

        def do_GET(self):
            path = self.path.split("?")[0]
            if path in ("/", "/index.html"):
                with open(os.path.join(ROOT, "viewer", "index.html"), "rb") as f:
                    self._send(200, f.read(), "text/html; charset=utf-8")
            elif path == "/api/sessions":
                self.api_sessions()
            elif path.startswith("/api/trail/"):
                self.api_trail(path[len("/api/trail/"):])
            elif path.startswith("/api/stream/"):
                self.api_stream(path[len("/api/stream/"):])
            else:
                self._send(404, '{"error":"not found"}')

        def api_sessions(self):
            now = time.time()
            out = []
            for f in sorted(os.listdir(trails_dir)):
                if not f.endswith(".jsonl"):
                    continue
                full = os.path.join(trails_dir, f)
                st = os.stat(full)
                out.append(
                    {
                        "name": f,
                        "size": st.st_size,
                        "mtime": st.st_mtime,
                        "live": (now - st.st_mtime) < LIVE_WINDOW,
                    }
                )
            out.sort(key=lambda s: -s["mtime"])
            self._send(200, json.dumps(out))

        def api_trail(self, name):
            path = self._trail_path(name)
            if not path:
                return self._send(404, '{"error":"no such trail"}')
            with open(path, "rb") as f:
                self._send(200, f.read(), "application/x-ndjson")

        def api_stream(self, name):
            path = self._trail_path(name)
            if not path:
                return self._send(404, '{"error":"no such trail"}')
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Connection", "keep-alive")
            self.end_headers()
            try:
                with open(path, "r") as f:
                    buf = ""
                    last_beat = time.time()
                    while True:
                        chunk = f.read()
                        if chunk:
                            buf += chunk
                            while "\n" in buf:
                                line, buf = buf.split("\n", 1)
                                if line.strip():
                                    self.wfile.write(f"data: {line}\n\n".encode())
                            self.wfile.flush()
                        else:
                            time.sleep(0.25)
                            if time.time() - last_beat > 15:
                                self.wfile.write(b": keepalive\n\n")
                                self.wfile.flush()
                                last_beat = time.time()
            except (BrokenPipeError, ConnectionResetError):
                pass

    return Handler


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--port", type=int, default=7845)
    ap.add_argument("--trails", default=os.path.join(ROOT, "trails"))
    args = ap.parse_args()
    os.makedirs(args.trails, exist_ok=True)
    srv = ThreadingHTTPServer(("127.0.0.1", args.port), make_handler(args.trails))
    print(f"agent-trail viewer:  http://127.0.0.1:{args.port}")
    print(f"trails directory:    {args.trails}")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
