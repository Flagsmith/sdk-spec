import inspect
import json
import os
import re
from collections.abc import Iterator
from dataclasses import dataclass
from typing import Any

import pytest
from pytest_bdd import given, parsers, then, when

from sdk_spec.flagsmith_admin import Environment, FlagsmithAdmin
from sdk_spec.sdk import SDK

# Where the runner reaches Flagsmith, to seed and inspect it.
FLAGSMITH_URL = os.environ.get("FLAGSMITH_URL", "http://localhost:8000")
# Where the SDK under test reaches Flagsmith. Differs from FLAGSMITH_URL when the
# SDK runs on a different network, e.g. a container network.
FLAGSMITH_SDK_URL = os.environ.get("FLAGSMITH_SDK_URL", FLAGSMITH_URL)
# Starts the SDK's language harness, e.g. `docker run -i --rm sdk-spec-sdk`.
SDK_COMMAND = os.environ.get("SDK_COMMAND", "")


def pytest_report_header() -> list[str]:
    return [
        f"flagsmith: {FLAGSMITH_URL} (SDK uses {FLAGSMITH_SDK_URL})",
        f"sdk: {SDK_COMMAND}",
    ]


@dataclass
class ScenarioState:
    environment: Environment | None = None
    client: str | None = None
    result: Any = None


@pytest.fixture(scope="session")
def flagsmith() -> FlagsmithAdmin:
    admin = FlagsmithAdmin(FLAGSMITH_URL)
    admin.wait_until_healthy()
    admin.sign_up()
    return admin


@pytest.fixture(scope="session")
def sdk(pytestconfig: pytest.Config) -> Iterator[SDK]:
    if not SDK_COMMAND:
        pytest.exit("Set SDK_COMMAND to the command that starts the SDK harness", returncode=4)
    sdk = SDK(SDK_COMMAND)
    required = [CREATE_CLIENT, *SDK_STEPS]
    implemented = [step for step in required if step in sdk.implemented_steps]
    # Write through the terminal reporter, so the line is shown even with output captured.
    terminal = pytestconfig.pluginmanager.get_plugin("terminalreporter")
    terminal.write_line(f"\nSDK implements {len(implemented)}/{len(required)} steps")
    yield sdk
    sdk.close()


@pytest.fixture
def state(flagsmith: FlagsmithAdmin, sdk: SDK) -> Iterator[ScenarioState]:
    state = ScenarioState()
    yield state
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


def table_argument(datatable: list[list[str]]) -> Any:
    """A `<key> | value` table becomes a map; any other table becomes a list of rows."""
    header = datatable[0]
    rows = table_rows(datatable)
    if len(header) == 2 and header[1] == "value":
        return {row[header[0]]: parse_value(row["value"]) for row in rows}
    return [{key: parse_value(value) for key, value in row.items()} for row in rows]


def require_environment(state: ScenarioState) -> Environment:
    assert state.environment, "Scenario must start with 'Given a Flagsmith environment'"
    return state.environment


# SDK steps
#
# Every `When` step is an SDK step: the runner hands it to the SDK's steps file, passing the
# step's placeholders in order, then its data table. Quoted placeholders ("{name}") are strings;
# others are JSON literals. Register SDK steps with `sdk_step`, never with `@when`.

CREATE_CLIENT = "Create the SDK client"
SDK_STEPS: list[str] = []
PLACEHOLDER = re.compile(r'("?)\{(\w+)\}\1')


def sdk_client(state: ScenarioState, sdk: SDK) -> str:
    """Creates the scenario's SDK client before its first SDK step, after all `Given` steps."""
    if state.client is None:
        state.client = sdk.step(
            CREATE_CLIENT,
            # Server-side SDKs authenticate with a server-side environment key.
            [require_environment(state).server_side_key, f"{FLAGSMITH_SDK_URL.rstrip('/')}/api/v1/"],
            returns_client=True,
        )
    return state.client


def sdk_step(pattern: str) -> None:
    """Registers `When <pattern>` as a step run by the SDK's steps file."""
    placeholders = PLACEHOLDER.findall(pattern)
    has_table = pattern.endswith(":")
    text = f"When {pattern}"

    def run(**kwargs: Any) -> None:
        state: ScenarioState = kwargs["state"]
        sdk: SDK = kwargs["sdk"]
        args = [
            kwargs[name] if quoted else parse_value(kwargs[name]) for quoted, name in placeholders
        ]
        if has_table:
            args.append(table_argument(kwargs["datatable"]))
        state.result = sdk.step(text, args, client=sdk_client(state, sdk))

    parameters = ["state", "sdk", *(name for _, name in placeholders)]
    if has_table:
        parameters.append("datatable")
    run.__signature__ = inspect.Signature(  # type: ignore[attr-defined]
        [inspect.Parameter(name, inspect.Parameter.POSITIONAL_OR_KEYWORD) for name in parameters]
    )
    run.__name__ = re.sub(r"\W+", "_", pattern).strip("_")
    when(parsers.parse(pattern), stacklevel=2)(run)
    SDK_STEPS.append(text)


sdk_step("the application gets the environment flags")
sdk_step('the application gets the flags for identity "{identifier}" with traits:')


# Given: the runner sets up Flagsmith


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


# Then: the runner checks the outcome


@then("the application receives the following flags:")
def received_flags(state: ScenarioState, datatable: list[list[str]]) -> None:
    assert state.result is not None, "The application has not fetched any flags"
    expected = {
        row["feature"]: {"enabled": parse_value(row["enabled"]), "value": parse_value(row["value"])}
        for row in table_rows(datatable)
    }
    actual = {
        flag["feature"]: {"enabled": flag["enabled"], "value": flag["value"]}
        for flag in state.result
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
