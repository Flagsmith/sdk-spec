"""Flagsmith's events API, as far as the spec is concerned. See ../README.md.

SDKs send tracking and exposure events to Flagsmith's events API, which the open-source
Flagsmith image does not serve. The spec runs this in its place: it records every batch it
is sent, keyed by the environment key that sent it, and the runner reads them back to
check what an SDK sent.

Uses only the standard library, so it runs in a stock Python image.
"""

import json
import os
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any
from urllib.parse import parse_qs, urlparse

PORT = int(os.environ.get("PORT", 8000))
MAX_BODY_BYTES = 10 * 1024 * 1024

_lock = threading.Lock()
_events: dict[str, list[dict[str, Any]]] = {}


def record(environment_key: str, events: list[dict[str, Any]]) -> None:
    with _lock:
        _events.setdefault(environment_key, []).extend(events)


def recorded(environment_key: str) -> list[dict[str, Any]]:
    with _lock:
        return list(_events.get(environment_key, ()))


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def do_GET(self) -> None:  # noqa: N802 - BaseHTTPRequestHandler's naming
        url = urlparse(self.path)
        if url.path == "/health":
            self.respond(200, {"status": "ok"})
        elif url.path == "/spec/events":
            key = parse_qs(url.query).get("environment_key", [""])[0]
            self.respond(200, {"events": recorded(key)})
        else:
            self.respond(404, {"detail": f"Nothing is served at {url.path}"})

    def do_POST(self) -> None:  # noqa: N802 - BaseHTTPRequestHandler's naming
        # Any path: which one an SDK posts a batch to is a wire detail the spec leaves open.
        environment_key = self.headers.get("X-Environment-Key")
        if not environment_key:
            self.respond(401, {"detail": "X-Environment-Key is missing"})
            return
        length = int(self.headers.get("Content-Length") or 0)
        if length > MAX_BODY_BYTES:
            self.respond(413, {"detail": "The batch is too large"})
            return
        try:
            batch = json.loads(self.rfile.read(length) or b"{}")
            events = batch["events"]
        except (ValueError, KeyError, TypeError):
            self.respond(400, {"detail": 'The body must be {"events": [...]}'})
            return
        record(environment_key, events)
        self.respond(200, {"success": True})

    def respond(self, status: int, body: dict[str, Any]) -> None:
        raw = json.dumps(body).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)


if __name__ == "__main__":
    ThreadingHTTPServer(("", PORT), Handler).serve_forever()
