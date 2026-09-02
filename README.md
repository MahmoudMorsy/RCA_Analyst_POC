# RCA Analyst v1.8.5 — Web UI + Hardware-Independent RCA Backend

v1.8.5 is a maintenance release of the major **application architecture/deployment refactor** built on the RCA Core v0.8.4 semantic baseline. The RCA reasoning, compliance, evidence, repair and reporting behavior is intentionally preserved; the application shell is moved from a monolithic PySide desktop process to a browser frontend, stable FastAPI backend, asynchronous run manager, storage layer and model gateway.

## Architecture at a glance

```text
Same Web UI
    │
    │ REST / polling / SSE
    ▼
RCA Backend API  /api/v1
    │
    ├── asynchronous Run Manager
    ├── Storage / Sessions / History / Telemetry
    ├── RCA Core (v0.8.4 behavior)
    │       │
    │       ▼
    │   ModelGateway
    │       │ OpenAI-compatible
    │       ▼
    │   LM Studio / llama.cpp / vLLM / future provider
    │
    └── deployment abstraction
            ├── Local Dell
            ├── RunPod
            └── Home AI Server
```

The browser contains **zero RCA decision logic**. It collects inputs/configuration, starts/stops jobs and renders backend state.

## Primary start — local Web application

```bat
setup.bat
run.bat
```

Then open:

```text
http://localhost:8000
```

By default the Local Dell deployment profile expects the model endpoint at:

```text
http://127.0.0.1:1234/v1
```

Configure the exact primary and small model IDs in the Web UI.

## Frozen desktop fallback

The old desktop workflow is intentionally retained during migration validation:

```bat
run_desktop.bat
```

or:

```bash
python run_desktop.py
```

It is a fallback/reference, not the primary v1.8.5 architecture.

## Deployment profiles

Included profiles:

- `configs/deployment/local-dell.yaml`
- `configs/deployment/runpod.yaml`
- `configs/deployment/home-ai-server.yaml`

Choose the backend deployment with:

```text
RCA_DEPLOYMENT_PROFILE=local-dell
RCA_DEPLOYMENT_PROFILE=runpod
RCA_DEPLOYMENT_PROFILE=home-ai-server
```

or point `RCA_DEPLOYMENT_PROFILE` directly to a YAML file.

The Web UI separately maintains browser-side backend profiles for **Local Dell**, **RunPod Development**, **Home AI Server** and **Custom endpoint**. Switching backend location does not change RCA code.

## Long-running jobs

`POST /api/v1/runs` returns quickly with a `run_id`. The backend job continues independently of the browser connection. A page reload or different browser client can reconnect using the run ID/history endpoints.

Explicit states:

`QUEUED → INITIALIZING → RUNNING → COMPLETED/FAILED`

Cancellation uses:

`RUNNING → CANCELLING → CANCELLED`

Partial logs, pipeline events and metrics remain persisted.

## Storage

The backend owns all file access. Default local storage:

```text
~/.rca_analyst_poc/web_backend/
```

Layout:

```text
config/
uploads/
runs/
sessions/
reports/
logs/
tmp/
```

Override with `RCA_STORAGE_ROOT`. RunPod should use persistent `/workspace`/network storage rather than container-local ephemeral storage.

## Remote security

Remote profiles enable bearer authentication. Set:

```text
RCA_API_TOKEN=<strong random token>
RCA_CORS_ORIGINS=https://your-web-origin.example
```

Use HTTPS/TLS through the RunPod proxy or your own reverse proxy. Keep raw model-serving ports private whenever possible.

## Model endpoint deployment overrides

Useful for Docker/remote deployments:

```text
RCA_PRIMARY_ENDPOINT=http://model-primary:8001/v1
RCA_SMALL_ENDPOINT=http://model-small:8002/v1
RCA_PRIMARY_MODEL=<model-id>
RCA_SMALL_MODEL=<model-id>
RCA_PRIMARY_PROVIDER=vllm
RCA_SMALL_PROVIDER=vllm
```

These are deployment details only; they do not alter RCA semantics.

## Documentation

- [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) — overall v1.8.5 application architecture
- [`docs/RCA_CORE_ARCHITECTURE_v0.8.4.md`](docs/RCA_CORE_ARCHITECTURE_v0.8.4.md) — preserved RCA semantic-core architecture
- [`docs/DESKTOP_UI_MIGRATION_MATRIX.md`](docs/DESKTOP_UI_MIGRATION_MATRIX.md) — mandatory desktop → Web/API parity map
- [`docs/MIGRATION_RISK_ASSESSMENT.md`](docs/MIGRATION_RISK_ASSESSMENT.md)
- [`docs/TARGET_MODULE_ARCHITECTURE.md`](docs/TARGET_MODULE_ARCHITECTURE.md)
- [`docs/API.md`](docs/API.md)
- [`docs/CONFIGURATION.md`](docs/CONFIGURATION.md)
- [`docs/DEPLOY_LOCAL_DELL.md`](docs/DEPLOY_LOCAL_DELL.md)
- [`docs/DEPLOY_RUNPOD.md`](docs/DEPLOY_RUNPOD.md)
- [`docs/DEPLOY_HOME_AI_SERVER.md`](docs/DEPLOY_HOME_AI_SERVER.md)
- [`docs/V1.8.4_RELEASE_NOTES.md`](docs/V1.8.4_RELEASE_NOTES.md)
- [`VERSION_HISTORY.md`](VERSION_HISTORY.md)
- [`CHANGELOG.md`](CHANGELOG.md)

## Tests

```bash
pytest -q
```

v1.8.5 retains the v1.8.4 backend/API migration tests and adds Python 3.9 backend compatibility coverage while retaining the complete v0.8.4 RCA regression suite. The release is not considered semantically frozen merely because the Web refactor passes software tests; TC12/TC17 live-model validation remains the next RCA validation step.
