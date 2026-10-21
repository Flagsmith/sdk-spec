"""Reads the events an SDK sent out of the environment's warehouse.

An SDK sends events to Flagsmith's events API, which writes them to Kafka, from where
warehouse delivery inserts them into the environment's warehouse. The spec connects a
ClickHouse warehouse to every `@events` environment (see `compose.yml`), so this reads the
far end of the real delivery path rather than standing in for it.
"""

import json
import time
import urllib.request
from typing import Any
from urllib.parse import quote

from sdk_spec.http import wait_until_ok

# How long the path from an SDK's buffer to the warehouse is given. SDKs send on a timer of
# their own, then the event is queued in Kafka and delivered in a batch.
ARRIVAL_TIMEOUT_SECONDS = 60
# How long an SDK is given to send an event before the spec calls it unsent. Longer than
# any SDK's send interval, so that a late event fails the scenario rather than passing it.
SETTLE_SECONDS = 30

# The columns the spec asserts on. `traits` and `metadata` are stored as JSON text.
COLUMNS = ("event", "feature_name", "identifier", "value", "traits", "metadata")
JSON_COLUMNS = ("traits", "metadata")

EVENTS_QUERY = f"""
SELECT {", ".join(COLUMNS)}
FROM events
WHERE environment_key = {{environment_key:String}}
ORDER BY timestamp, event
"""


class Warehouse:
    """The ClickHouse instance the spec connects to its environments."""

    def __init__(self, base_url: str, database: str, username: str, password: str) -> None:
        self.base_url = base_url.rstrip("/")
        self.database = database
        self.username = username
        self.password = password

    def wait_until_healthy(self, timeout_seconds: float = 120) -> None:
        wait_until_ok(f"{self.base_url}/ping", timeout_seconds, expect_json=False)

    def query(self, sql: str, **parameters: str) -> list[dict[str, Any]]:
        """Runs a query, with `{name:Type}` placeholders bound to `parameters`."""
        url = f"{self.base_url}/?database={self.database}&default_format=JSONEachRow"
        url += "".join(f"&param_{name}={quote(value)}" for name, value in parameters.items())
        request = urllib.request.Request(
            url,
            data=sql.encode(),
            method="POST",
            headers={"X-ClickHouse-User": self.username, "X-ClickHouse-Key": self.password},
        )
        with urllib.request.urlopen(request, timeout=30) as response:
            body = response.read().decode()
        return [json.loads(line) for line in body.splitlines() if line]

    def events(self, environment_key: str) -> list[dict[str, Any]]:
        """The events delivered for the environment so far, oldest first.

        An SDK sends events under its own environment key; Flagsmith records them against
        the environment, so `environment_key` is the environment's API key.
        """
        rows = self.query(EVENTS_QUERY, environment_key=environment_key)
        for row in rows:
            for column in JSON_COLUMNS:
                row[column] = json.loads(row[column]) if row[column] else None
        return rows

    def wait_for_events(self, environment_key: str, count: int) -> list[dict[str, Any]]:
        """Waits for `count` events to be delivered, then returns everything that has."""
        deadline = time.monotonic() + ARRIVAL_TIMEOUT_SECONDS
        while True:
            events = self.events(environment_key)
            if len(events) >= count or time.monotonic() >= deadline:
                return events
            time.sleep(1)

    def settle(self, environment_key: str) -> list[dict[str, Any]]:
        """Waits out the send and delivery path, then returns whatever arrived."""
        time.sleep(SETTLE_SECONDS)
        return self.events(environment_key)
