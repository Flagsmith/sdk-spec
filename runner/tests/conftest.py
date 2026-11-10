import inspect
import json
import os
import re
import time
from collections.abc import Iterator
from dataclasses import dataclass
from typing import Any

import pytest
from pytest_bdd import given, parsers, then, when
from pytest_bdd.parser import Scenario

from sdk_spec.events_test_proxy import EventsTestProxy
from sdk_spec.flagsmith_admin import Environment, FlagsmithAdmin
from sdk_spec import sdk as sdk_module
from sdk_spec.sdk import SDK
from sdk_spec.warehouse import Warehouse

# Where the runner reaches Flagsmith, to seed and inspect it.
FLAGSMITH_URL = os.environ.get("FLAGSMITH_URL", "http://localhost:8000")
# Where the SDK under test reaches Flagsmith. Differs from FLAGSMITH_URL when the
# SDK runs on a different network, e.g. a container network.
FLAGSMITH_SDK_URL = os.environ.get("FLAGSMITH_SDK_URL", FLAGSMITH_URL)
# Where the SDK under test reaches Flagsmith's events API, through the proxy in front of it.
# Unlike Flagsmith, which can be anywhere, it is part of the spec's compose project, so it
# defaults to its service there.
EVENTS_SDK_URL = os.environ.get("EVENTS_SDK_URL", "http://events-test-proxy:8080")
# Where the runner reaches that proxy, to make it fail and to read the requests it received.
EVENTS_URL = os.environ.get("EVENTS_URL", "http://localhost:8080")
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
        f"events: {EVENTS_SDK_URL} (SDK), {EVENTS_URL} (runner), warehouse: {WAREHOUSE_URL}",
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
    local_evaluation: bool = False
    experiment_id: int | None = None
    result: Any = None
    elapsed_seconds: float | None = None


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
def events_test_proxy() -> EventsTestProxy:
    proxy = EventsTestProxy(EVENTS_URL)
    proxy.wait_until_healthy()
    return proxy


@pytest.fixture(scope="session")
def sdk(pytestconfig: pytest.Config) -> Iterator[SDK]:
    if not SDK_COMMAND:
        pytest.exit("Set SDK_COMMAND to the command that starts the SDK harness", returncode=4)
    sdk = SDK(SDK_COMMAND)
    required = [
        CREATE_CLIENT,
        CREATE_CLIENT_WITH_EVENTS,
        CREATE_CLIENT_WITH_LOCAL_EVALUATION,
        *SDK_STEPS,
    ]
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
# A client evaluating flags against the environment document, for server-side SDKs only.
CREATE_CLIENT_WITH_LOCAL_EVALUATION = "Create the SDK client with local evaluation"
# Both of the above, for scenarios about the events an SDK sends under local evaluation.
CREATE_CLIENT_WITH_LOCAL_EVALUATION_AND_EVENTS = (
    "Create the SDK client with local evaluation and events enabled"
)
SDK_STEPS: list[str] = []
SDK_STEP_PARSERS: list[tuple[parsers.parse, str]] = []
PLACEHOLDER = re.compile(r'("?)\{(\w+)\}\1')


def sdk_client(state: ScenarioState, sdk: SDK) -> str:
    """Creates the scenario's SDK client before its first SDK step, after all `Given` steps."""
    if state.client is None:
        environment = require_environment(state)
        # Server-side SDKs authenticate with a server-side environment key.
        args = [environment.server_side_key, f"{FLAGSMITH_SDK_URL.rstrip('/')}/api/v1/"]
        if state.events:
            args.append(f"{EVENTS_SDK_URL.rstrip('/')}/")
            step = (
                CREATE_CLIENT_WITH_LOCAL_EVALUATION_AND_EVENTS
                if state.local_evaluation
                else CREATE_CLIENT_WITH_EVENTS
            )
        elif state.local_evaluation:
            step = CREATE_CLIENT_WITH_LOCAL_EVALUATION
        else:
            step = CREATE_CLIENT
        state.client = sdk.step(step, args, returns_client=True)
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
        client = sdk_client(state, sdk)
        started = time.monotonic()
        state.result = sdk.step(text, args, client=client)
        state.elapsed_seconds = time.monotonic() - started

    parameters = ["state", "sdk", *(name for _, name in placeholders)]
    if has_table:
        parameters.append("datatable")
    run.__signature__ = inspect.Signature(  # type: ignore[attr-defined]
        [inspect.Parameter(name, inspect.Parameter.POSITIONAL_OR_KEYWORD) for name in parameters]
    )
    run.__name__ = re.sub(r"\W+", "_", pattern).strip("_")
    parser = parsers.parse(pattern)
    when(parser, stacklevel=2)(run)
    SDK_STEPS.append(text)
    SDK_STEP_PARSERS.append((parser, text))


def pytest_bdd_before_scenario(request: pytest.FixtureRequest, scenario: Scenario) -> None:
    """Ends a scenario using an SDK step the SDK does not implement before it changes anything.

    Otherwise it would set up Flagsmith and track events for nothing, and an SDK sharing state
    between clients would send those events in a later scenario.
    """
    sdk: SDK = request.getfixturevalue("sdk")
    for step in scenario.steps:
        if step.type != "when":
            continue
        for parser, text in SDK_STEP_PARSERS:
            if parser.is_matching(step.name) and text not in sdk.implemented_steps:
                sdk_module.report_missing(text)


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
sdk_step(
    'the application tracks events "event_{first}" to "event_{last}" for identity "{identifier}"'
)
sdk_step("the application flushes events")
sdk_step("the application closes the client with a timeout of {timeout} seconds")


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


