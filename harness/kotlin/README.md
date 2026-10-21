# Kotlin harness

Runs a Kotlin SDK's [steps file](../../README.md#onboarding-an-sdk) for the spec runner, speaking the
[harness protocol](../../HARNESS.md) over stdin and stdout.

## Finding steps

The steps file is `sdk-spec/steps.kt`. At startup, the harness reads that source, maps each
step-marker comment to the name of the top-level function declared below it, and invokes the
function by reflection on the compiled file facade class: `StepsKt`, or the `@file:JvmName` if
there is one, plus the `package` declaration if there is one.

## Writing steps

- Steps are top-level functions of any visibility, one per name (no overloads).
- Arguments are converted from JSON to the parameter types with Gson, so declare them as you
  would use them: `String` for placeholders, `Map<String, Any>` for data tables. Integers arrive
  as `Long` and decimals as `Double`.
- Return any value Gson can serialise. Flag values keep their JSON types, and nulls are kept.
- Steps are called synchronously: wait for asynchronous SDK calls before returning.
- Let SDK exceptions propagate. The harness reports them as `"<SimpleClassName>: <message>"` and
  prints the stack trace to stderr.
- Anything written to `System.out` is redirected to stderr, so the SDK may log freely.

```kotlin
// When the application gets the environment flags
fun getEnvironmentFlags(flagsmith: Flagsmith) =
    await { flagsmith.getFeatureFlags(result = it) }.asSpecFlags()
```

## Using it from `sdk-spec/Dockerfile`

The harness needs Gson (`com.google.code.gson:gson` 2.10 or later) on the classpath. Compile
`Harness.kt` together with the steps file and the SDK built from source, for example with a Gradle
`application` build in `sdk-spec/` whose main class is `Harness`:

```kotlin
sourceSets.main {
    kotlin.srcDirs("../src/main/kotlin", providers.gradleProperty("harness"))
}

tasks.compileKotlin {
    source("steps.kt")
}

application {
    mainClass.set("Harness")
}
```

```dockerfile
COPY --from=harness Harness.kt /harness/Harness.kt
RUN gradle --no-daemon -p sdk-spec installDist -Pharness=/harness
```

The harness reads the steps source at runtime, so ship `sdk-spec/steps.kt` in the final image too:

```dockerfile
ENTRYPOINT ["app/bin/sdk-spec", "sdk-spec/steps.kt"]
```

See `flagsmith-kotlin-android-client` for a complete example.

## Running locally

```sh
docker build -t sdk-spec-sdk -f sdk-spec/Dockerfile --build-context harness=<path to sdk-spec>/harness/kotlin .
echo '{"id": 1, "command": "hello"}' | docker run -i --rm sdk-spec-sdk
```

Or without Docker, after building as above:

```sh
sdk-spec/build/install/sdk-spec/bin/sdk-spec sdk-spec/steps.kt
```
