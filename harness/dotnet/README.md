# .NET (C#) harness

Runs a C# [steps file](../../STEPS.md) under the spec. See [`HARNESS.md`](../../HARNESS.md) for the
protocol.

`Harness.csproj` compiles the harness together with the SDK's steps file and a reference to the SDK
project, so the SDK repository needs no project file of its own. At runtime the harness reads the
steps file's source to map each marker comment to the name of the method below it, then calls that
method by reflection.

## In an SDK's `sdk-spec/Dockerfile`

Copy the whole harness directory, publish it with the steps file and the SDK project, and run the
published harness on the steps file:

```dockerfile
FROM mcr.microsoft.com/dotnet/sdk:10.0 AS build
WORKDIR /sdk
COPY . .
COPY --from=harness . /harness
RUN dotnet publish /harness/Harness.csproj --configuration Release --output /app \
    -p:StepsFile=/sdk/sdk-spec/steps.cs \
    -p:SdkProject=/sdk/MySdk/MySdk.csproj

FROM mcr.microsoft.com/dotnet/runtime:10.0
WORKDIR /sdk
COPY --from=build /app /harness
COPY sdk-spec/steps.cs ./sdk-spec/steps.cs
ENTRYPOINT ["dotnet", "/harness/Harness.dll", "sdk-spec/steps.cs"]
```

The steps file is needed at runtime too, because the harness reads the markers from its source.

## Steps file conventions

- Steps are `static` methods, in any class, with unique names. Put the marker comment directly above
  the method's declaration line (`// When the application gets the environment flags`).
- The project has implicit usings and nullable reference types enabled.
- Parameters are converted from JSON to their declared types. Use `string` for text and
  `Dictionary<string, object?>` for data tables: JSON values arrive as `string`, `long`, `double`,
  `bool` or `null`.
- Return any value; it is serialised with `System.Text.Json` web defaults, so record properties are
  camelCased. Anonymous types (`new { feature = …, enabled = …, value = … }`) are serialised as
  written. A step may be `async` and return `Task<T>`; the harness awaits it.
- Let exceptions propagate: they are reported as `"<exception type>: <message>"`, with the stack
  trace on stderr.
- Anything written to the console goes to stderr, so stdout carries only the protocol.

## Running locally

Build the SDK image from the SDK repository and point the runner at it:

```sh
docker build -t sdk-spec-sdk -f sdk-spec/Dockerfile --build-context harness=<path to sdk-spec>/harness/dotnet .
cd <path to sdk-spec>/runner
FLAGSMITH_SDK_URL=http://flagsmith:8000 \
SDK_COMMAND="docker run -i --rm --network sdk-spec_default sdk-spec-sdk" \
uv run pytest -v
```

Or, with a local .NET SDK, without Docker:

```sh
dotnet publish harness/dotnet/Harness.csproj --output /tmp/harness \
  -p:StepsFile=<SDK>/sdk-spec/steps.cs -p:SdkProject=<SDK>/MySdk/MySdk.csproj
SDK_COMMAND="dotnet /tmp/harness/Harness.dll <SDK>/sdk-spec/steps.cs" uv run pytest -v
```
