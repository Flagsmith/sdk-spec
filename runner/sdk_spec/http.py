import json
import time
import urllib.error
import urllib.request
from typing import Any


class HTTPError(Exception):
    def __init__(self, method: str, url: str, status: int, body: str) -> None:
        super().__init__(f"{method} {url} failed with {status}: {body}")
        self.status = status


def json_request(
    method: str,
    url: str,
    body: Any = None,
    headers: dict[str, str] | None = None,
    timeout: float = 30,
) -> Any:
    data = json.dumps(body).encode() if body is not None else None
    request = urllib.request.Request(
        url,
        data=data,
        method=method,
        headers={"Content-Type": "application/json", **(headers or {})},
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            raw = response.read()
    except urllib.error.HTTPError as e:
        raise HTTPError(method, url, e.code, e.read().decode(errors="replace")) from e
    return json.loads(raw) if raw else None


def wait_until_ok(url: str, timeout_seconds: float, expect_json: bool = True) -> Any:
    deadline = time.monotonic() + timeout_seconds
    while True:
        try:
            if expect_json:
                return json_request("GET", url, timeout=5)
            with urllib.request.urlopen(url, timeout=5) as response:
                return response.read()
        except (urllib.error.URLError, ConnectionError, HTTPError) as e:
            if time.monotonic() > deadline:
                raise TimeoutError(f"{url} did not become healthy: {e}") from e
            time.sleep(1)
