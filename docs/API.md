# RCA Analyst v1.8.13 API

Base path: `/api/v1`.

## Backend/system

- `GET /health` — status, application version, RCA core version, deployment/profile.
- `GET /system` — best-effort infrastructure telemetry.
- `GET /capabilities` — backend/provider capabilities plus active model environment overrides.
- `GET /models` — discovery using effective persisted/deployment configuration (compatibility endpoint).
- `POST /models/discover` — discover models using the **current submitted role configuration**, without saving first.
- `POST /models/test` — test the current submitted role configuration or the effective saved role when omitted.
- `GET /config` — current effective application configuration.
- `PUT /config` — persist validated application configuration.

### Current-form model discovery

```json
{
  "role": "small",
  "config": {
    "provider": "openai-compatible",
    "endpoint": "http://127.0.0.1:8004/v1",
    "model": "",
    "temperature": 0.0,
    "reasoning_effort": "provider_default",
    "max_tokens": 6000,
    "context_size": 32768,
    "timeout_seconds": 10800,
    "thinking_mode": "off",
    "transport": "auto",
    "api_token_env": "LM_API_TOKEN"
  }
}
```

The response contains `models` and the provider `catalog` where available. llama.cpp metadata such as `meta.n_ctx` is observational and can be displayed by the frontend.

## Files/examples

- `POST /files`
- `GET /files/{file_id}`
- `GET /examples/TEST-001`
- `GET /examples/TEST-002`
- `GET /examples/TEST-003`

## Runs

### Create

`POST /runs`

```json
{
  "run_type": "single",
  "raw_case": "...",
  "label": "optional",
  "config_override": {"...": "complete ApplicationConfig snapshot"}
}
```

`config_override` is optional. v1.8.11 Web runs submit the current form as an immutable per-run override so deployment environment variables remain backend defaults without silently blocking a one-run routing experiment.

Run types:

- `single`
- `builtin_regression`
- `bundle`

Response returns quickly:

```json
{"run_id":"...","status":"QUEUED"}
```


### Testcase lifecycle — v1.8.9

`GET /api/v1/runs/{run_id}/result` now includes top-level `case_lifecycle`. For batch runs, `result.cases` also contains the current RUNNING testcase before completion. A lifecycle record includes the testcase ID, execution status, semantic acceptance state, timestamps, result availability and partial/final statistics where available.

Single runs expose one lifecycle row as soon as execution begins. Batch runs update the same row in place from `RUNNING` to `PASS`, `FAILED` or `CANCELLED`. Clients should use this authoritative lifecycle instead of assuming that only completed cases exist.

### Inspect

- `GET /runs`
- `GET /runs/{run_id}`
- `GET /runs/{run_id}/status`
- `GET /runs/{run_id}/pipeline`
- `GET /runs/{run_id}/metrics`
- `GET /runs/{run_id}/logs`
- `GET /runs/{run_id}/result`
- `GET /runs/{run_id}/events?after=N`

Pipeline stages include persistent `input_text`, `output_text`, optional structured `input_data`/`output_data`, metadata and per-stage statistics when available.

For batch runs, `result.cases` is updated and persisted after each successful or failed testcase rather than only at the end of the batch.

### Cancel/download

- `POST /runs/{run_id}/cancel`
- `GET /runs/{run_id}/report/download`
- `GET /runs/{run_id}/session/download`

## Sessions

- `GET /sessions`
- `POST /sessions/save`
- `POST /sessions/load`
- `GET /sessions/{session_id}`
- `GET /sessions/{session_id}/download`

Legacy desktop payloads remain wrapped/migrated with original payload retention.

## Authentication

When `auth_required=true`:

```text
Authorization: Bearer <RCA_API_TOKEN>
```

Browser bearer tokens are session-scoped and are not committed in frontend source.


## v1.8.9 reconnect behavior

`GET /runs` is the browser reconnect source of truth. Non-terminal runs are rediscovered after authentication; run status/pipeline/logs/metrics/result endpoints are then reattached through the existing run ID.


## Current batch failure semantics

For `builtin_regression` and `bundle` runs, a testcase-local unexpected exception no longer changes the whole run to `FAILED`. The affected `result.cases[]` row becomes `FAILED`, its failure artifact is persisted, and the next testcase is attempted unless cancellation/run-level failure occurs.

Generic testcase failure payloads include:

```json
{
  "status": "FAILED",
  "case_id": "TEST-007",
  "exception_type": "ValueError",
  "message": "...",
  "traceback": "Traceback ...",
  "partial_pipeline": []
}
```

A completed bundle may therefore contain a mix of `PASS` and `FAILED` testcase rows while the run itself is `COMPLETED`. `COMPLETED` means the requested sequence finished; it does not mean semantic acceptance passed.

If a run has both partial result data and an unrecoverable run-level failure, the saved session keeps the normal result payload and adds `run_failure`.


## v1.8.12 model endpoint discovery/test behavior

`POST /api/v1/models/discover` uses the request's current form configuration and returns `status` as `AVAILABLE`, `NO_MODELS`, or `UNAVAILABLE`, plus `models`, `resolved_model`, `catalog`, and discovered `context_size` when explicit provider metadata exposes it. `NO_MODELS` means the HTTP endpoint is reachable but no model is currently advertised/loaded.

`POST /api/v1/models/test` validates the selected model against the current endpoint and performs a minimal OpenAI-compatible chat completion probe. The response includes `ok`, `message`, `resolved_model`, `models`, `catalog`, and `context_size`. This endpoint tests inference readiness; it does not start or load a model server.
