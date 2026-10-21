# SDK adapter protocol

Each SDK repository provides an **adapter**: a small HTTP service that wraps the SDK and lets the spec
runner drive it. The runner owns a mock Flagsmith API. It tells the adapter where that API is, makes the
adapter call the SDK, and then asserts on both the SDK's HTTP traffic and the values the SDK returned.

The adapter is shipped as a Docker image built from a Dockerfile in the SDK repository (by default
`spec-adapter/Dockerfile`). It must build the SDK **from source**, so that the spec is run against the
code under test, not a published release.

## Conventions

- The adapter listens on the port given by the `PORT` environment variable (default `8080`).
- All request and response bodies are JSON.
- Flag and trait values are JSON values (string, number, boolean or `null`) and must be passed through
  with their type intact. Do not stringify them.
- If the SDK raises an error, respond with `500` and `{"error": "<message>"}`.

## Endpoints

### `GET /health`

Returns `200` once the adapter is ready to accept commands. The runner polls this endpoint before
running any scenarios.

```json
{"sdk": "flagsmith-python-client", "version": "6.3.0"}
```

### `POST /clients`

Create a new SDK client. Each scenario creates its own client.

Request:

```json
{
  "environmentKey": "test_environment_key",
  "apiUrl": "http://localhost:41234/api/v1/"
}
```

Response `201`:

```json
{"clientId": "1"}
```

### `POST /clients/{clientId}/environment-flags`

Get the environment flags.

Response `200`:

```json
{
  "flags": [
    {"featureName": "banner", "enabled": true, "value": "welcome"}
  ]
}
```

### `POST /clients/{clientId}/identity-flags`

Get the flags for an identity.

Request:

```json
{
  "identifier": "user_123",
  "traits": {"plan": "premium", "age": 30}
}
```

Response `200`: same shape as `environment-flags`.

### `DELETE /clients/{clientId}`

Dispose of the client (stop background threads, flush, close connections). Response `204`.
