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
from sdk_spec import sdk as sdk_module
from sdk_spec.sdk import SDK
from sdk_spec.warehouse import Warehouse

# Where the runner reaches Flagsmith, to seed and inspect it.
FLAGSMITH_URL = os.environ.get("FLAGSMITH_URL", "http://localhost:8000")
# Where the SDK under test reaches Flagsmith. Differs from FLAGSMITH_URL when the
# SDK runs on a different network, e.g. a container network.
FLAGSMITH_SDK_URL = os.environ.get("FLAGSMITH_SDK_URL", FLAGSMITH_URL)
# Where the SDK under test reaches Flagsmith's events API. Unlike Flagsmith, which can be
# anywhere, it is part of the spec's compose project, so it defaults to its service there.
EVENTS_SDK_URL = os.environ.get("EVENTS_SDK_URL", "http://events:8080")
# Where the runner reaches the warehouse the spec connects to its environments, to read
# back the events delivered to it, and how Flagsmith and warehouse delivery reach it.
WAREHOUSE_URL = os.environ.get("WAREHOUSE_URL", "http://localhost:8123")
WAREHOUSE_CONFIG = {
    "config": {
        "host": os.environ.get("WAREHOUSE_HOST", "clickhouse"),
        "port": 8123,
        "database": "flagsmith_exp",
        "username": "flagsmith",
        "secure": False,
    },
    "credentials": {"password": "password"},
}
# Starts the SDK's language harness, e.g. `docker run -i --rm sdk-spec-sdk`.
SDK_COMMAND = os.environ.get("SDK_COMMAND", "")


def pytest_report_header() -> list[str]:
    return [
        f"flagsmith: {FLAGSMITH_URL} (SDK uses {FLAGSMITH_SDK_URL})",
        f"events: {EVENTS_SDK_URL} (SDK), warehouse: {WAREHOUSE_URL} (runner)",
        f"sdk: {SDK_COMMAND}",
        f"missing steps: {sdk_module.MISSING_STEPS}",
    ]


def pytest_terminal_summary(terminalreporter: pytest.TerminalReporter) -> None:
    """Lists the steps the SDK does not implement, as GitHub annotations when in Actions."""
    if not sdk_module.missing_steps:
        return
    terminalreporter.section("steps the SDK does not implement")
    for step in sorted(sdk_module.missing_steps):
        terminalreporter.write_line(step)
        if os.environ.get("GITHUB_ACTIONS") == "true":
            level = "warning" if sdk_module.MISSING_STEPS == "xfail" else "error"
            terminalreporter.write_line(
                f"::{level} title=SDK does not implement a step::{step}"
            )


@dataclass
class ScenarioState:
    environment: Environment | None = None
    client: str | None = None
    events: bool = False
    result: Any = None


@pytest.fixture(scope="session")
def flagsmith() -> FlagsmithAdmin:
    admin = FlagsmithAdmin(FLAGSMITH_URL)
    admin.wait_until_healthy()
    admin.sign_up()
    return admin


@pytest.fixture(scope="session")
def warehouse() -> Warehouse:
    config = WAREHOUSE_CONFIG["config"]
    warehouse = Warehouse(
        WAREHOUSE_URL,
        database=config["database"],
        username=config["username"],
        password=WAREHOUSE_CONFIG["credentials"]["password"],
    )
    warehouse.wait_until_healthy()
    return warehouse


@pytest.fixture(scope="session")
def sdk(pytestconfig: pytest.Config) -> Iterator[SDK]:
    if not SDK_COMMAND:
        pytest.exit("Set SDK_COMMAND to the command that starts the SDK harness", returncode=4)
    sdk = SDK(SDK_COMMAND)
    required = [CREATE_CLIENT, CREATE_CLIENT_WITH_EVENTS, *SDK_STEPS]
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
# A second client, for scenarios that are about the events an SDK sends. Events are off by
# default in every SDK, and the events API is not derived from the Flagsmith API URL.
CREATE_CLIENT_WITH_EVENTS = "Create the SDK client with events enabled"
SDK_STEPS: list[str] = []
PLACEHOLDER = re.compile(r'("?)\{(\w+)\}\1')


def sdk_client(state: ScenarioState, sdk: SDK) -> str:
    """Creates the scenario's SDK client before its first SDK step, after all `Given` steps."""
    if state.client is None:
        environment = require_environment(state)
        # Server-side SDKs authenticate with a server-side environment key.
        args = [environment.server_side_key, f"{FLAGSMITH_SDK_URL.rstrip('/')}/api/v1/"]
        if state.events:
            args.append(f"{EVENTS_SDK_URL.rstrip('/')}/")
        state.client = sdk.step(
            CREATE_CLIENT_WITH_EVENTS if state.events else CREATE_CLIENT,
            args,
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
sdk_step(
    'the application gets the experiment flag "{feature}" for identity "{identifier}"'
    " with traits:"
)
sdk_step(
    'the application tracks event "{event}" for identity "{identifier}"'
    " with value {value} and metadata:"
)
sdk_step(
    'the application tracks an exposure of feature "{feature}" for identity "{identifier}"'
    " with value {value} and metadata:"
)


# Given: the runner sets up Flagsmith


@given("a Flagsmith environment")
def flagsmith_environment(state: ScenarioState, flagsmith: FlagsmithAdmin) -> None:
    state.environment = flagsmith.create_environment()


@given("the SDK sends events to Flagsmith")
def sdk_sends_events(state: ScenarioState, flagsmith: FlagsmithAdmin) -> None:
    """Connects the environment's warehouse, so that Flagsmith accepts the SDK's events.

    Also asks for a client with events enabled, which the runner creates for the first SDK
    step: events are off by default in every SDK.
    """
    assert state.client is None, "The SDK client has already been created without events"
    flagsmith.connect_warehouse(require_environment(state), WAREHOUSE_CONFIG)
    state.events = True


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


# Columns of an event table that name the field differently from the event itself.
EVENT_FIELDS = {"feature": "feature_name"}
# Columns of an event table holding a JSON value rather than a bare name.
EVENT_VALUES = ("value", "traits", "metadata")


def event_as_expected(event: dict[str, Any], expectation: dict[str, Any]) -> dict[str, Any]:
    """The part of a delivered event its expectation names, in the expectation's terms."""
    actual = {column: event.get(EVENT_FIELDS.get(column, column)) for column in expectation}
    if "metadata" in expectation:
        # SDKs add metadata of their own, such as the version they report themselves as.
        delivered = actual["metadata"] or {}
        actual["metadata"] = {key: delivered.get(key) for key in expectation["metadata"]}
    return actual


@then("Flagsmith has received the following events:")
def received_events(
    state: ScenarioState, warehouse: Warehouse, datatable: list[list[str]]
) -> None:
    """Checks the events the SDK sent, on the columns the table names."""
    expected = [
        {key: parse_value(value) if key in EVENT_VALUES else value for key, value in row.items()}
        for row in table_rows(datatable)
    ]
    delivered = warehouse.wait_for_events(require_environment(state).api_key, len(expected))
    assert len(delivered) == len(expected), f"Flagsmith received {delivered}"
    for event, expectation in zip(delivered, expected):
        assert event_as_expected(event, expectation) == expectation, f"Flagsmith received {event}"


@then("Flagsmith has received no events")
def received_no_events(state: ScenarioState, warehouse: Warehouse) -> None:
    delivered = warehouse.settle(require_environment(state).api_key)
    assert delivered == [], f"Flagsmith received {delivered}"
