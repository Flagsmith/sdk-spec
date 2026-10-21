# Node.js (TypeScript) harness

Runs an SDK's `sdk-spec/steps.mts` under the spec. See [`HARNESS.md`](../../HARNESS.md) for the protocol.

It needs Node.js 22.18 or later, which runs TypeScript natively by stripping types. Nothing is compiled,
so steps files must use [erasable syntax](https://nodejs.org/api/typescript.html#type-stripping) only:
type annotations and `import type` are fine, but `enum` and constructor parameter properties are not.

## Using it in an SDK's Dockerfile

Install the SDK, built from source, so that the steps file can import it by its package name. Then copy
in the harness and the steps file, and run one on the other:

```dockerfile
COPY --from=harness harness.mts /harness/harness.mts
COPY sdk-spec/steps.mts ./sdk-spec/steps.mts

ENTRYPOINT ["node", "/harness/harness.mts", "sdk-spec/steps.mts"]
```

See `flagsmith-nodejs-client` for a full example.

## Writing steps

The harness reads the steps file for step markers, and calls the first function after each marker.
Step functions must be exported, as either a function declaration or a `const`:

```ts
// When the application gets the environment flags
export async function getEnvironmentFlags(flagsmith: Flagsmith) {
    return asSpecFlags(await flagsmith.getEnvironmentFlags());
}
```

- Step functions may be `async`: the harness awaits them.
- Arguments arrive as parsed JSON: strings, numbers, booleans, `null`, and plain objects for maps such as
  traits.
- Return any JSON-serialisable value. `undefined` is reported as `null`.
- Errors are reported as `<name>: <message>`, followed by the error's `cause`, if any. Let SDK errors
  propagate.
- Log freely. The harness redirects everything written to stdout, including by loggers such as pino that
  write to the file descriptor directly, to stderr.

## Running locally

From the spec's `runner/` directory, with the SDK built (e.g. `npm run build`) so the steps file can
import it:

```sh
SDK_COMMAND="node ../harness/nodejs/harness.mts <sdk checkout>/sdk-spec/steps.mts" uv run pytest -v
```
