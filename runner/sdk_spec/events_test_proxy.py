"""Controls the proxy SDKs send events through, in front of Flagsmith's events API.

See `events-test-proxy/server.py`. Responses and requests are kept per environment key, the
server-side key the SDK sends events with.
"""

from typing import Any
from urllib.parse import quote

from sdk_spec.http import json_request, wait_until_ok


class EventsTestProxy:
    def __init__(self, base_url: str) -> None:
        self.base_url = base_url.rstrip("/")

    def wait_until_healthy(self, timeout_seconds: float = 60) -> None:
        wait_until_ok(f"{self.base_url}/test-proxy/health", timeout_seconds)

    def fail(self, environment_key: str, failures: list[int | str]) -> None:
        """Fails the next requests for the key with `failures`, in order; later ones are forwarded."""
        json_request(
            "POST",
            f"{self.base_url}/test-proxy/environments/{quote(environment_key)}/failures",
            {"failures": failures},
        )

    def requests(self, environment_key: str) -> list[dict[str, Any]]:
        """Every request received for the key so far, oldest first, with the response it got."""
        return json_request(
            "GET", f"{self.base_url}/test-proxy/environments/{quote(environment_key)}/requests"
        )["requests"]
