"""A proxy in front of Flagsmith's events API, for scenarios about how SDKs deliver events.

SDKs send events here. A request is passed through to the events API, unless the runner has
set up responses for its environment key: each request then takes the next of them.

- `POST /test-proxy/environments/<key>/responses` with `{"responses": [...]}` appends responses,
  each a status code, `"dropped connection"` or `"no response"`.
- `GET /test-proxy/environments/<key>/requests` returns `{"requests": [...]}`, every request
  received for the key in order, as `{"response": ..., "events": [...]}`. `response` is the
  one it took, or `"passed through"`.
"""

import json
import os
import select
import socket
import threading
import time
import urllib.error
import urllib.request
from collections import defaultdict, deque
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

UPSTREAM_URL = os.environ.get("UPSTREAM_URL", "http://events:8080").rstrip("/")
PORT = int(os.environ.get("PORT", "8080"))
ENVIRONMENT_KEY_HEADER = "X-Environment-Key"
DROPPED_CONNECTION = "dropped connection"
NO_RESPONSE = "no response"
PASSED_THROUGH = "passed through"
# How long a request taking `"no response"` is held when the SDK never gives up on it.
MAX_HANG_SECONDS = 300
# Not forwarded: they describe this connection, not the request.
HOP_BY_HOP_HEADERS = {"connection", "content-length", "host", "keep-alive", "transfer-encoding"}

lock = threading.Lock()
responses: defaultdict[str, deque[int | str]] = defaultdict(deque)
requests: defaultdict[str, list[dict[str, Any]]] = defaultdict(list)


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def do_GET(self) -> None:
        self.handle_request()

    def do_POST(self) -> None:
        self.handle_request()

    def handle_request(self) -> None:
        body = self.read_body()
        parts = self.path.strip("/").split("/")
        if parts == ["test-proxy", "health"]:
            self.reply(200, {})
        elif len(parts) == 4 and parts[:2] == ["test-proxy", "environments"]:
            self.control(self.command, parts[2], parts[3], body)
        else:
            self.proxy(body)

    def control(self, method: str, environment_key: str, resource: str, body: bytes) -> None:
        with lock:
            if (method, resource) == ("POST", "responses"):
                new = json.loads(body)["responses"]
                invalid = [r for r in new if not is_injectable(r)]
                if invalid:
                    self.reply(400, {"detail": f"Cannot respond with {invalid}"})
                    return
                responses[environment_key].extend(new)
                self.reply(204, None)
            elif (method, resource) == ("GET", "requests"):
                self.reply(200, {"requests": requests[environment_key]})
            else:
                self.reply(404, {"detail": f"No {method} /test-proxy/environments/<key>/{resource}"})

    def proxy(self, body: bytes) -> None:
        environment_key = self.headers.get(ENVIRONMENT_KEY_HEADER, "")
        with lock:
            queued = responses[environment_key]
            response = queued.popleft() if queued else PASSED_THROUGH
            requests[environment_key].append({"response": response, "events": events_in(body)})
        if response == PASSED_THROUGH:
            self.pass_through(body)
        elif response == DROPPED_CONNECTION:
            self.drop_connection()
        elif response == NO_RESPONSE:
            self.wait_for_sdk_to_give_up()
            self.drop_connection()
        else:
            self.reply(response, {"detail": f"Test proxy {response} response"})

    def pass_through(self, body: bytes) -> None:
        upstream = urllib.request.Request(
            f"{UPSTREAM_URL}{self.path}",
            data=body if self.command == "POST" else None,
            method=self.command,
            headers={
                name: value
                for name, value in self.headers.items()
                if name.lower() not in HOP_BY_HOP_HEADERS
            },
        )
        try:
            with urllib.request.urlopen(upstream, timeout=30) as response:
                status, headers, content = response.status, response.headers, response.read()
        except urllib.error.HTTPError as e:
            status, headers, content = e.code, e.headers, e.read()
        self.send_response(status)
        for name, value in headers.items():
            if name.lower() not in HOP_BY_HOP_HEADERS:
                self.send_header(name, value)
        self.send_header("Content-Length", str(len(content)))
        self.end_headers()
        self.wfile.write(content)

    def wait_for_sdk_to_give_up(self) -> None:
        """Returns once the SDK closes the connection, as it does when its request times out."""
        deadline = time.monotonic() + MAX_HANG_SECONDS
        while time.monotonic() < deadline:
            readable, _, _ = select.select([self.connection], [], [], 1)
            if readable and not self.connection.recv(1, socket.MSG_PEEK):
                return
            if readable:
                time.sleep(0.1)

    def drop_connection(self) -> None:
        self.close_connection = True
        try:
            self.connection.shutdown(socket.SHUT_RDWR)
        except OSError:
            pass

    def read_body(self) -> bytes:
        if self.headers.get("Transfer-Encoding", "").lower() == "chunked":
            chunks = []
            while size := int(self.rfile.readline().split(b";")[0], 16):
                chunks.append(self.rfile.read(size))
                self.rfile.readline()
            while self.rfile.readline() not in (b"\r\n", b"\n", b""):
                pass
            return b"".join(chunks)
        return self.rfile.read(int(self.headers.get("Content-Length") or 0))

    def reply(self, status: int, body: Any) -> None:
        content = b"" if body is None else json.dumps(body).encode()
        self.send_response(status)
        if content:
            self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(content)))
        self.end_headers()
        self.wfile.write(content)


def is_injectable(response: Any) -> bool:
    if isinstance(response, int) and not isinstance(response, bool):
        return 100 <= response <= 599
    return response in (DROPPED_CONNECTION, NO_RESPONSE)


def events_in(body: bytes) -> list[Any]:
    try:
        return json.loads(body)["events"]
    except (ValueError, KeyError, TypeError):
        return []


if __name__ == "__main__":
    ThreadingHTTPServer(("", PORT), Handler).serve_forever()
