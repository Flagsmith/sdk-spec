# Language harnesses

A harness runs an SDK's [steps file](STEPS.md) on behalf of the spec runner. There is one harness per
language, in `harness/<language>/`. SDK repositories never contain harness code.

| Language | Harness                                        | Run as                                          |
| -------- | ---------------------------------------------- | ----------------------------------------------- |
| Python   | [`harness/python`](harness/python/harness.py)  | `python /harness/harness.py sdk-spec/steps.py`  |

## Finding steps

A step is marked by a line comment whose text starts with `Given `, `When ` or `Then `. The marked
function is the first function defined after the comment. The comment text is the step's identity, and
it must match the runner's step text exactly.

Harnesses for dynamic or reflective languages can find steps at runtime. Harnesses for other languages
can generate a dispatch table at build time.

## Protocol

The runner starts the harness, for example `docker run -i --rm <sdk image>`, and exchanges JSON
messages with it, one per line, over stdin and stdout. Every request has an `id`, and the matching
response repeats it. Any stdout line that is not a response is treated as SDK output and forwarded to
the runner's stderr, so SDKs may log freely. Remember to flush stdout after each response.

### `hello`

```json
{"id": 1, "command": "hello"}
{"id": 1, "steps": ["Given an SDK client for the environment", "..."]}
```

`steps` lists every step the steps file implements.

### `step`

```json
{"id": 2, "command": "step", "step": "Given an SDK client for the environment", "args": ["ser.abc", "http://flagsmith:8000/api/v1/"], "client": null, "returnsClient": true}
{"id": 2, "client": "1"}

{"id": 3, "command": "step", "step": "When the application gets the environment flags", "args": [], "client": "1", "returnsClient": false}
{"id": 3, "result": [{"feature": "banner", "enabled": true, "value": "welcome"}]}
```

- If `client` is set, pass the client stored under that handle as the first argument, followed by `args`.
- If `returnsClient` is true, store the step's return value and respond with a new handle as `client`.
  Otherwise respond with the return value, as JSON, under `result`.
- If the step is not implemented, respond with `{"id": …, "missing": true}`.
- If the step raises, respond with `{"id": …, "error": "<type>: <message>"}`.

The harness exits when stdin closes.
