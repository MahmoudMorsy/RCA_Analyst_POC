# RCA Analyst v1.8.10 — Web UI + Hardware-Independent RCA Backend

**Application version:** v1.8.10  
**Embedded RCA Core:** v0.8.9 candidate

v1.8.10 is a failure-containment and verifier-equivalence patch built directly from v1.8.9 after the first exact-package 27B full-suite run exposed a TEST-007 arbitration-contract exception that terminated the whole bundle and false verifier mismatches caused by descriptive IR text. It keeps all v1.8.9 reconnect/live-view and RCA integration fixes intact.

RCA Core v0.8.9 is **not frozen** until the exact v1.8.10 package passes a stable live full-suite validation. Frozen anchors remain v0.4.3 TEST-003 and v0.5.2 TC1–TC3, with v0.3.6 TEST-001 retained as an earlier checkpoint.

## Architecture at a glance

```text
Same Web UI
    │ REST / polling / SSE
    ▼
RCA Backend API /api/v1
    │
    ├── asynchronous Run Manager
    ├── Storage / Sessions / History / Telemetry
    ├── RCA Core v0.8.9
    │       │
    │       ├── Small / Utility model roles
    │       ├── Critical Semantic Model Routing
    │       │      ├── compiler + evidence: small OR primary
    │       │      └── verifier: small OR primary
    │       ├── Python deterministic compliance authority
    │       └── conditional Primary arbitration / RCA synthesis
    │
    └── ModelGateway → OpenAI-compatible endpoint(s)
            ├── LM Studio
            ├── llama.cpp
            ├── vLLM
            └── compatible providers
```

The browser contains **zero RCA decision logic**. Model capacity may change by role, but Python remains authoritative for deterministic applicability/compliance/timing/evidence mechanics.

## v1.8.10 highlights

- unexpected testcase exceptions are isolated to that testcase; sequential bundle execution continues to later cases;
- pipeline construction is inside the testcase-local isolation boundary;
- invalid semantic-arbitration patches are rejected atomically and leave unresolved semantics conservative instead of crashing the testcase;
- an omitted arbitration target field is accepted only when every material issue governing that field is explicitly returned in `unresolved_issue_ids`;
- rejected arbitration responses remain preserved in attempts and Live Pipeline output for forensic inspection;
- generic testcase failure records include exception type, message, traceback and partial testcase pipeline;
- session export preserves partial batch results plus run-level failure metadata when both exist;
- Web failed-testcase views surface exception type and traceback;
- independent semantic verification compares executable required-behavior semantics only and ignores descriptive `process_description` wording;
- persistence fingerprint comparison normalizes structured scope categories instead of comparing arbitrary scope strings;
- all v1.8.9 fixes remain: verified-fact reuse, all-target completion, atomic field merge, RCA packet/provenance corrections, browser reconnect and live Pipeline expansion-state persistence.

See [`docs/V1.8.10_RELEASE_NOTES.md`](docs/V1.8.10_RELEASE_NOTES.md) for the exact TEST-007/TC12 evidence and release changes.

## Start the local Web application

```bat
setup.bat
run.bat
```

Open:

```text
http://localhost:8000
```

Configure the exact model endpoints and IDs in **Models & Inference**. Use **Discover at Endpoint** to query the endpoint currently entered in the form.

## Critical Semantic Model Routing

Under **RCA Configuration → Critical Semantic Model Routing**:

- `Compiler + evidence model`: `Small / Utility` or `Primary`;
- `Independent verifier model`: `Small / Utility` or `Primary`;
- separate reasoning/thinking settings for those two critical roles.

This lets RunPod test a stronger semantic model without changing utility intake/review roles or modifying model-server processes.

## External model-server context and inference settings

The v1.8.10 backend does **not** start/restart external LM Studio/llama.cpp/vLLM processes. Therefore a server launched as:

```text
llama-server ... -c 8192
```

