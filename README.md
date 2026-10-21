# Flagsmith SDK behavioural spec

A language-agnostic, versioned specification of how Flagsmith SDKs behave, written in Gherkin and
executed against every SDK.

- [`features/`](features) — the spec. One `.feature` file per behaviour.
- [`runner/`](runner) — executes the spec (pytest-bdd). Step definitions live here, written once for
  every SDK.
- [`compose.yml`](compose.yml) — the Flagsmith API (pinned) the spec runs against.
- [`harness/`](harness) — one harness per language, running an SDK's steps file
  ([`HARNESS.md`](HARNESS.md)).
- [`.github/workflows/run-spec.yml`](.github/workflows/run-spec.yml) — reusable workflow SDKs call.
- [`.github/workflows/compatibility.yml`](.github/workflows/compatibility.yml) — runs the spec
  against every onboarded SDK on pull requests and nightly.

## How it works

```
 ┌────────┐  Admin API: seed & inspect        ┌───────────┐
 │ runner │ ────────────────────────────────► │ Flagsmith │
 │        │                                   └───────────┘
 │        │  stdio  ┌──────────────────────────────┐  ▲
 │        │ ──────► │ harness ─► SDK steps file    │──┘ SDK API calls
 └────────┘         │ (SDK image, built from source)│
                    └──────────────────────────────┘
```

Each scenario gets its own Flagsmith project and environment, and the steps split three ways:

- **`Given`** steps set up Flagsmith through the Admin API. The runner implements them.
- **`When`** steps are the application using the SDK. Every SDK implements every `When` step in
  its steps file.
- **`Then`** steps check what the SDK returned and Flagsmith's resulting state. The runner
  implements them.

The feature files are therefore the whole contract: the `When` steps in `features/` are the steps
SDKs implement. The runner creates the scenario's SDK client just before its first `When` step.

## Writing scenarios

- Describe behaviour, not wire details: assert on what the application receives and what Flagsmith
  ends up with.
- Table cells and value arguments are JSON literals: `"text"`, `42`, `true`, `null`.
- Tag every feature with a capability (`@core`, …). SDKs select capabilities with a tag expression.
  Register new tags under `markers` in [`runner/pyproject.toml`](runner/pyproject.toml).
- Prefer reusing existing steps in [`runner/tests/conftest.py`](runner/tests/conftest.py).
- A new `When` step is registered with one `sdk_step(...)` line in the runner. It is a minor
  version: SDKs that have not implemented it go red with "The SDK does not implement the step: …".
  Rewording a `When` step is a major version.

## Versioning

The spec is released as semver tags (`vX.Y.Z`). SDKs pin a tag, so spec changes never break an SDK
until it opts in.

- **Major** — changed behaviour, reworded `When` steps, or a changed harness protocol.
- **Minor** — new scenarios, tags or `When` steps.
- **Patch** — wording and runner fixes.

Each release also pins the Flagsmith version in `compose.yml` that it was verified against.

## Onboarding an SDK

1. Add `sdk-spec/steps.<ext>` to the SDK repository: a function creating the SDK client, and one
   function per `When` step in [`features/`](features). Mark each with a comment directly above it:

   ```python
   # Create the SDK client
   def create_client(environment_key, api_url):
       return Flagsmith(environment_key=environment_key, api_url=api_url)


   # When the application gets the environment flags
   def get_environment_flags(flagsmith):
       return as_spec_flags(flagsmith.get_environment_flags())
   ```

   - `Create the SDK client` receives a server-side environment key and the Flagsmith API URL, and
     returns a client created with default options.
   - A `When` step receives the client, then the step's placeholders in order, then its data table.
     A `<key> | value` table arrives as a map, e.g. `{"plan": "premium", "age": 30}`.
   - Values are JSON values. Pass flag and trait values through with their types intact.
   - Steps that get flags return a list of `{"feature": …, "enabled": …, "value": …}`.
   - Let SDK errors propagate: the scenario fails with the error.

   Keep it to SDK calls. The steps file doubles as a working, CI-checked usage example.

2. Add `sdk-spec/Dockerfile`, which builds the SDK from source and runs the steps file under the
   language's harness. See `harness/<language>/README.md`. If the language has no harness yet, add
   one (see [`HARNESS.md`](HARNESS.md)).

3. Add a workflow:

   ```yaml
   name: SDK spec
   on:
     pull_request:
     push:
       branches: [main]
   jobs:
     sdk-spec:
       uses: Flagsmith/sdk-spec/.github/workflows/run-spec.yml@v0.3.0
       with:
         spec-ref: v0.3.0  # keep in sync with `uses:`
         language: python
         tags: core        # optional: select capabilities
   ```

4. Let Renovate bump both refs together:

   ```json
   {
     "customManagers": [
       {
         "customType": "regex",
         "managerFilePatterns": ["/^\\.github/workflows/sdk-spec\\.yml$/"],
         "matchStrings": ["spec-ref: (?<currentValue>v[\\d.]+)"],
         "depNameTemplate": "Flagsmith/sdk-spec",
         "datasourceTemplate": "github-tags"
       }
     ],
     "packageRules": [
       { "matchPackageNames": ["Flagsmith/sdk-spec"], "groupName": "SDK spec" }
     ]
   }
   ```

5. Add the SDK to the matrix in [`compatibility.yml`](.github/workflows/compatibility.yml).

## Running locally

```sh
# 1. Start Flagsmith
docker compose up --detach --wait

# 2. Build the SDK image, in the SDK repository
docker build -t sdk-spec-sdk -f sdk-spec/Dockerfile --build-context harness=<path to sdk-spec>/harness/python .

# 3. Run the spec
cd runner
FLAGSMITH_SDK_URL=http://flagsmith:8000 \
SDK_COMMAND="docker run -i --rm --network sdk-spec_default sdk-spec-sdk" \
uv run pytest -v
```

| Variable            | Default                 | Purpose                                         |
| ------------------- | ----------------------- | ----------------------------------------------- |
| `SDK_COMMAND`       | (required)              | Starts the SDK under its harness                |
| `FLAGSMITH_URL`     | `http://localhost:8000` | Where the runner reaches Flagsmith              |
| `FLAGSMITH_SDK_URL` | `$FLAGSMITH_URL`        | Where the SDK reaches Flagsmith                 |
| `FLAGSMITH_PORT`    | `8000`                  | Host port for Flagsmith (`compose.yml`)         |
| `FLAGSMITH_IMAGE`   | pinned version          | Override the Flagsmith image (`compose.yml`)    |

`SDK_COMMAND` can be any command, so you can also run a harness straight against an SDK checkout,
without Docker, e.g. `python ../harness/python/harness.py ../../flagsmith-python-client/sdk-spec/steps.py`.
