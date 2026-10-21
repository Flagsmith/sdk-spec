"""Client for the SDK adapter protocol described in ADAPTER.md."""

from typing import Any

import pytest

from sdk_spec.http import HTTPError, json_request, wait_until_ok

ADAPTER_DOCS_URL = "https://github.com/Flagsmith/sdk-spec/blob/main/ADAPTER.md"


class Adapter:
    def __init__(self, base_url: str) -> None:
        self.base_url = base_url.rstrip("/")

    def _command(
        self, method: str, path: str, body: Any = None, client_id: str | None = None
    ) -> Any:
        """Sends an adapter command. `path` may contain a `{clientId}` placeholder."""
        command = f"{method} {path}"
        url = f"{self.base_url}{path.format(clientId=client_id)}"
        try:
            return json_request(method, url, body)
        except HTTPError as e:
            if e.status != 404:
                raise
        pytest.fail(
            f"The SDK adapter does not implement `{command}`.\n"
            f"Implement it as described in {ADAPTER_DOCS_URL}",
            pytrace=False,
        )

    def wait_until_healthy(self, timeout_seconds: float = 120) -> dict[str, Any]:
        return wait_until_ok(f"{self.base_url}/health", timeout_seconds)

    def create_client(self, environment_key: str, api_url: str) -> str:
        response = self._command(
            "POST", "/clients", {"environmentKey": environment_key, "apiUrl": api_url}
        )
        return str(response["clientId"])

    def environment_flags(self, client_id: str) -> list[dict[str, Any]]:
        return self._command(
            "POST", "/clients/{clientId}/environment-flags", {}, client_id
        )["flags"]

    def identity_flags(
        self, client_id: str, identifier: str, traits: dict[str, Any]
    ) -> list[dict[str, Any]]:
        return self._command(
            "POST",
            "/clients/{clientId}/identity-flags",
            {"identifier": identifier, "traits": traits},
            client_id,
        )["flags"]

    def delete_client(self, client_id: str) -> None:
        self._command("DELETE", "/clients/{clientId}", client_id=client_id)
