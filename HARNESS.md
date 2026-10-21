# Language harnesses

A harness runs an SDK's steps file for the spec runner. There is one per language in
`harness/<language>/`, and its `README.md` shows SDKs how to use it.

| Language | Harness                            |
| -------- | ---------------------------------- |
| .NET     | [`harness/dotnet`](harness/dotnet) |
| Dart     | [`harness/dart`](harness/dart)     |
| Elixir   | [`harness/elixir`](harness/elixir) |
| Go       | [`harness/go`](harness/go)         |
| Java     | [`harness/java`](harness/java)     |
| Kotlin   | [`harness/kotlin`](harness/kotlin) |
| Node.js  | [`harness/nodejs`](harness/nodejs) |
| PHP      | [`harness/php`](harness/php)       |
| Python   | [`harness/python`](harness/python) |
| Ruby     | [`harness/ruby`](harness/ruby)     |
| Rust     | [`harness/rust`](harness/rust)     |
| Swift    | [`harness/swift`](harness/swift)   |

## Finding steps

- A step marker is a line comment holding either `Create the SDK client` or a step starting with
  `When `, e.g. `When the application gets the environment flags`.
- The marked function is the first function defined after the marker.
- The marker text identifies the step, and must match the runner's text exactly.

Find steps at runtime where the language allows it. Otherwise, generate a dispatch table at build time
inside the SDK's Docker build (Go does this, for example).

## Protocol

The runner starts the SDK image (`docker run -i --rm <image>`) and exchanges JSON messages with the
harness over stdin and stdout, one per line. Each request has an `id`, and its response repeats it.

- Flush stdout after each response.
- Keep SDK output off stdout where you can: redirect it to stderr. The runner forwards any stdout line
  that is not a response to its stderr, but it is safer not to rely on that.
- Exit when stdin closes.

### `hello`

```json
{"id": 1, "command": "hello"}
{"id": 1, "steps": ["Create the SDK client", "When the application gets the environment flags"]}
```

`steps` lists every step the steps file implements.

### `step`

```json
{"id": 2, "command": "step", "step": "Create the SDK client", "args": ["ser.abc", "http://flagsmith:8000/api/v1/"], "client": null, "returnsClient": true}
{"id": 2, "client": "1"}

{"id": 3, "command": "step", "step": "When the application gets the environment flags", "args": [], "client": "1", "returnsClient": false}
{"id": 3, "result": [{"feature": "banner", "enabled": true, "value": "welcome"}]}
```

- **`client` is set:** pass the client stored under that handle as the first argument, then `args`.
- **`returnsClient` is true:** store the return value and respond with a new handle as `client`.
  Otherwise, respond with the return value under `result`.
- **Step not implemented:** respond with `{"id": …, "missing": true}`.
- **Step raises or returns an error:** respond with `{"id": …, "error": "<type>: <message>"}`.

## Adding a harness

Follow [`harness/python`](harness/python) as a reference. Add a `README.md` covering:

- the SDK's `sdk-spec/Dockerfile`: what to `COPY --from=harness` and what to run;
- the steps-file conventions for that language: function signatures and how to return errors;
- how to run the harness locally without Docker.
