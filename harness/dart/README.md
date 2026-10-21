# Dart harness

Runs a Dart or Flutter SDK's [steps file](../../README.md#onboarding-an-sdk) for the spec runner, over the
[stdio protocol](../../HARNESS.md#protocol).

Dart cannot call a function by name at runtime, so the harness generates an entrypoint for each steps
file. `build.dart` reads `sdk-spec/steps.dart`, finds each step-marker comment and the first top-level
function after it, and writes an entrypoint that passes those functions to `harness.dart`, keyed by
step text. At runtime, `harness.dart` calls them with `Function.apply`.

## Steps file

- Step functions are public, top-level functions in `sdk-spec/steps.dart`, each below its step marker
  (`// Create the SDK client`, `// When …`). Import the SDK by its package name.
- A `Create the SDK client…` step returns the client. `When` steps take it first.
- Arguments arrive as decoded JSON: `String`, `int`, `double`, `bool`, `null`, and data tables as
  `Map<String, dynamic>`. Declare them with those types, e.g. `Map<String, Object?> traits`.
- Return a JSON-encodable value, or a `Future` of one.
- Let SDK errors propagate. They are reported as `"<type>: <message>"`, with the stack trace on stderr.
- `print` output goes to stderr, so the SDK may log freely.

```dart
// When the application gets the environment flags
Future<List<Map<String, Object?>>> getEnvironmentFlags(FlagsmithClient flagsmith) async =>
    asSpecFlags(await flagsmith.getFeatureFlags());
```

## Dockerfile

Generate the entrypoint inside the SDK's package, so that the steps file's `package:` imports resolve,
then compile it.

For a **Flutter** package, which needs `dart:ui`, build a kernel with `flutter build bundle` and run
it on `flutter_tester`, the headless engine `flutter test` uses:

```dockerfile
FROM ghcr.io/cirruslabs/flutter:3.44.0
WORKDIR /sdk
COPY . .
COPY --from=harness . /harness
RUN flutter pub get \
    && dart /harness/build.dart -o sdk-spec/harness_main.dart sdk-spec/steps.dart \
    && flutter build bundle --debug --target sdk-spec/harness_main.dart \
    && ln -s "$(find "$(dirname "$(readlink -f "$(command -v flutter)")")/cache/artifacts/engine" \
        -path '*/linux-*/flutter_tester' -print -quit)" /usr/local/bin/flutter_tester
ENTRYPOINT ["flutter_tester", "--non-interactive", "--disable-vm-service", "build/flutter_assets/kernel_blob.bin"]
```

For a **Dart** package, compile the entrypoint to an executable:

```dockerfile
FROM docker.io/library/dart:stable AS build
WORKDIR /sdk
COPY . .
COPY --from=harness . /harness
RUN dart pub get \
    && dart /harness/build.dart -o sdk-spec/harness_main.dart sdk-spec/steps.dart \
    && mkdir /out \
    && dart compile exe sdk-spec/harness_main.dart -o /out/harness

FROM scratch
# The dart image provides /runtime/: the minimal files an AOT-compiled executable needs.
COPY --from=build /runtime/ /
COPY --from=build /out/harness /harness
ENTRYPOINT ["/harness"]
```

`build.dart` prints the steps it found to stderr, and fails if a marked function is private.

## Running locally

Generate and compile the entrypoint in the SDK checkout, then point the runner at it:

```sh
cd <sdk checkout>
dart <spec>/harness/dart/build.dart -o sdk-spec/harness_main.dart sdk-spec/steps.dart
flutter build bundle --debug --target sdk-spec/harness_main.dart

cd <spec>/runner
SDK_COMMAND="$(dirname "$(readlink -f "$(command -v flutter)")")/cache/artifacts/engine/darwin-x64/flutter_tester \
  --non-interactive --disable-vm-service <sdk checkout>/build/flutter_assets/kernel_blob.bin" uv run pytest -v
```

For a Dart package, use `SDK_COMMAND="dart run <sdk checkout>/sdk-spec/harness_main.dart"` instead.
