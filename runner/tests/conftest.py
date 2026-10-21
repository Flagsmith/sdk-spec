import json
import os
from collections.abc import Iterator
from dataclasses import dataclass
from typing import Any

import pytest
from pytest_bdd import given, parsers, then, when

from sdk_spec.adapter import Adapter
from sdk_spec.flagsmith_admin import Environment, FlagsmithAdmin

# Where the runner reaches Flagsmith, to seed and inspect it.
FLAGSMITH_URL = os.environ.get("FLAGSMITH_URL", "http://localhost:8000")
# Where the SDK under test reaches Flagsmith. Differs from FLAGSMITH_URL when the
# adapter runs on a different network, e.g. a container network.
FLAGSMITH_SDK_URL = os.environ.get("FLAGSMITH_SDK_URL", FLAGSMITH_URL)
SDK_ADAPTER_URL = os.environ.get("SDK_ADAPTER_URL", "http://localhost:8080")


def pytest_report_header() -> list[str]:
    return [
        f"flagsmith: {FLAGSMITH_URL} (SDK uses {FLAGSMITH_SDK_URL})",
        f"sdk adapter: {SDK_ADAPTER_URL}",
    ]


@dataclass
class ScenarioState:
    environment: Environment | None = None
    client_id: str | None = None
    flags: list[dict[str, Any]] | None = None


@pytest.fixture(scope="session")
def flagsmith() -> FlagsmithAdmin:
    admin = FlagsmithAdmin(FLAGSMITH_URL)
    admin.wait_until_healthy()
    admin.sign_up()
    return admin


@pytest.fixture(scope="session")
def adapter() -> Adapter:
    adapter = Adapter(SDK_ADAPTER_URL)
    adapter.wait_until_healthy()
    return adapter


@pytest.fixture
def state(flagsmith: FlagsmithAdmin, adapter: Adapter) -> Iterator[ScenarioState]:
    state = ScenarioState()
    yield state
    if state.client_id:
        adapter.delete_client(state.client_id)
    if state.environment:
        flagsmith.delete_project(state.environment)


def parse_value(raw: str) -> Any:
    """Table cells and step arguments hold JSON literals: "text", 42, true, null."""
    try:
        return json.loads(raw)
    except ValueError as e:
        raise ValueError(f"{raw!r} is not a JSON literal; quote strings, e.g. \"{raw}\"") from e


def table_rows(datatable: list[list[str]]) -> list[dict[str, str]]:
    header, *rows = datatable
    return [dict(zip(header, (cell.strip() for cell in row))) for row in rows]


def table_traits(datatable: list[list[str]]) -> dict[str, Any]:
    return {row["trait"]: parse_value(row["value"]) for row in table_rows(datatable)}


def require_environment(state: ScenarioState) -> Environment:
    assert state.environment, "Scenario must start with 'Given a Flagsmith environment'"
    return state.environment


def require_client(state: ScenarioState) -> str:
    assert state.client_id, "Scenario must create a client with 'an SDK client for the environment'"
    return state.client_id


# Given


@given("a Flagsmith environment")
def flagsmith_environment(state: ScenarioState, flagsmith: FlagsmithAdmin) -> None:
    state.environment = flagsmith.create_environment()


@given("the environment has the following features:")
def environment_features(
    state: ScenarioState, flagsmith: FlagsmithAdmin, datatable: list[list[str]]
) -> None:
    environment = require_environment(state)
    for row in table_rows(datatable):
        flagsmith.create_feature(
            environment,
            name=row["feature"],
            enabled=parse_value(row["enabled"]),
            value=parse_value(row["value"]),
        )


@given(parsers.parse('a segment "{segment}" where trait "{trait}" equals {value}'))
def trait_segment(
    state: ScenarioState, flagsmith: FlagsmithAdmin, segment: str, trait: str, value: str
) -> None:
    flagsmith.create_trait_segment(
        require_environment(state), segment, trait, "EQUAL", parse_value(value)
    )


@given(
    parsers.parse(
        'segment "{segment}" overrides feature "{feature}" with enabled {enabled} and value {value}'
    )
)
def segment_override(
    state: ScenarioState,
    flagsmith: FlagsmithAdmin,
    segment: str,
    feature: str,
    enabled: str,
    value: str,
) -> None:
    flagsmith.create_segment_override(
        require_environment(state), segment, feature, parse_value(enabled), parse_value(value)
    )


@given("an SDK client for the environment")
def sdk_client(state: ScenarioState, adapter: Adapter) -> None:
    state.client_id = adapter.create_client(
        environment_key=require_environment(state).api_key,
        api_url=f"{FLAGSMITH_SDK_URL.rstrip('/')}/api/v1/",
    )


# When


@when("the application gets the environment flags")
def get_environment_flags(state: ScenarioState, adapter: Adapter) -> None:
    state.flags = adapter.environment_flags(require_client(state))


@when(parsers.parse('the application gets the flags for identity "{identifier}" with traits:'))
def get_identity_flags(
    state: ScenarioState, adapter: Adapter, identifier: str, datatable: list[list[str]]
) -> None:
    state.flags = adapter.identity_flags(
        require_client(state), identifier, table_traits(datatable)
    )


# Then


@then("the application receives the following flags:")
def received_flags(state: ScenarioState, datatable: list[list[str]]) -> None:
    assert state.flags is not None, "The application has not fetched any flags"
    expected = {
        row["feature"]: {"enabled": parse_value(row["enabled"]), "value": parse_value(row["value"])}
        for row in table_rows(datatable)
    }
    actual = {
        flag["featureName"]: {"enabled": flag["enabled"], "value": flag["value"]}
        for flag in state.flags
    }
    assert actual == expected


@then(parsers.parse('Flagsmith has identity "{identifier}" with the following traits:'))
def persisted_traits(
    state: ScenarioState,
    flagsmith: FlagsmithAdmin,
    identifier: str,
    datatable: list[list[str]],
) -> None:
    actual = flagsmith.get_identity_traits(require_environment(state), identifier)
    assert actual == table_traits(datatable)
