# Swift harness

Runs a Swift SDK's [steps file](../../README.md#onboarding-an-sdk) for the spec runner, over the
[stdio protocol](../../HARNESS.md#protocol).

Swift cannot call a function by name at runtime, so the harness compiles the steps file in. The
`GenerateSteps` build tool plugin runs [`StepsGenerator`](StepsGenerator) on the steps file, which
finds each step marker and the first function declared after it, skipping comments, and generates a
table mapping the step text to that function. [`Sources/Harness`](Sources/Harness) speaks the protocol
over stdin and stdout, decoding each JSON argument to the function's parameter type and encoding its
result.

`StepsGenerator` is a package of its own, so its tests run without an SDK:
`swift test --package-path harness/swift/StepsGenerator`.

## The SDK's `sdk-spec/`

- `steps.swift`: the steps file.
- `Package.swift`: makes the steps file a library named `SDKSpecSteps`, depending on the SDK by path.
  The harness checks the SDK out as `/sdk`, so refer to the SDK package as `sdk`:

  ```swift
  // swift-tools-version:5.9

  import PackageDescription

  let package = Package(
      name: "sdk-spec",
      platforms: [.macOS(.v10_15)],
      products: [
          .library(name: "SDKSpecSteps", targets: ["SDKSpecSteps"]),
      ],
      dependencies: [
          .package(path: ".."),
      ],
      targets: [
          .target(
              name: "SDKSpecSteps",
              dependencies: [.product(name: "FlagsmithClient", package: "sdk")],
              path: ".",
              exclude: ["Dockerfile"],
              sources: ["steps.swift"]
          ),
      ]
  )
  ```

- `Dockerfile`: copies the SDK to `/sdk` and the harness to `/harness`, then builds the harness:

  ```dockerfile
  FROM docker.io/library/swift:6.1-noble AS build
  WORKDIR /sdk
  COPY . .
  COPY --from=harness . /harness
  RUN swift build --package-path /harness --configuration release \
      && cp "$(swift build --package-path /harness --configuration release --show-bin-path)/sdk-spec-harness" /usr/local/bin/

  FROM docker.io/library/swift:6.1-noble-slim
  COPY --from=build /usr/local/bin/sdk-spec-harness /usr/local/bin/
  ENTRYPOINT ["sdk-spec-harness"]
  ```

  The harness depends on the steps package at `../sdk/sdk-spec`, so the SDK must be at `/sdk`.

## Step functions

- Step functions are `public`, top-level functions, each directly below its step marker comment
  (`// When …`). Give each a unique name: the table refers to them by name.
- `When` steps take the client first. A `Create the SDK client…` function takes no client and
  returns one. The client can be any type.
- Other parameters take any `Decodable` type, e.g. `String` or `[String: V]` for a data table.
- Return any `Encodable` type. Functions can be `async` and can `throw`. A thrown error is reported as
  `"<type>: <message>"`, e.g. `FlagsmithClient.FlagsmithError: …`, using `errorDescription` for a
  `LocalizedError`.
- Steps run off the main thread, and the main thread serves the main dispatch queue, so SDKs can call
  back on it.

```swift
// When the application gets the environment flags
public func getEnvironmentFlags(_ client: Client) async throws -> [SpecFlag] {
    try await client.flagsmith.getFeatureFlags().map(SpecFlag.init)
}
```

## Running locally

The harness expects the SDK checkout next to it, as `../sdk`:

```sh
mkdir /tmp/swift-harness
cp -r harness/swift /tmp/swift-harness/harness
ln -s <path to SDK> /tmp/swift-harness/sdk
swift build --package-path /tmp/swift-harness/harness

cd runner
SDK_COMMAND=/tmp/swift-harness/harness/.build/debug/sdk-spec-harness uv run pytest -v
```
