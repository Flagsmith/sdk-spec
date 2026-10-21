"""Reads back the events an SDK sent. See events-api/events_api.py."""

import time
from typing import Any
from urllib.parse import quote

from sdk_spec.http import json_request, wait_until_ok

# SDKs buffer events and send them on a timer, so the runner waits for them to arrive.
ARRIVAL_TIMEOUT_SECONDS = 30
# How long an SDK is given to send an event before the spec calls it unsent. Longer than
# any SDK's send interval, so that a late batch fails the scenario rather than passing it.
SETTLE_SECONDS = 15


class EventsAPI:
    def __init__(self, base_url: str) -> None:
        self.base_url = base_url.rstrip("/")

    def wait_until_healthy(self, timeout_seconds: float = 60) -> None:
        wait_until_ok(f"{self.base_url}/health", timeout_seconds)

    def events(self, environment_key: str) -> list[dict[str, Any]]:
        """The events sent so far by the client holding `environment_key`."""
        url = f"{self.base_url}/spec/events?environment_key={quote(environment_key)}"
        return json_request("GET", url)["events"]

    def wait_for_events(self, environment_key: str, count: int) -> list[dict[str, Any]]:
        """Waits for `count` events to arrive, then returns everything that has."""
        deadline = time.monotonic() + ARRIVAL_TIMEOUT_SECONDS
        while True:
            events = self.events(environment_key)
            if len(events) >= count or time.monotonic() >= deadline:
                return events
            time.sleep(0.5)

    def settle(self, environment_key: str) -> list[dict[str, Any]]:
        """Waits out every SDK's send interval, then returns whatever arrived."""
        time.sleep(SETTLE_SECONDS)
        return self.events(environment_key)
