"""Controls the fake events API SDKs send events to, in front of Flagsmith's.

See `fake-events/server.py`. Responses and requests are kept per environment key, the
server-side key the SDK sends events with.
"""

from typing import Any
from urllib.parse import quote

from sdk_spec.http import json_request, wait_until_ok


class FakeEvents:
    def __init__(self, base_url: str) -> None:
        self.base_url = base_url.rstrip("/")

    def wait_until_healthy(self, timeout_seconds: float = 60) -> None:
        wait_until_ok(f"{self.base_url}/fake/health", timeout_seconds)

    def respond(self, environment_key: str, responses: list[int | str]) -> None:
        """Makes the next requests for the key take `responses`, in order, before passing through."""
        json_request(
            "POST",
            f"{self.base_url}/fake/environments/{quote(environment_key)}/responses",
            {"responses": responses},
        )

    def requests(self, environment_key: str) -> list[dict[str, Any]]:
        """Every request received for the key so far, oldest first, with the response it took."""
        return json_request(
            "GET", f"{self.base_url}/fake/environments/{quote(environment_key)}/requests"
        )["requests"]
