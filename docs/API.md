# RCA Analyst v1.8.5 API

Base path: `/api/v1`

Interactive OpenAPI docs are available at `/docs` when the backend is running.

## Backend/system

- `GET /health` — backend/version/profile health
- `GET /system` — best-effort infrastructure telemetry
- `GET /capabilities` — hardware/provider capability discovery
- `GET /models` — configured primary/small model availability and model lists
- `POST /models/test` — test one model role
- `GET /config` — current application config
- `PUT /config` — replace validated application config

## Files/examples

- `POST /files` — multipart upload; returns `file_id`
- `GET /files/{file_id}` — download uploaded file
- `GET /examples/TEST-001`
- `GET /examples/TEST-002`
- `GET /examples/TEST-003`

## Runs

### Create

`POST /runs`

Single case:

```json
{"run_type":"single","raw_case":"...","label":"optional"}
```

Built-in regression:

```json
{"run_type":"builtin_regression","label":"TC1-TC3"}
```

Uploaded ZIP:

```json
{"run_type":"bundle","file_id":"...","label":"bundle"}
```

Response returns quickly:

```json
{"run_id":"TC12_...","status":"QUEUED"}
```

A full immutable config can optionally be supplied as `config_override`; otherwise the backend snapshots its current config at creation time.

### Inspect

- `GET /runs`
- `GET /runs/{run_id}`
- `GET /runs/{run_id}/status`
- `GET /runs/{run_id}/pipeline`
- `GET /runs/{run_id}/metrics`
- `GET /runs/{run_id}/logs`
- `GET /runs/{run_id}/result`
- `GET /runs/{run_id}/events?after=N` — SSE event replay/live tail

### Cancel

- `POST /runs/{run_id}/cancel`

### Download

- `GET /runs/{run_id}/report/download`
- `GET /runs/{run_id}/session/download`

## Sessions

- `GET /sessions`
- `POST /sessions/save` with `{ "run_id": "..." }`
- `POST /sessions/load` with a previously uploaded JSON `file_id` or inline `payload`
- `GET /sessions/{session_id}`
- `GET /sessions/{session_id}/download`

Legacy v0.x desktop payloads are wrapped without field loss.

## Authentication

When the deployment profile has `auth_required: true`, all `/api/v1/*` requests require:

```text
Authorization: Bearer <RCA_API_TOKEN>
```

The Web UI obtains/stores that token only in the current browser session.
