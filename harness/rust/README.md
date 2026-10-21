# Rust harness

Runs a Rust SDK's [steps file](../../README.md#onboarding-an-sdk) under the spec. See [`HARNESS.md`](../../HARNESS.md).

Rust cannot call a function by name at runtime, so the harness compiles the steps file in.
[`build.rs`](build.rs) finds the step markers in `sdk-spec/steps.rs` and generates a dispatch table:
one function per step that converts the JSON arguments, calls the marked function and converts its
return value. [`src/main.rs`](src/main.rs) speaks the protocol over stdin and stdout.

## The SDK's `sdk-spec/`

- `steps.rs` — the steps file.
- `Cargo.toml` — makes the steps file a library crate named `sdk-spec`, depending on the SDK by path:

  ```toml
  [package]
  name = "sdk-spec"
  version = "0.0.0"
  edition = "2021"
  publish = false

  [lib]
  path = "steps.rs"

  [dependencies]
  flagsmith = { path = ".." }
  ```

- `Dockerfile` — copies the SDK to `/sdk` and the harness to `/harness`, then builds the harness:

  ```dockerfile
  FROM docker.io/library/rust:1-slim-bookworm AS build
  WORKDIR /sdk
  COPY . .
  COPY --from=harness . /harness
  # Optional: resolve dependencies to the versions the SDK is tested with.
  COPY Cargo.lock /harness/Cargo.lock
  RUN cargo build --release --manifest-path /harness/Cargo.toml

  FROM docker.io/library/debian:bookworm-slim
  # Plus anything the SDK needs at runtime, e.g. CA certificates.
  COPY --from=build /harness/target/release/sdk-spec-harness /usr/local/bin/
  ENTRYPOINT ["sdk-spec-harness"]
  ```

  The harness depends on the steps crate at `../sdk/sdk-spec`, so the SDK must be at `/sdk`.

## Step functions

- Step functions are `pub fn`, marked with a `//` comment holding the step's text.
- `When` steps take the client first, as `&Client` or `&mut Client`. A `Create the SDK client…`
  function takes no client and returns one.
- Other parameters take any type that deserialises from the JSON argument, e.g. `String` or
  `HashMap<String, V>` for a data table.
- Return any type that serialises to JSON, or a `Result` of one. A `Result` is recognised by its
  return type's name, so write `Result<…>` or `some::path::Result<…>`, not an alias. `Err(e)` is
  reported as `"<type of e>: <e>"`, and a panic as `"panic: <message>"`.

```rust
// When the application gets the environment flags
pub fn get_environment_flags(flagsmith: &Flagsmith) -> Result<Vec<SpecFlag>, Error> {
    flagsmith.get_environment_flags().map(as_spec_flags)
}
```

## Running locally

The harness expects the SDK checkout next to it, as `../sdk`:

```sh
mkdir /tmp/rust-harness
cp -r harness/rust /tmp/rust-harness/harness
ln -s <path to SDK> /tmp/rust-harness/sdk
cargo build --release --manifest-path /tmp/rust-harness/harness/Cargo.toml

cd runner
SDK_COMMAND=/tmp/rust-harness/harness/target/release/sdk-spec-harness uv run pytest -v
```
