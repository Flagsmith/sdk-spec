# SDK steps

The steps every SDK implements in its steps file. The step text is the contract: rewording a step is a
major version, and adding one is a minor version.

For how to write a steps file, see [Onboarding an SDK](README.md#onboarding-an-sdk).

## Conventions

- A step receives the client first, unless it creates one, followed by the step's `{placeholders}` in
  order. A data table comes last.
- Values are JSON values: string, number, boolean or `null`. Pass flag and trait values through with
  their types intact. Do not stringify them.
- Flags are returned as a list of `{"feature": <name>, "enabled": <bool>, "value": <value>}`.
- Let SDK errors propagate. The scenario fails with the error message.

## `Given an SDK client for the environment`

| Argument         | Example                         |
| ---------------- | ------------------------------- |
| `environmentKey` | `ser.abc123` (server-side key)  |
| `apiUrl`         | `http://flagsmith:8000/api/v1/` |

Returns an SDK client created with default options.

## `When the application gets the environment flags`

| Argument | |
| -------- | - |
| `client` | |

Returns the environment's flags.

## `When the application gets the flags for identity "{identifier}" with traits:`

| Argument     | Example                           |
| ------------ | --------------------------------- |
| `client`     |                                   |
| `identifier` | `user_123`                        |
| `traits`     | `{"plan": "premium", "age": 30}`  |

Returns the identity's flags.
