# RCA Analyst v1.8.13 — Web UI + Hardware-Independent RCA Backend

**Application version:** v1.8.13  
**Embedded RCA Core:** v0.8.11 candidate

v1.8.13 is a semantic-core contract hardening release driven by the complete v1.8.12 RunPod session `RCA_20260903_110944_47ac48`. That run completed all 17 cases and improved semantic acceptance to 14/17, leaving TEST-004, TEST-009 and TEST-019. v1.8.13 fixes those demonstrated boundaries without changing the overall v0.8 topology or frozen evidence rules.

RCA Core v0.8.11 remains **candidate**, not frozen, until this exact v1.8.13 package completes the full live RunPod suite. TC12 and TC17 remain live-confirmed 27B anchors.

## Architecture at a glance

```text
Same Web UI
    │ REST / polling / SSE
    ▼
RCA Backend API /api/v1
    │
    ├── asynchronous Run Manager
    ├── Storage / Sessions / History / Telemetry
    ├── RCA Core v0.8.11
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

## v1.8.13 highlights

- Structured verifier `target_fields` are authoritative; explanatory prose cannot create extra repair targets.
- Structural completion admits safe targeted fields from partial responses and leaves omitted sibling fields unresolved for the next bounded pass.
- Arbitration admits valid targeted sibling repairs when another target field is omitted; changed untargeted fields remain rejected.
- RCA Evidence Packets preserve correlated current direct-observation peers by explicit observation group or exact same-clock timestamp.
- Deterministic compliance accepts semantic facts only from authoritative current-case observation sources; historical evidence can never establish current applicability/compliance.
- v1.8.12 Models & Inference discovery/test behavior is retained unchanged.
- Terminal run states are published only after the auto-saved session ID exists, removing an intermittent reconnect/download race.

See [`docs/V1.8.13_RELEASE_NOTES.md`](docs/V1.8.13_RELEASE_NOTES.md).

## v1.8.12 highlights

- Model discovery distinguishes reachable/no-model/unavailable states.
- Single advertised models are resolved into the form after endpoint changes.
- OpenAI-compatible `data[].id` and `models[].name` catalog variants are normalized.
- llama.cpp runtime context is discovered from `/props` when catalog metadata omits it.
- Model Test performs a real one-token inference request and leaves persistent PASS/FAIL feedback.
- RCA Core v0.8.10 is unchanged.

See [`docs/V1.8.12_RELEASE_NOTES.md`](docs/V1.8.12_RELEASE_NOTES.md).

## v1.8.11 highlights

- VERIFIED independent-verifier fingerprints must themselves be structurally complete; incomplete operator/value/trigger/timing/relationship identity is a structured-output defect, not a false compiler mismatch;
- Requirement persistence scope now uses a dedicated canonical domain and rejects evidence observation tokens such as `INTERVAL_STATE`;
- atomic arbitration ignores redundant unchanged untargeted fields but still rejects any changed untargeted field;
- creating a previously absent semantic field automatically couples the repair to `source_clauses` when its provenance role is missing;
- RCA Evidence Packets include referenced canonical structural direct observations even when they required no language annotation;
- rejected arbitration attempts persist the exact contract-rejection reason in attempt diagnostics and validation issues;
- all v1.8.10 containment/session/Web behavior remains, including testcase-local failure isolation, browser reconnect and live Pipeline state persistence.

See [`docs/V1.8.11_RELEASE_NOTES.md`](docs/V1.8.11_RELEASE_NOTES.md) for the live TEST-007/015/016/018/019/021 evidence and release changes.

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

The v1.8.11 backend does **not** start/restart external LM Studio/llama.cpp/vLLM processes. Therefore a server launched as:

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

These remain deployment-time defaults. v1.8.11 exposes active overrides in the Web UI and snapshots the current form into each run's `config_override`, avoiding the v1.8.5 ambiguity where a save could appear to revert after an environment override was reapplied.

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

- [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) — current v1.8.11 application architecture
- [`docs/RCA_CORE_ARCHITECTURE_v0.8.11.md`](docs/RCA_CORE_ARCHITECTURE_v0.8.11.md) — current semantic-core architecture
- [`docs/DESKTOP_UI_MIGRATION_MATRIX.md`](docs/DESKTOP_UI_MIGRATION_MATRIX.md) — desktop → Web parity contract
- [`docs/API.md`](docs/API.md)
- [`docs/CONFIGURATION.md`](docs/CONFIGURATION.md)
- [`docs/DEPLOY_LOCAL_DELL.md`](docs/DEPLOY_LOCAL_DELL.md)
- [`docs/DEPLOY_RUNPOD.md`](docs/DEPLOY_RUNPOD.md)
- [`docs/DEPLOY_HOME_AI_SERVER.md`](docs/DEPLOY_HOME_AI_SERVER.md)
- [`docs/V1.8.12_RELEASE_NOTES.md`](docs/V1.8.12_RELEASE_NOTES.md)
- [`docs/V1.8.11_RELEASE_NOTES.md`](docs/V1.8.11_RELEASE_NOTES.md)
- [`VERSION_HISTORY.md`](VERSION_HISTORY.md)
- [`CHANGELOG.md`](CHANGELOG.md)

Historical v0.8.4/v1.8.4/v1.8.5 architecture and release documents remain packaged as historical references.

## Tests

```bash
pytest -q
```

v1.8.13 release validation: **253 passed** in the working tree and **253 passed** from a clean fresh extraction of the exact release candidate, plus Python compile, Web JavaScript syntax, FastAPI health/config/capabilities smoke and ZIP integrity/hygiene gates. The final packaged ZIP is replayed again after documentation synchronization.

Automated tests prove software/regression contracts only. They do not constitute live-model acceptance. After release packaging, rerun the complete live regression bundle with a stable model configuration. TC17 and TC12 remain explicit semantic anchors within that run. Do not consider RCA Core v0.8.11 frozen until live full-suite acceptance succeeds.
