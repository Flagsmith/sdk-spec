# Ruby harness

Runs a Ruby SDK's `sdk-spec/steps.rb` under the spec. See [`HARNESS.md`](../../HARNESS.md) for the
protocol and [`STEPS.md`](../../STEPS.md) for the steps.

## In an SDK's `sdk-spec/Dockerfile`

Install the SDK from source, then copy in `harness.rb` and run it on the steps file. For a full
example, see `sdk-spec/Dockerfile` in `flagsmith-ruby-client`.

```dockerfile
FROM docker.io/library/ruby:3.3-slim
WORKDIR /sdk
COPY . .
RUN gem build flagsmith.gemspec --output flagsmith.gem && gem install --no-document flagsmith.gem

COPY --from=harness harness.rb /harness/harness.rb
ENTRYPOINT ["ruby", "/harness/harness.rb", "sdk-spec/steps.rb"]
```

The harness only uses the standard library (`json`), so it needs no gems of its own.

## Steps file conventions

- Steps are top-level methods (`def create_client(environment_key, api_url)`), each directly below its
  step-marker comment. The harness `load`s the steps file, so it should `require` the SDK itself.
- Arguments arrive as parsed JSON: strings, and data tables as `Hash`es with `String` keys. Splat a
  table into keyword arguments with `**traits` where the SDK expects them.
- Return plain Ruby values (`Array`, `Hash`, `String`, `Integer`, `Float`, `true`, `false`, `nil`).
  Symbol keys are fine: they are serialised as strings.
- Errors: just let them raise. Any `StandardError` is reported as `"<class>: <message>"`, with its
  backtrace written to stderr.
- Write anything you like to stdout, for example the SDK's default `Logger.new($stdout)`: the harness
  keeps the real stdout for protocol responses and sends everything else to stderr.

## Running locally

Without Docker, from the runner directory, with the SDK's dependencies installed and its `lib` on the
load path:

```sh
SDK_COMMAND="ruby -I ../../flagsmith-ruby-client/lib ../harness/ruby/harness.rb ../../flagsmith-ruby-client/sdk-spec/steps.rb" \
uv run pytest -v
```

With Docker, in the SDK repository:

```sh
docker build -t sdk-spec-sdk -f sdk-spec/Dockerfile --build-context harness=<path to sdk-spec>/harness/ruby .
```

Then run the spec with `SDK_COMMAND="docker run -i --rm --network sdk-spec_default sdk-spec-sdk"`.
