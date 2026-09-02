# APP Architecture Versions

**Current application version:** v1.8.6  
**Embedded RCA Core:** v0.8.5 candidate

## 1. Principles

- browser is a backend client, not an RCA decision engine;
- backend owns long-running jobs;
- model providers stay behind ModelGateway;
- deployment hardware is configuration;
- sessions remain hardware-independent;
- Web mode uses backend-mediated files/storage;
- detailed developer controls remain available;
- desktop remains fallback/reference until live Web parity is accepted.

## 2. B0 — Monolithic desktop (v0.1 → v0.5.1)

PySide UI, RCA pipeline, local files and LM Studio client shared one workstation process.

## 3. B1 — Regression/bundle workstation (v0.5.2 → v0.5.4)

Sequential regression, ZIP bundles, persisted sessions/reports, execution-vs-semantic acceptance and forensic model attempts matured.

## 4. B2 — Live observability/cancellation (v0.5.5 → v0.6.5)

Desktop Live Pipeline, exact stage I/O, Stop/cancellation and rich multi-model controls became the functional parity reference.

## 5. B3 — Architecture-debugging desktop (v0.7.x → v0.8.4)

Dynamic stage/chunk inspection and detailed session exports continued, but remote GPU deployment remained awkward because UI/execution/files were local-process coupled.

## 6. B4 — v1.8.4/v1.8.5 Web/backend refactor

```text
Same Web UI
→ FastAPI /api/v1
→ backend Run Manager / Storage / Sessions / Telemetry
→ RCA Core
→ ModelGateway
→ provider endpoint
→ Dell / RunPod / Home
```

v1.8.4 introduced backend-owned asynchronous runs, storage/session schema, provider abstraction, deployment profiles, bearer/CORS and Web UI. v1.8.5 fixed Python 3.9 FastAPI runtime annotations.

## 7. B5 — v1.8.6 observability/configuration/benchmarking repair

Live Dell/RunPod use exposed Web migration defects that unit tests had not exercised sufficiently.

### 7.1 Persistent Stage I/O

Repeated stage updates are merged; completion no longer erases input. Structured input/output is persisted and rendered human-readably with Raw JSON.

### 7.2 Batch parity

Batch case results are persisted incrementally. Selecting a testcase populates all forensic/result surfaces instead of leaving Validation, Canonical Input, LLM Attempts, Final Report, etc. empty.

### 7.3 Statistics

Per-case and per-stage aggregation includes elapsed/model time, tokens, retries, throughput, role/model/endpoint and requirement-result counts. Failed calls remain visible.

### 7.4 Current-endpoint discovery/test

`/models/discover` and `/models/test` accept current submitted role configuration so a user does not need to persist an endpoint before discovering/testing it.

### 7.5 Deployment overrides and run snapshots

Active `RCA_*` environment overrides are visible. Web runs carry explicit immutable `config_override` snapshots so deployment defaults do not silently prevent a controlled run.

### 7.6 External model-server authority

The backend does not claim that Web inference fields reconfigure an external llama.cpp/LM Studio/vLLM process. Context/offload settings are server-managed unless a future adapter declares ownership.

### 7.7 Critical semantic model routing

Application configuration adds a model-routing envelope selecting Small / Utility or Primary for semantic preparation and independent verification without endpoint hacks or process killing.

## 8. Current API additions

Existing `/api/v1` remains stable. v1.8.6 adds/extends:

- `POST /models/discover` current-form endpoint discovery;
- `POST /models/test` explicit submitted role config;
- run `config_override`;
- structured/persistent stage data;
- incremental batch results;
- richer case/stage metrics;
- capabilities reporting active environment overrides.

## 9. Deployment

Dell, RunPod and Home remain one codebase. RunPod model ports should remain private. Real model context is established by the provider/server launch (`llama-server -c ...`), not by a browser value.

## 10. Current validation status

Automated application tests are release gates, but Web parity/RunPod readiness still require live-model/browser validation. TC17/TC12 are the next semantic acceptance targets after v1.8.6 packaging.
