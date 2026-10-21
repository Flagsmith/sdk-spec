"""Seeds and inspects a real Flagsmith instance through its Admin API."""

import uuid
from dataclasses import dataclass, field
from typing import Any

from sdk_spec.http import json_request, wait_until_ok


@dataclass
class Environment:
    project_id: int
    id: int
    api_key: str
    server_side_key: str
    features: dict[str, int] = field(default_factory=dict)
    segments: dict[str, int] = field(default_factory=dict)


class FlagsmithAdmin:
    def __init__(self, base_url: str) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_url = f"{self.base_url}/api/v1"
        self._token: str | None = None
        self._organisation_id: int | None = None

    def _request(self, method: str, path: str, body: Any = None) -> Any:
        headers = {"Authorization": f"Token {self._token}"} if self._token else {}
        return json_request(method, f"{self.api_url}{path}", body, headers)

    def wait_until_healthy(self, timeout_seconds: float = 180) -> None:
        wait_until_ok(f"{self.base_url}/health/liveness/", timeout_seconds)

    def sign_up(self) -> None:
        """Registers a throwaway admin user and creates an organisation for this run."""
        password = uuid.uuid4().hex + "Aa1!"
        response = self._request(
            "POST",
            "/auth/users/",
            {
                "email": f"sdk-spec-{uuid.uuid4().hex[:12]}@example.com",
                "password": password,
                "re_password": password,
                "first_name": "SDK",
                "last_name": "Spec",
            },
        )
        self._token = response["key"]
        organisation = self._request("POST", "/organisations/", {"name": "SDK spec"})
        self._organisation_id = organisation["id"]

    def create_environment(self) -> Environment:
        """Creates an isolated project and environment for a single scenario."""
        project = self._request(
            "POST",
            "/projects/",
            {"name": f"scenario-{uuid.uuid4().hex[:12]}", "organisation": self._organisation_id},
        )
        environment = self._request(
            "POST", "/environments/", {"name": "spec", "project": project["id"]}
        )
        server_side_key = self._request(
            "POST",
            f"/environments/{environment['api_key']}/api-keys/",
            {"name": "sdk-spec"},
        )
        return Environment(
            project_id=project["id"],
            id=environment["id"],
            api_key=environment["api_key"],
            server_side_key=server_side_key["key"],
        )

    def delete_project(self, environment: Environment) -> None:
        self._request("DELETE", f"/projects/{environment.project_id}/")

    def connect_warehouse(self, environment: Environment, config: dict[str, Any]) -> None:
        """Connects the environment to a warehouse, so that it can receive events.

        Flagsmith's events API only accepts an environment that has one, and warehouse
        delivery inserts the environment's events there for the runner to read.
        """
        self._request(
            "POST",
            f"/environments/{environment.api_key}/warehouse-connections/",
            {"name": "sdk-spec", "warehouse_type": "clickhouse", **config},
        )

    def create_feature(
        self, environment: Environment, name: str, enabled: bool, value: Any
    ) -> None:
        body: dict[str, Any] = {"name": name, "default_enabled": enabled}
        if value is not None:
            # Flagsmith infers the value type (string, integer or boolean) from `initial_value`.
            body["initial_value"] = value
        feature = self._request("POST", f"/projects/{environment.project_id}/features/", body)
        environment.features[name] = feature["id"]

    def create_trait_segment(
        self, environment: Environment, name: str, trait: str, operator: str, value: Any
    ) -> None:
        segment = self._request(
            "POST",
            f"/projects/{environment.project_id}/segments/",
            {
                "name": name,
                "project": environment.project_id,
                "rules": [
                    {
                        "type": "ALL",
                        "conditions": [],
                        "rules": [
                            {
                                "type": "ANY",
                                "rules": [],
                                "conditions": [
                                    {"property": trait, "operator": operator, "value": str(value)}
                                ],
                            }
                        ],
                    }
                ],
            },
        )
        environment.segments[name] = segment["id"]

    def create_segment_override(
        self, environment: Environment, segment: str, feature: str, enabled: bool, value: Any
    ) -> None:
        self._request(
            "POST",
            f"/environments/{environment.api_key}/features/"
            f"{environment.features[feature]}/create-segment-override/",
            {
                "enabled": enabled,
                "feature_state_value": _typed_value(value),
                "feature_segment": {"segment": environment.segments[segment]},
            },
        )

    def get_identity_traits(self, environment: Environment, identifier: str) -> dict[str, Any]:
        identities = self._request(
            "GET", f"/environments/{environment.api_key}/identities/?q={identifier}"
        )["results"]
        matches = [i for i in identities if i["identifier"] == identifier]
        if not matches:
            raise LookupError(f"Identity {identifier!r} does not exist in Flagsmith")
        traits = self._request(
            "GET", f"/environments/{environment.api_key}/identities/{matches[0]['id']}/traits/"
        )["results"]
        return {trait["trait_key"]: _trait_value(trait) for trait in traits}


def _typed_value(value: Any) -> dict[str, Any]:
    if isinstance(value, bool):
        return {"type": "bool", "boolean_value": value}
    if isinstance(value, int):
        return {"type": "int", "integer_value": value}
    return {"type": "unicode", "string_value": None if value is None else str(value)}


def _trait_value(trait: dict[str, Any]) -> Any:
    return {
        "int": trait["integer_value"],
        "bool": trait["boolean_value"],
        "float": trait["float_value"],
    }.get(trait["value_type"], trait["string_value"])
