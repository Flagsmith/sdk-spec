# Go harness

Runs a Go SDK's [steps file](../../STEPS.md) for the spec runner, over the
[stdio protocol](../../HARNESS.md#protocol).

Go cannot call a function by name at runtime, so the harness is compiled for each steps file.
`build.go` parses the steps file with `go/parser`, finds each step-marker comment and the first
function after it, and generates a table mapping the step text to that function. It compiles the table
with `harness.go` into a single static binary. At runtime, `harness.go` uses `reflect` to convert the
JSON arguments to the function's parameter types and to call it.

## Steps file

- Put `steps.go` in its own module, `sdk-spec/go.mod`, with a `replace` directive pointing at the SDK
  source (`replace github.com/Flagsmith/<sdk> => ../`). A nested module keeps the steps file out of
  the published module and out of the SDK's `./...`.
- Use any package name except `main`. Step functions must be **exported**, top-level functions.
- Arguments are converted from JSON with `encoding/json`, so a parameter can be any type JSON decodes
  into. JSON values in `any` or `map[string]any` keep their types: strings, booleans, `nil`, and
  numbers as `int64` (integers) or `float64`.
- Return the step's result, optionally followed by an `error`. A non-nil error is reported as
  `"<type>: <message>"`, e.g. `flagsmith.FlagsmithClientError: …`. A panic is reported as
  `"panic: <type>: <value>"`. Results are serialised with `encoding/json`, so use `json` struct tags
  for the spec's field names.

```go
// When the application gets the environment flags
func GetEnvironmentFlags(client *flagsmith.Client) ([]Flag, error) {
	flags, err := client.GetEnvironmentFlags(context.Background())
	return asSpecFlags(flags), err
}
```

## Dockerfile

Build the harness with `go run build.go`, then copy the binary into an empty image:

```dockerfile
FROM docker.io/library/golang:1.25-alpine AS build
WORKDIR /sdk
COPY go.mod go.sum ./
COPY sdk-spec/go.mod sdk-spec/go.sum ./sdk-spec/
RUN cd sdk-spec && go mod download

COPY . .
COPY --from=harness . /harness
RUN go run /harness/build.go -o /out/harness sdk-spec/steps.go

FROM scratch
COPY --from=build /out/harness /harness
ENTRYPOINT ["/harness"]
```

`build.go` prints the steps it found to stderr, and fails the build if a marked function is not
exported.

## Running locally

```sh
go run harness/go/build.go -o /tmp/harness ../flagsmith-go-client/sdk-spec/steps.go
cd runner && SDK_COMMAND=/tmp/harness uv run pytest -v
```

`build.go` builds in a temporary `_harness*` directory next to the steps file and removes it afterwards.
