# Elixir harness

Runs an Elixir SDK's `sdk-spec/steps.exs` under the spec. See [`HARNESS.md`](../../HARNESS.md).

The harness is a script, `harness.exs`, run with `mix run` inside the SDK's own Mix project, so the
steps file can call the SDK as an application would. It uses [Jason](https://hex.pm/packages/jason)
for JSON, so the SDK must depend on it.

## Finding steps

The harness loads the steps file with `Code.require_file/1`, then scans its source for step-marker
comments. The first `def` after a marker is the step, called with `apply/3` on whichever module
defined in the steps file exports it. Private functions (`defp`) are free to use as helpers.

## SDK Dockerfile

Build the SDK from source in `MIX_ENV=prod`, then copy in the harness and the steps file:

```dockerfile
COPY --from=harness harness.exs /harness/harness.exs
COPY sdk-spec/steps.exs ./sdk-spec/steps.exs

ENTRYPOINT ["mix", "run", "--no-compile", "--no-deps-check", "/harness/harness.exs", "sdk-spec/steps.exs"]
```

`--no-compile` and `--no-deps-check` keep start-up fast, since everything was compiled at build time.
See `flagsmith-elixir-client` for a full example.

## Steps

Define the steps as public functions of a module in `steps.exs`:

```elixir
defmodule SDKSpec.Steps do
  # When the application gets the environment flags
  def get_environment_flags(client) do
    with {:ok, flags} <- Flagsmith.Client.get_environment_flags(client) do
      {:ok, as_spec_flags(flags)}
    end
  end
end
```

- **Arguments** arrive as decoded JSON: strings, numbers, booleans, `nil`, lists, and maps with
  string keys. A client is whatever the client-creating step returned.
- **Return** a value, `{:ok, value}` or `{:error, reason}`, whichever is idiomatic for the SDK call.
  The harness unwraps `{:ok, value}` and encodes the value with Jason, so atom-keyed maps are fine.
- **Errors.** `{:error, reason}` is reported as `error: <inspect(reason)>`, or as `<Module>: <message>`
  when `reason` is an exception. Raised exceptions are reported as `<Module>: <message>`, with the
  stack trace on stderr. Throws and exits are reported as `throw: …` and `exit: …`.
- **Output.** The harness owns stdout. Anything the SDK prints, including `Logger` output, goes to
  stderr.

## Running locally

From the SDK repository, with Elixir installed, compile first so that Mix prints nothing to stdout
while the harness runs:

```sh
export MIX_ENV=prod
mix deps.get && mix compile
mix run --no-compile <path to sdk-spec>/harness/elixir/harness.exs sdk-spec/steps.exs
```

then use it as the runner's `SDK_COMMAND` (with absolute paths), or type requests into it:

```json
{"id": 1, "command": "hello"}
```
