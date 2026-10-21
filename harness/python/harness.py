"""
Python harness for the Flagsmith SDK behavioural spec. See HARNESS.md.

Usage: python harness.py path/to/steps.py
"""

import importlib.util
import json
import re
import sys
import traceback
from pathlib import Path
from typing import Any, Callable

MARKER = re.compile(r"^\s*#+\s*((?:Given|When|Then) .+?)\s*$")
FUNCTION = re.compile(r"^\s*(?:async\s+)?def\s+(\w+)")


def load_steps(path: Path) -> dict[str, Callable[..., Any]]:
    spec = importlib.util.spec_from_file_location("sdk_spec_steps", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    steps: dict[str, Callable[..., Any]] = {}
    pending: str | None = None
    for line in path.read_text().splitlines():
        if marker := MARKER.match(line):
            pending = marker[1]
        elif pending and (function := FUNCTION.match(line)):
            steps[pending] = getattr(module, function[1])
            pending = None
    return steps


def main() -> None:
    steps = load_steps(Path(sys.argv[1]))
    clients: dict[str, Any] = {}
    out = sys.stdout

    for line in sys.stdin:
        request = json.loads(line)
        response: dict[str, Any] = {"id": request["id"]}
        if request["command"] == "hello":
            response["steps"] = list(steps)
        elif (step := steps.get(request["step"])) is None:
            response["missing"] = True
        else:
            args = request["args"]
            if request.get("client") is not None:
                args = [clients[request["client"]], *args]
            try:
                result = step(*args)
            except Exception as e:  # noqa: BLE001 - reported to the runner
                traceback.print_exc()
                response["error"] = f"{type(e).__name__}: {e}"
            else:
                if request.get("returnsClient"):
                    response["client"] = str(len(clients) + 1)
                    clients[response["client"]] = result
                else:
                    response["result"] = result
        out.write(json.dumps(response) + "\n")
        out.flush()


if __name__ == "__main__":
    main()
