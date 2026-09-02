# RCA Analyst v1.8.5 Application Architecture

## 1. Scope and frozen semantic baseline

v1.8.5 preserves the v1.8.4 **application architecture, deployment and UI boundaries**. It does not redesign the RCA reasoning architecture.

Authoritative RCA Core baseline: **v0.8.4**. The preserved semantic architecture is retained separately in [`RCA_CORE_ARCHITECTURE_v0.8.4.md`](RCA_CORE_ARCHITECTURE_v0.8.4.md).

Application versioning intentionally jumps from **v0.8.4 → v1.8.4**, retaining the same minor/patch coordinates while marking the major application-architecture transition.

## 2. Target topology

```text
                         SAME WEB FRONTEND
                                │
                     REST / polling / SSE
                                │
                                ▼
                    FIXED RCA BACKEND /api/v1
                                │
       ┌────────────────────────┼────────────────────────┐
       │                        │                        │
       ▼                        ▼                        ▼
 Async Run Manager        RCA Core v0.8.4       Storage / Sessions
       │                        │                        │
       │                        ▼                        │
       │                   ModelGateway                 │
       │                        │                        │
       └────────────────────────┼────────────────────────┘
                                │
                      OpenAI-compatible API
                                │
             ┌──────────────────┼──────────────────┐
             ▼                  ▼                  ▼
         LOCAL DELL          RUNPOD           HOME AI SERVER
       LM Studio/etc.       vLLM/etc.       LM Studio/vLLM/etc.
```

The backend URL is the deployment abstraction. The frontend and RCA core are not forked by hardware target.

## 3. Frontend boundary

`web/` is a dependency-light browser SPA using HTML/CSS/ES modules. It can be served by FastAPI or hosted separately.

It contains no RCA decision logic. It may only:

- collect case/configuration input;
- select backend profiles;
- upload/download data;
- start/cancel runs;
- render run state, stages, logs, results and telemetry;
- capability-gate unsupported inference-engine controls;
- manage session/history presentation.

It never decides applicability, compliance, repair, retry, evidence sufficiency, RCA routing, hypothesis validity or model-role execution.

### Desktop parity

The functional contract is [`DESKTOP_UI_MIGRATION_MATRIX.md`](DESKTOP_UI_MIGRATION_MATRIX.md). The Web UI preserves:

- primary and small-model configuration;
- intake/semantic/arbitration/RCA/review controls;
- all legacy compatibility config fields;
- case input and built-in tests;
- sequential test-bundle execution;
- Stop/Abort;
- Final Report;
- Live Pipeline + dynamic stages + input/output inspection;
- Stage Log;
- Sequential Batch;
- Validation;
- Canonical Input;
- Structured JSON;
- API Stats;
- LLM Attempts;
- Repair Routing;
- report/session export;
- run/session history.

## 4. Backend boundary

`rca_server/` is a modular monolith built with FastAPI. It deliberately avoids Redis/Celery/database infrastructure at this POC stage.

Responsibilities:

- versioned REST API;
- authentication/CORS;
- immutable per-run config snapshots;
- background job lifecycle;
- cooperative cancellation;
- persistent run journal;
- live pipeline event capture;
- file/session/report services;
- capability discovery;
- best-effort system telemetry;
- ModelGateway construction;
- deployment configuration.

The API schemas are separate from `rca_app.models` domain objects.

## 5. Long-running execution

`POST /api/v1/runs` writes `QUEUED` metadata and returns immediately. Execution occurs in a backend thread pool. Browser/request lifetime has no ownership of the job.

States are backend-authoritative:

- `QUEUED`
- `INITIALIZING`
- `RUNNING`
- `CANCELLING`
- `CANCELLED`
- `COMPLETED`
- `FAILED`

Every transition is journaled. The browser can reload and recover state from `/runs` and `/runs/{id}`.

### Process restart

v1.8.4 preserves incomplete run artifacts but does not attempt unsafe mid-pipeline resume after a backend process restart. Runs found in non-terminal state on startup are deterministically marked `FAILED` with an interruption message. Browser disconnect/reconnect is fully supported; backend-process crash recovery is artifact-preserving rather than semantic resume.

## 6. Cancellation

Each run owns a `CancellationToken` and current pipeline reference. `POST /runs/{id}/cancel`:

1. moves state to `CANCELLING`;
2. sets the shared cancellation token;
3. calls pipeline/model-client cancellation to close an active streaming request where possible;
4. prevents additional pipeline progression/model calls;
5. persists partial logs, stages and metrics;
6. finalizes state as `CANCELLED`.

No partial RCA output is promoted to a completed result.

## 7. ModelGateway

The RCA core now consumes the provider-neutral `ModelClient` protocol. Deployment code creates clients through `ModelGateway`.

