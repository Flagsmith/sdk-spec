# Flagsmith SDK behavioural spec

A language-agnostic, versioned specification of how Flagsmith SDKs behave, written in Gherkin and
executed against every SDK.

- [`features/`](features) — the spec. One `.feature` file per behaviour.
- [`runner/`](runner) — executes the spec (pytest-bdd). Step definitions live here, written once for
  every SDK.
- [`compose.yml`](compose.yml) — the stack the spec runs against: a real Flagsmith API (pinned) and
  the SDK adapter under test.
- [`ADAPTER.md`](ADAPTER.md) — the HTTP protocol each SDK implements so the runner can drive it.
- [`.github/workflows/run-spec.yml`](.github/workflows/run-spec.yml) — reusable workflow SDKs call.
- [`.github/workflows/compatibility.yml`](.github/workflows/compatibility.yml) — runs the spec
  against every onboarded SDK on pull requests and nightly.

## How it works

```
 ┌────────┐  Admin API: seed & inspect   ┌───────────┐
 │ runner │ ───────────────────────────► │ Flagsmith │
 │        │                              └───────────┘
 │        │  adapter protocol   ┌─────────────┐  ▲
 │        │ ──────────────────► │ SDK adapter │──┘ SDK API calls
 └────────┘                     └─────────────┘
```

Each scenario gets its own Flagsmith project and environment. `Given` steps seed it through the
Admin API, `When` steps ask the SDK adapter to act as an application would, and `Then` steps assert
on what the SDK returned and on Flagsmith's resulting state.

## Writing scenarios

- Describe behaviour, not wire details: assert on what the application receives and what Flagsmith
  ends up with.
- Table cells and value arguments are JSON literals: `"text"`, `42`, `true`, `null`.
- Tag every feature with a capability (`@core`, …). SDKs select capabilities with a tag expression.
  Register new tags under `markers` in [`runner/pyproject.toml`](runner/pyproject.toml).
- Prefer reusing existing steps in [`runner/tests/conftest.py`](runner/tests/conftest.py). Adding a
  step that needs a new adapter command is a breaking change for SDKs: update `ADAPTER.md` and
  release a new minor (or major) version.

## Versioning

The spec is released as semver tags (`vX.Y.Z`). SDKs pin a tag, so spec changes never break an SDK
until it opts in.

- **Major** — changed behaviour, or a changed adapter protocol.
- **Minor** — new scenarios, tags, or optional adapter commands.
- **Patch** — wording and runner fixes.

Each release also pins the Flagsmith version in `compose.yml` that it was verified against.

## Onboarding an SDK

1. Add an adapter implementing [`ADAPTER.md`](ADAPTER.md), plus a Dockerfile that builds the SDK from
   source (default location: `spec-adapter/Dockerfile`). See `flagsmith-python-client` for a
   reference implementation.
2. Add a workflow:

   ```yaml
   name: SDK spec
   on:
     pull_request:
     push:
       branches: [main]
   jobs:
     sdk-spec:
       uses: Flagsmith/sdk-spec/.github/workflows/run-spec.yml@v0.1.0
       with:
         spec-ref: v0.1.0  # keep in sync with `uses:`
         tags: core        # optional: select capabilities
   ```

3. Let Renovate bump both refs together:

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

4. Add the SDK to the matrix in [`compatibility.yml`](.github/workflows/compatibility.yml).

## Running locally

```sh
# 1. Build the adapter image from the SDK repository
docker build -t sdk-spec-adapter -f spec-adapter/Dockerfile .   # in the SDK repo

# 2. Start Flagsmith and the adapter
docker compose up --detach --wait

# 3. Run the spec
cd runner
FLAGSMITH_SDK_URL=http://flagsmith:8000 uv run pytest -v
```

| Variable            | Default                 | Purpose                                         |
| ------------------- | ----------------------- | ----------------------------------------------- |
| `FLAGSMITH_URL`     | `http://localhost:8000` | Where the runner reaches Flagsmith              |
| `FLAGSMITH_SDK_URL` | `$FLAGSMITH_URL`        | Where the SDK adapter reaches Flagsmith         |
| `SDK_ADAPTER_URL`   | `http://localhost:8080` | Where the runner reaches the SDK adapter        |
| `FLAGSMITH_PORT`    | `8000`                  | Host port for Flagsmith (`compose.yml`)         |
| `SDK_ADAPTER_PORT`  | `8080`                  | Host port for the adapter (`compose.yml`)       |
| `SDK_ADAPTER_IMAGE` | `sdk-spec-adapter`      | Adapter image to run (`compose.yml`)            |
| `FLAGSMITH_IMAGE`   | pinned version          | Override the Flagsmith image (`compose.yml`)    |
