# Writing an SDK's steps file

Each SDK repository has a short **steps file**, `sdk-spec/steps.<ext>`, written in the SDK's language.
It holds one function per SDK step: the parts of a scenario where the application uses the SDK.
Everything else (seeding Flagsmith, assertions) is done by the spec runner.

Mark each function with a line comment holding the step's exact text, directly above the function:

```python
# When the application gets the environment flags
def get_environment_flags(flagsmith):
    return as_spec_flags(flagsmith.get_environment_flags())
```

```go
// When the application gets the environment flags
func GetEnvironmentFlags(client *flagsmith.Client) ([]Flag, error) {
```

Keep the steps file readable: it doubles as a working, CI-checked example of how to use the SDK.

## Conventions

- **Arguments.** A step receives the client first, unless it creates one, followed by the step's
  `{placeholders}` in order. A data table comes last.
- **Values** are JSON values: string, number, boolean or `null`. Pass flag and trait values through with
  their types intact. Do not stringify them.
- **Errors.** Let SDK errors propagate. The harness reports them to the runner, and the scenario fails
  with the error message.
- **Missing steps.** A step the SDK has not implemented fails its scenario with "The SDK does not
  implement the step: …".

## Steps

### `Given an SDK client for the environment`

Arguments: `environmentKey` (a server-side environment key), `apiUrl` (e.g. `http://flagsmith:8000/api/v1/`).

Create an SDK client with default options and return it.

### `When the application gets the environment flags`

Arguments: `client`.

Return the environment's flags as a list of `{"feature": <name>, "enabled": <bool>, "value": <value>}`.

### `When the application gets the flags for identity "{identifier}" with traits:`

Arguments: `client`, `identifier`, `traits` (a map of trait key to value).

Return the identity's flags, in the same shape as above.

## Running the SDK under the spec

The SDK repository also has `sdk-spec/Dockerfile`, which builds the SDK **from source** and runs the
steps file under the spec's harness for its language. The harness is available as the `harness` build
context:

```dockerfile
COPY --from=harness harness.py /harness/harness.py
```

See [`HARNESS.md`](HARNESS.md) for how to run each harness.
