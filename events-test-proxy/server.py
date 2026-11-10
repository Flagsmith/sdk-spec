"""A proxy in front of Flagsmith's events API, for scenarios about how SDKs deliver events.

SDKs send events here. A request is forwarded to the events API, unless the runner has set up
failures for its environment key: each request then fails with the next of them.

- `POST /test-proxy/environments/<key>/failures` with `{"failures": [...]}` appends failures,
  each a status code, `"ECONNRESET"` (the connection is reset) or `"ETIMEDOUT"` (the request is
  held until the SDK gives up on it).
- `GET /test-proxy/environments/<key>/requests` returns `{"requests": [...]}`, every request
  received for the key in order, as `{"response": ..., "events": [...]}`. `response` is the
  failure it took, or the events API's status when it was forwarded.
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
CONNECTION_RESET = "ECONNRESET"
TIMED_OUT = "ETIMEDOUT"
# How long a request failing with `ETIMEDOUT` is held when the SDK never gives up on it.
MAX_HANG_SECONDS = 300
# Not forwarded: they describe this connection, not the request.
HOP_BY_HOP_HEADERS = {"connection", "content-length", "host", "keep-alive", "transfer-encoding"}

lock = threading.Lock()
failures: defaultdict[str, deque[int | str]] = defaultdict(deque)
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
            if (method, resource) == ("POST", "failures"):
                new = json.loads(body)["failures"]
                invalid = [f for f in new if not is_failure(f)]
                if invalid:
                    self.reply(400, {"detail": f"Cannot fail with {invalid}"})
                    return
                failures[environment_key].extend(new)
                self.reply(204, None)
            elif (method, resource) == ("GET", "requests"):
                self.reply(200, {"requests": requests[environment_key]})
            else:
                self.reply(404, {"detail": f"No {method} /test-proxy/environments/<key>/{resource}"})

    def proxy(self, body: bytes) -> None:
        environment_key = self.headers.get(ENVIRONMENT_KEY_HEADER, "")
        with lock:
            queued = failures[environment_key]
            failure = queued.popleft() if queued else None
            request = {"response": failure, "events": events_in(body)}
            requests[environment_key].append(request)
        if failure is None:
            status = self.forward(body)
            with lock:
                request["response"] = status
        elif failure == CONNECTION_RESET:
            self.drop_connection()
        elif failure == TIMED_OUT:
            self.wait_for_sdk_to_give_up()
            self.drop_connection()
        else:
            self.reply(failure, {"detail": f"Test proxy {failure} response"})

    def forward(self, body: bytes) -> int:
        """Sends the request on to the events API, and its response back. Returns its status."""
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
        except OSError as e:
            self.reply(502, {"detail": f"Events API unreachable: {e}"})
            return 502
        self.send_response(status)
        for name, value in headers.items():
            if name.lower() not in HOP_BY_HOP_HEADERS:
                self.send_header(name, value)
        self.send_header("Content-Length", str(len(content)))
        self.end_headers()
        self.wfile.write(content)
        return status

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


def is_failure(failure: Any) -> bool:
    if isinstance(failure, int) and not isinstance(failure, bool):
        return 400 <= failure <= 599
    return failure in (CONNECTION_RESET, TIMED_OUT)


def events_in(body: bytes) -> list[Any]:
    try:
        return json.loads(body)["events"]
    except (ValueError, KeyError, TypeError):
        return []


if __name__ == "__main__":
    ThreadingHTTPServer(("", PORT), Handler).serve_forever()
