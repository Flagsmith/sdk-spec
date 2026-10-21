# Java harness

Runs a Java SDK's [steps file](../../README.md#onboarding-an-sdk) for the spec runner, speaking the
[harness protocol](../../HARNESS.md) over stdin and stdout.

## Finding steps

The steps file is a Java class, `sdk-spec/Steps.java`. At startup, the harness reads that source,
maps each step-marker comment to the name of the `static` method declared below it, and invokes
the method by reflection on the compiled class. The class name comes from the file name, plus the
`package` declaration if there is one.

## Writing steps

- Steps are `static` methods of any visibility, one per name (no overloads).
- Arguments are converted from JSON to the parameter types with Jackson, so declare them as you
  would use them: `String` for placeholders, `Map<String, Object>` for data tables.
- Return any value Jackson can serialise. Flag values keep their JSON types.
- Declare and let SDK exceptions propagate (`throws FlagsmithClientError`). The harness reports
  them as `"<SimpleClassName>: <message>"` and prints the stack trace to stderr.
- Anything written to `System.out` is redirected to stderr, so the SDK may log freely.

```java
// When the application gets the environment flags
static List<SpecFlag> getEnvironmentFlags(FlagsmithClient flagsmith)
    throws FlagsmithClientError {
  return asSpecFlags(flagsmith.getEnvironmentFlags());
}
```

## Using it from `sdk-spec/Dockerfile`

The harness needs Jackson (`jackson-databind`) on the classpath, as Java SDKs already depend on it.
Build the SDK from source, collect its runtime dependencies, then compile the harness together with
the steps file. No build file is needed in `sdk-spec/`:

```dockerfile
RUN mvn package dependency:copy-dependencies -DincludeScope=runtime -DoutputDirectory=target/lib ...
COPY --from=harness Harness.java /harness/Harness.java
COPY sdk-spec/Steps.java ./sdk-spec/Steps.java
RUN javac -cp "target/lib/*" -d target/classes-spec /harness/Harness.java sdk-spec/Steps.java
```

The harness reads the steps source at runtime, so ship `sdk-spec/Steps.java` in the final image too:

```dockerfile
ENTRYPOINT ["java", "-cp", "classes:lib/*", "Harness", "sdk-spec/Steps.java"]
```

See `flagsmith-java-client` for a complete example.

## Running locally

```sh
docker build -t sdk-spec-sdk -f sdk-spec/Dockerfile --build-context harness=<path to sdk-spec>/harness/java .
echo '{"id": 1, "command": "hello"}' | docker run -i --rm sdk-spec-sdk
```

Or without Docker, after compiling as above:

```sh
java -cp "target/classes-spec:target/lib/*" Harness sdk-spec/Steps.java
```