```text
RCAPipeline
   │ ModelClient protocol
   ▼
ModelGateway
   ├─ OpenAI-compatible / LM Studio
   ├─ llama.cpp-compatible
   ├─ vLLM
   └─ future providers
```

The proven `LMStudioClient` transport remains as an OpenAI-compatible implementation behind the gateway. Core `pipeline.py` no longer imports it directly.

The legacy Qt UI remains a frozen compatibility fallback and may still construct LM Studio clients directly; this does not define the v1 production architecture.

## 8. Configuration separation

### RCA configuration

Hardware-independent behavior and model-role semantics. The backend retains the exact legacy `AppConfig` field names internally for migration safety.

### Model endpoint configuration

Per role:

- provider;
- endpoint;
- model ID;
- context size metadata;
- temperature;
- reasoning effort;
- max output tokens;
- thinking mode;
- transport;
- timeout;
- token environment-variable name.

Primary and small models remain independently configurable.

### Inference-engine configuration

Hardware/provider dependent:

- CPU threads;
- GPU layers/offload;
- tensor split;
- Flash Attention;
- physical/eval batch size;
- parallel slots;
- context override;
- provider-specific options.

Capabilities determine whether a control is active. These settings never change RCA semantics.

### Infrastructure configuration

Detected/reported:

- deployment type/profile;
- hostname/OS/Python;
- CPU/thread counts;
- RAM;
- GPU count/model/VRAM/utilization/temperature/power where available;
- disk usage.

Telemetry absence never fails an RCA run.

## 9. Storage abstraction

The browser never accesses backend filesystem paths directly.

`LocalStorageBackend` is the first storage implementation and works for:

- Dell local filesystem;
- RunPod persistent mounted storage;
- future home-server disks.

Configurable root, no RunPod path in RCA core.

```text
<root>/
  config/
  uploads/
  runs/<run_id>/
    metadata.json
    config_snapshot.json
    pipeline.json
    events.jsonl
    logs.jsonl
    metrics.json
    result.json | failure.json
    report.md
    cases/...                 # batch runs
  sessions/
  reports/
  logs/
  tmp/
```

## 10. Sessions

There remains one RCA session format across hardware targets.

v1.8.4 introduces envelope schema version 2:

```json
{
  "schema_version": 2,
  "app_version": "1.8.4",
  "session_id": "...",
  "run_id": "...",
  "status": "COMPLETED",
  "deployment": {},
  "hardware": {},
  "inference_engine": {},
  "config_snapshot": {},
  "payload": {}
}
```

Legacy desktop result/failure JSON without an envelope is deterministically wrapped. The complete original payload is retained in `original_legacy_payload`; migration never silently discards fields.

## 11. Live Pipeline

The validated RCA core already emits dynamic stage trace events. The backend timestamps and persists them as API `PipelineStage` objects:

- stage ID/name;
- status;
- summary;
- start/end time;
- elapsed time;
- exact stage input/output text;
- metadata.

The frontend renders stages dynamically and does not assume a fixed count. Both polling and SSE replay are available.

## 12. Metrics and benchmarking

Run metrics include:

- model/provider/role;
- prompt/completion/reasoning/total tokens;
- request duration;
- derived generation tokens/s;
- finish reason;
- retries;
- transport;
- stage timing;
- total run timing;
- start/end hardware telemetry.

Metrics unavailable from a provider (for example TTFT or model-load time) remain `null` rather than blocking analysis.

Run history persists configuration/hardware/model metadata so TC12/TC17 can be compared across Dell, RunPod and future home hardware.

## 13. Security

Local profile may run unauthenticated on loopback.

Remote profiles support:

- bearer token authentication (`RCA_API_TOKEN`);
- explicit CORS (`RCA_CORS_ORIGINS`);
- TLS/HTTPS at the platform/reverse-proxy edge;
- private model endpoints behind the backend.

Secrets are not stored in source configuration. Model configs store environment-variable names, not token values. Browser backend bearer tokens are held in `sessionStorage`, not committed source/profile JSON.

## 14. Docker/deployment

The backend and frontend are one portable container in v1.8.4. Model servers remain separate provider services/endpoints because model-runtime choices differ greatly by hardware.

`docker compose up --build` starts the RCA application. Deployment profiles and environment variables select storage/model endpoints without code changes.

## 15. Migration safety

The desktop app is retained through `run_desktop.py` / `run_desktop.bat` until live parity is proven.

RCA semantic changes are prohibited as part of this refactor. Any future migration-induced RCA change requires explicit documentation and the existing TC regression suite.


## v1.8.5 Python 3.9 compatibility

The backend avoids PEP 604 `T | None` annotations in FastAPI runtime signatures and server-layer callable annotations. This keeps the Web/backend application compatible with the existing Python 3.9 Dell environment without changing RCA semantics.
