# Python harness

## In an SDK's `sdk-spec/Dockerfile`

Install the SDK from source, then copy in `harness.py` and run it on the steps file. For a full
example, see `sdk-spec/Dockerfile` in `flagsmith-python-client`.

```dockerfile
FROM docker.io/library/python:3.12-slim
WORKDIR /sdk
COPY . .
RUN pip install --no-cache-dir .

COPY --from=harness harness.py /harness/harness.py
ENTRYPOINT ["python", "/harness/harness.py", "sdk-spec/steps.py"]
```

The harness uses only the standard library, and needs Python 3.10 or later.

## Steps file conventions

- Steps are module-level functions, each directly below its step marker comment (`# When …`).
- Arguments arrive as parsed JSON: `str`, `int`, `float`, `bool`, `None`, and data tables as `dict`.
- Return JSON-serialisable values.
- Let errors raise. They are reported as `"<class>: <message>"`, with the traceback on stderr.

## Running locally

From the runner directory, with the SDK installed in the runner's environment:

```sh
SDK_COMMAND="python ../harness/python/harness.py ../../flagsmith-python-client/sdk-spec/steps.py" uv run pytest -v
```
