"""Client for the SDK adapter protocol described in ADAPTER.md."""

from typing import Any

from sdk_spec.http import json_request, wait_until_ok


class Adapter:
    def __init__(self, base_url: str) -> None:
        self.base_url = base_url.rstrip("/")

    def wait_until_healthy(self, timeout_seconds: float = 120) -> dict[str, Any]:
        return wait_until_ok(f"{self.base_url}/health", timeout_seconds)

    def create_client(self, environment_key: str, api_url: str) -> str:
        response = json_request(
            "POST",
            f"{self.base_url}/clients",
            {"environmentKey": environment_key, "apiUrl": api_url},
        )
        return str(response["clientId"])

    def environment_flags(self, client_id: str) -> list[dict[str, Any]]:
        return json_request(
            "POST", f"{self.base_url}/clients/{client_id}/environment-flags", {}
        )["flags"]

    def identity_flags(
        self, client_id: str, identifier: str, traits: dict[str, Any]
    ) -> list[dict[str, Any]]:
        return json_request(
            "POST",
            f"{self.base_url}/clients/{client_id}/identity-flags",
            {"identifier": identifier, "traits": traits},
        )["flags"]

    def delete_client(self, client_id: str) -> None:
        json_request("DELETE", f"{self.base_url}/clients/{client_id}")