# Failures of a request to the events API, named after the error the SDK gets.
CONNECTION_RESET = "ECONNRESET"
TIMED_OUT = "ETIMEDOUT"


def parse_response(raw: str) -> int | str:
    """A response to a request: an HTTP status code, ECONNRESET or ETIMEDOUT."""
    if raw.isdigit():
        return int(raw)
    if raw in (CONNECTION_RESET, TIMED_OUT):
        return raw
    raise ValueError(f"{raw!r} is not a status code, {CONNECTION_RESET} or {TIMED_OUT}")


@given("the events API fails the next requests with:")
def events_api_failures(
    state: ScenarioState, events_test_proxy: EventsTestProxy, datatable: list[list[str]]
) -> None:
    """Fails the SDK's next requests to the events API, in order; later ones reach it.

    A failure is a status code, ECONNRESET (the connection is reset), or ETIMEDOUT (the request
    goes unanswered until the SDK gives up on it).
    """
    assert state.events, "Scenario must say 'Given the SDK sends events to Flagsmith' first"
    events_test_proxy.fail(
        require_environment(state).server_side_key,
        [parse_response(row["failure"]) for row in table_rows(datatable)],
    )


@given("the SDK evaluates flags locally")
def sdk_evaluates_flags_locally(state: ScenarioState) -> None:
    """Asks for a client with local evaluation, which the runner creates for the first SDK step."""
    assert state.client is None, "The SDK client has already been created without local evaluation"
    state.local_evaluation = True


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


@given(
    parsers.re(
        r'a running experiment on feature "(?P<feature>[^"]+)"'
        r" enrolling (?P<rollout>\d+)% of identities,"
        r' serving variant "(?P<variant>[^"]+)" with value (?P<value>.+)'
        r" to (?P<allocation>\d+)% of them"
    ),
    converters={"rollout": int, "allocation": int},
)
def running_experiment(
    state: ScenarioState,
    flagsmith: FlagsmithAdmin,
    feature: str,
    variant: str,
    value: str,
    rollout: int,
    allocation: int,
) -> None:
    """Runs an experiment on the feature. Identities not served the variant are its control."""
    state.experiment_id = flagsmith.start_experiment(
        require_environment(state), feature, variant, parse_value(value), rollout, allocation
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


@given(parsers.parse('feature "{feature}" depends on feature "{prerequisite}"'))
def flag_dependency(
    state: ScenarioState, flagsmith: FlagsmithAdmin, feature: str, prerequisite: str
) -> None:
    flagsmith.create_flag_dependency(require_environment(state), feature, prerequisite)


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


# A metadata value standing for the id of the scenario's experiment, which Flagsmith assigns.
EXPERIMENT_ID = "<experiment>"


def with_experiment_id(metadata: Any, state: ScenarioState) -> Any:
    if not isinstance(metadata, dict):
        return metadata
    return {
        key: state.experiment_id if value == EXPERIMENT_ID else value
        for key, value in metadata.items()
    }


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
    for expectation in expected:
        if "metadata" in expectation:
            expectation["metadata"] = with_experiment_id(expectation["metadata"], state)
    delivered = warehouse.wait_for_events(require_environment(state).api_key, len(expected))
    assert len(delivered) == len(expected), f"Flagsmith received {delivered}"
    for event, expectation in zip(delivered, expected):
        assert event_as_expected(event, expectation) == expectation, f"Flagsmith received {event}"


@then("the SDK has sent the following events to the events API:")
def sent_events(
    state: ScenarioState, events_test_proxy: EventsTestProxy, datatable: list[list[str]]
) -> None:
    """Checks every event the SDK sent, in the order it sent them, with the response the request
    carrying each got: a failure it was given, or the events API's status code. How events are
    grouped into requests is up to the SDK.
    """
    expected = [
        {"response": parse_response(row["response"]), "event": row["event"]}
        for row in table_rows(datatable)
    ]
    actual = [
        {"response": request["response"], "event": event.get("event")}
        for request in events_test_proxy.requests(require_environment(state).server_side_key)
        for event in request["events"]
    ]
    assert actual == expected


@then(parsers.parse("the application waited less than {seconds} seconds"))
def waited_less_than(state: ScenarioState, seconds: str) -> None:
    """Checks how long the last SDK step took to return."""
    assert state.elapsed_seconds is not None, "The application has not used the SDK"
    assert state.elapsed_seconds < parse_value(seconds), (
        f"The application waited {state.elapsed_seconds:.1f} seconds"
    )


@then(parsers.parse('Flagsmith has received exactly events "event_{first:d}" to "event_{last:d}"'))
def received_numbered_events(
    state: ScenarioState, warehouse: Warehouse, first: int, last: int
) -> None:
    """Checks the SDK sent each of a range of numbered events once, and no other event.

    Order is not checked: the warehouse orders events by time, which many of them share.
    """
    expected = [f"event_{number}" for number in range(first, last + 1)]
    delivered = warehouse.wait_for_events(require_environment(state).api_key, len(expected))
    names = sorted(event["event"] for event in delivered)
    missing = sorted(set(expected) - set(names))
    unexpected = sorted(set(names) - set(expected))
    assert names == sorted(expected), (
        f"Flagsmith received {len(names)} events; missing {missing[:10]}, "
        f"unexpected {unexpected[:10]}"
    )


@then("Flagsmith has received no events")
def received_no_events(state: ScenarioState, warehouse: Warehouse) -> None:
    delivered = warehouse.settle(require_environment(state).api_key)
    assert delivered == [], f"Flagsmith received {delivered}"