still has an 8192-token runtime context until that server is restarted with another value. Web `Expected server context` fields are metadata/checks and model discovery displays provider-advertised context where available. External engine controls are capability-disabled unless a future backend adapter explicitly owns that setting.

## Long-running jobs

`POST /api/v1/runs` returns a `run_id` quickly. The backend owns execution lifetime independently of the browser.

```text
QUEUED → INITIALIZING → RUNNING → COMPLETED / FAILED
                         │
                         └→ CANCELLING → CANCELLED
```

Partial pipeline state, logs, metrics and incremental batch case results are persisted for reconnect/inspection.

## Storage

Default local Web storage:

```text
~/.rca_analyst_poc/web_backend/
```

Typical layout:

```text
config/
uploads/
runs/
  <run_id>/
    metadata.json
    config_snapshot.json
    pipeline.json
    metrics.json
    logs.jsonl
    events.jsonl
    result.json or failure.json
    cases/<TEST-ID>/session.json|failure.json
sessions/
reports/
logs/
tmp/
```

Override with `RCA_STORAGE_ROOT`. RunPod should use persistent `/workspace` storage.

## Deployment environment defaults

Useful deployment variables:

```text
RCA_PRIMARY_ENDPOINT=http://127.0.0.1:<primary-port>/v1
RCA_SMALL_ENDPOINT=http://127.0.0.1:<small-port>/v1
RCA_PRIMARY_MODEL=<model-id>
RCA_SMALL_MODEL=<model-id>
RCA_PRIMARY_PROVIDER=openai-compatible
RCA_SMALL_PROVIDER=openai-compatible
```

These remain deployment-time defaults. v1.8.10 exposes active overrides in the Web UI and snapshots the current form into each run's `config_override`, avoiding the v1.8.5 ambiguity where a save could appear to revert after an environment override was reapplied.

## Remote security

For remote deployments:

```text
RCA_API_TOKEN=<strong random token>
RCA_CORS_ORIGINS=https://your-ui-origin.example
```

Use HTTPS/TLS through RunPod/reverse proxy and keep raw model-serving ports private when practical.

## Desktop fallback

The old desktop application remains packaged as a fallback/reference:

```bat
run_desktop.bat
```

or:

```bash
python run_desktop.py
```

Do not remove it until Web parity is live-proven.

## Documentation

- [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) — current v1.8.10 application architecture
- [`docs/RCA_CORE_ARCHITECTURE_v0.8.9.md`](docs/RCA_CORE_ARCHITECTURE_v0.8.9.md) — current semantic-core architecture
- [`docs/DESKTOP_UI_MIGRATION_MATRIX.md`](docs/DESKTOP_UI_MIGRATION_MATRIX.md) — desktop → Web parity contract
- [`docs/API.md`](docs/API.md)
- [`docs/CONFIGURATION.md`](docs/CONFIGURATION.md)
- [`docs/DEPLOY_LOCAL_DELL.md`](docs/DEPLOY_LOCAL_DELL.md)
- [`docs/DEPLOY_RUNPOD.md`](docs/DEPLOY_RUNPOD.md)
- [`docs/DEPLOY_HOME_AI_SERVER.md`](docs/DEPLOY_HOME_AI_SERVER.md)
- [`docs/V1.8.10_RELEASE_NOTES.md`](docs/V1.8.10_RELEASE_NOTES.md)
- [`VERSION_HISTORY.md`](VERSION_HISTORY.md)
- [`CHANGELOG.md`](CHANGELOG.md)

Historical v0.8.4/v1.8.4/v1.8.5 architecture and release documents remain packaged as historical references.

## Tests

```bash
pytest -q
```

v1.8.10 release validation: **232 passed** in the working tree and **232 passed** from a clean fresh extraction.

Automated tests prove software/regression contracts only. They do not constitute live-model acceptance. After release packaging, rerun the complete live regression bundle with a stable model configuration. TC17 and TC12 remain explicit semantic anchors within that run. Do not consider RCA Core v0.8.9 frozen until live full-suite acceptance succeeds.
