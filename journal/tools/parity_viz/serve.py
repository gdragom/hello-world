#!/usr/bin/env python3
"""Local web app: TV vs Python Fib / FVG / entries (2026→now).

Usage:
  cd journal/tools/parity_viz
  python serve.py

Then open http://127.0.0.1:8765
"""
from __future__ import annotations

import argparse
import functools
import http.server
import os
import socketserver
import subprocess
import sys
import webbrowser
from pathlib import Path

HERE = Path(__file__).resolve().parent
BUILD = HERE / "build_data.py"
DATA = HERE / "data.json"
STATIC = HERE / "static"


class Handler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(STATIC), **kwargs)

    def do_GET(self):  # noqa: N802
        if self.path in ("/data.json", "/api/data"):
            if not DATA.exists():
                self.send_error(404, "data.json missing — run build first")
                return
            body = DATA.read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)
            return
        if self.path in ("/", "/index.html"):
            self.path = "/index.html"
        return super().do_GET()

    def log_message(self, fmt: str, *args) -> None:
        sys.stderr.write("%s - %s\n" % (self.address_string(), fmt % args))


def build() -> None:
    print("Building parity data (Python + TV export)…", flush=True)
    subprocess.check_call([sys.executable, str(BUILD)], cwd=str(HERE.parent))


def main() -> int:
    ap = argparse.ArgumentParser(description="LEDGER TV vs Python parity viz")
    ap.add_argument("--port", type=int, default=8765)
    ap.add_argument("--no-build", action="store_true", help="Skip rebuild if data.json exists")
    ap.add_argument("--no-open", action="store_true")
    args = ap.parse_args()

    if not args.no_build or not DATA.exists():
        build()
    elif not DATA.exists():
        build()

    # Allow reuse on Windows
    socketserver.TCPServer.allow_reuse_address = True
    with socketserver.TCPServer(("127.0.0.1", args.port), Handler) as httpd:
        url = f"http://127.0.0.1:{args.port}/"
        print(f"Parity viz -> {url}", flush=True)
        print("Ctrl+C to stop.", flush=True)
        if not args.no_open:
            try:
                webbrowser.open(url)
            except Exception:
                pass
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\nStopped.", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
