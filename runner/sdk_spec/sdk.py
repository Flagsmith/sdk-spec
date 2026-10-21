"""Drives an SDK's steps file through its language harness. See HARNESS.md."""

import itertools
import json
import os
import queue
import shlex
import subprocess
import sys
import threading
from typing import Any

import pytest

STEPS_DOCS_URL = "https://github.com/Flagsmith/sdk-spec/blob/main/README.md#onboarding-an-sdk"
# `fail` (default): a step the SDK does not implement fails its scenario.
# `xfail`: it marks the scenario as an expected failure instead, so the run stays green.
MISSING_STEPS = os.environ.get("MISSING_STEPS", "fail")
if MISSING_STEPS not in ("fail", "xfail"):
    raise ValueError(f"MISSING_STEPS must be `fail` or `xfail`, not {MISSING_STEPS!r}")

# Steps the SDK does not implement, as seen during this run.
missing_steps: set[str] = set()
RESPONSE_TIMEOUT_SECONDS = 60


class SDKError(Exception):
    pass


class SDK:
    """A running SDK harness process, spoken to in JSON lines over stdin and stdout.

    Any stdout line that is not a harness response (for example, SDK logging) is
    forwarded to stderr, so SDKs are free to log.
    """

    def __init__(self, command: str) -> None:
        self.command = command
        self._ids = itertools.count(1)
        self._responses: queue.Queue[dict[str, Any] | None] = queue.Queue()
        self._process = subprocess.Popen(
            shlex.split(command),
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            text=True,
            bufsize=1,
        )
        threading.Thread(target=self._read_stdout, daemon=True).start()
        self.implemented_steps: list[str] = self._request({"command": "hello"})["steps"]

    def _read_stdout(self) -> None:
        assert self._process.stdout
        for line in self._process.stdout:
            try:
                message = json.loads(line)
            except ValueError:
                message = None
            if isinstance(message, dict) and "id" in message:
                self._responses.put(message)
            else:
                sys.stderr.write(f"[sdk] {line}")
        self._responses.put(None)

    def _request(self, request: dict[str, Any]) -> dict[str, Any]:
        request_id = next(self._ids)
        assert self._process.stdin
        try:
            self._process.stdin.write(json.dumps({"id": request_id, **request}) + "\n")
            self._process.stdin.flush()
        except BrokenPipeError as e:
            raise SDKError(f"The SDK harness has exited: {self.command}") from e
        while True:
            try:
                response = self._responses.get(timeout=RESPONSE_TIMEOUT_SECONDS)
            except queue.Empty:
                raise SDKError(
                    f"The SDK harness did not respond within {RESPONSE_TIMEOUT_SECONDS}s"
                ) from None
            if response is None:
                raise SDKError(
                    f"The SDK harness exited with code {self._process.wait()}: {self.command}"
                )
            if response["id"] == request_id:
                return response

    def step(
        self,
        step: str,
        args: list[Any],
        client: str | None = None,
        returns_client: bool = False,
    ) -> Any:
        """Runs an SDK step and returns its result, or a client handle if `returns_client`."""
        response = self._request(
            {
                "command": "step",
                "step": step,
                "args": args,
                "client": client,
                "returnsClient": returns_client,
            }
        )
        if response.get("missing"):
            missing_steps.add(step)
            message = (
                f"The SDK does not implement the step:\n\n    {step}\n\n"
                f"Add it to the SDK's steps file as described in {STEPS_DOCS_URL}"
            )
            if MISSING_STEPS == "xfail":
                pytest.xfail(message)
            pytest.fail(message, pytrace=False)
        if "error" in response:
            pytest.fail(f"The SDK raised an error in `{step}`:\n\n{response['error']}", pytrace=False)
        return response.get("client") if returns_client else response.get("result")

    def close(self) -> None:
        if self._process.poll() is None:
            assert self._process.stdin
            self._process.stdin.close()
            try:
                self._process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                self._process.kill()
