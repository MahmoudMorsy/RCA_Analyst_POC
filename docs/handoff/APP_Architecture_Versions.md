# RCA Analyst — Application Architecture Versions

**Current application version:** v1.8.9  
**Embedded RCA Core:** v0.8.8 candidate

## 1. Principles

- one Web UI for Dell, RunPod and Home deployments;
- fixed versioned FastAPI `/api/v1` backend boundary;
- browser contains zero RCA decision logic;
- backend owns long-run lifetime, cancellation, persistence and telemetry;
- model/provider differences sit behind ModelGateway;
- deployment differences are configuration, not code forks;
- desktop application remains fallback/reference until live Web parity is accepted.

## 2. B0 — Monolithic desktop (v0.1 → v0.5.1)

PySide UI and RCA execution were colocated. Suitable for initial POC development but tightly coupled to local inference/runtime.

## 3. B1 — Regression/bundle workstation (v0.5.2 → v0.5.4)

Added sequential test bundles, session outputs and reproducible regression workflows.

## 4. B2 — Live observability/cancellation (v0.5.5 → v0.6.5)

Added dynamic pipeline visibility, attempts/repair views, statistics and cooperative stop behavior.

## 5. B3 — Architecture-debugging desktop (v0.7.x → v0.8.4)

Desktop remained primary while semantic architecture changed substantially. This exposed the need to decouple UI from model/runtime location.

## 6. B4 — v1.8.4/v1.8.5 Web/backend refactor

Introduced:

- same static Web frontend;
- FastAPI `/api/v1` backend;
- backend-owned asynchronous Run Manager;
- persistent Storage/Sessions/History/Telemetry;
- ModelGateway/provider abstraction;
- local Dell, RunPod and Home deployment profiles;
- auth/CORS/remote deployment contracts;
- desktop fallback.

v1.8.5 repaired Python 3.9 server-layer compatibility.

## 7. B5 — v1.8.6 Web observability/configuration repair

- merged repeated pipeline stage events so completed stages retain earlier input/output;
- human-readable structured stage renderer plus Raw JSON;
- per-testcase batch result tabs;
- incremental completed-case publishing;
- per-testcase/per-stage/failed-call statistics;
- endpoint-current model discovery/test;
- visible environment overrides;
- immutable per-run configuration snapshots;
- external model-server context/offload ownership represented accurately;
- Critical Semantic Model Routing.

## 8. B6 — v1.8.7 semantic transport/observability hardening

- explicit Qwen/llama.cpp request-level Thinking Off/On;
- reasoning-content presence telemetry independent from provider reasoning-token count;
- stable critical-role routing without endpoint hacks or killing model processes;
- external model-server runtime context remains server-owned.

## 9. B7 — v1.8.8 testcase lifecycle and full-suite integration

The Tests selector is no longer derived only from completed result objects.

Backend behavior:

```text
case created → RUNNING → PASS / FAILED / CANCELLED
```

- lifecycle row is persisted before pipeline execution;
- single and batch runs both expose `case_lifecycle`;
- batch `result.cases` includes the current RUNNING row;
- the same row is updated in place at terminal state;
- lifecycle snapshots contain slim status/timing/statistics metadata, not duplicated huge result payloads.

Web behavior:

- **Tests** selector appears for single and batch runs;
- current running case appears immediately;
- user can browse completed results and switch back to live case;
- running case shows Live Pipeline, Logs and partial Stats;
- final-only views report that final result is not yet available.

This is presentation/lifecycle state only. The browser still does not infer RCA verdicts or semantic acceptance.

## 10. Current backend/API contracts

Key endpoints include:

- `/api/v1/health`, `/system`, `/capabilities`;
- `/api/v1/config`, `/models`, `/models/discover`;
- `/api/v1/files`;
- `/api/v1/runs` and run status/result/pipeline/logs/events/cancel/download;
- `/api/v1/sessions`.

`GET /runs/{run_id}/result` includes authoritative testcase lifecycle state during execution.

## 11. Deployment

The exact same v1.8.9 application package runs on Dell, RunPod and Home. Model endpoints/model IDs/context/offload are deployment configuration. External llama.cpp/LM Studio/vLLM process lifecycle remains external unless a future adapter explicitly owns it.

## 12. Current validation status

Automated application/core tests, compile/static checks, JS syntax, API smoke and clean-package replay are mandatory release gates. They do not replace live model/browser acceptance.

Next: deploy the exact v1.8.9 package and rerun the complete live regression bundle with stable model settings. RCA Core v0.8.8 remains candidate.


## B8 — v1.8.9 reconnect and live pipeline UX

The Web client reconciles active runs from the backend after authentication. One active run resumes automatically; multiple active runs are selectable. Pipeline structured-tree expansion and per-run testcase/stage selection survive live polling rerenders.
