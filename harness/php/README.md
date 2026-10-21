# PHP harness

Runs a PHP SDK's `sdk-spec/steps.php` under the spec. See [`HARNESS.md`](../../HARNESS.md).

## Using it in an SDK's `sdk-spec/Dockerfile`

Install the SDK from source with Composer in the working directory, then copy in the harness and the
steps file:

```dockerfile
WORKDIR /sdk
COPY composer.json ./
COPY src ./src
RUN composer require guzzlehttp/guzzle --update-no-dev --optimize-autoloader --no-interaction

COPY --from=harness harness.php /harness/harness.php
COPY sdk-spec/steps.php ./sdk-spec/steps.php

ENTRYPOINT ["php", "/harness/harness.php", "sdk-spec/steps.php"]
```

The harness requires `vendor/autoload.php` from the working directory, if present, before loading the
steps file, so the steps file needs no `require` of its own. No `composer.json` is needed in `sdk-spec/`.

## Steps

Steps are plain functions, marked with a `//` or `#` comment holding the step's text:

```php
// When the application gets the flags for identity "{identifier}" with traits:
function getIdentityFlags(Flagsmith $flagsmith, string $identifier, object $traits): array
{
    return asSpecFlags($flagsmith->getIdentityFlags($identifier, $traits));
}
```

- The harness reads the steps file's source to map each marker to the next `function` declared after
  it, honouring a `namespace` declaration, and calls it by reflection.
- JSON objects arrive as `stdClass`, and JSON arrays as lists. A parameter typed `array` receives
  objects as associative arrays instead.
- Return any JSON-encodable value. Floats keep their fractional part (`1.0`).
- Throw to fail a step: the harness reports `<exception class>: <message>`, with the stack trace on
  stderr.
- Anything the SDK or steps print, and PHP warnings, go to stderr, so stdout stays clean.

## Running locally

Build the SDK image as in the [README](../../README.md#running-locally), with
`--build-context harness=<sdk-spec>/harness/php`. To run without Docker, install the SDK's dependencies
(including an HTTP client such as Guzzle) and start the harness from the SDK repository root, so that it
finds `vendor/autoload.php`:

```sh
# In runner/
SDK_COMMAND="sh -c 'cd <sdk> && php <sdk-spec>/harness/php/harness.php sdk-spec/steps.php'" uv run pytest -v
```
