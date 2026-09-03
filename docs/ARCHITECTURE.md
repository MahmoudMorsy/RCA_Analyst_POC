# RCA Analyst v1.8.12 Application Architecture

## 1. Scope and semantic baseline

**Application version:** v1.8.12  
**Embedded RCA Core:** v0.8.10 candidate

v1.8.12 keeps the v1.8.x Web/FastAPI modular-monolith architecture and RCA Core v0.8.10 unchanged. It is an application-only reliability patch for model endpoint discovery, context metadata and active inference testing.

RCA Core v0.8.10 is **not frozen** until the exact v1.8.12 package passes a stable live full-suite rerun. TC12 and TC17 are live-confirmed 27B anchors from v1.8.10; TC21 remains the primary RCA integration anchor. Frozen semantic anchors remain v0.4.3 TEST-003 and v0.5.2 TC1–TC3, with v0.3.6 TEST-001 retained as an earlier checkpoint.

Current core details are documented in [`RCA_CORE_ARCHITECTURE_v0.8.10.md`](RCA_CORE_ARCHITECTURE_v0.8.10.md). Historical v0.8.4-v0.8.8 architecture documents remain packaged separately.

## 2. Current topology

```text
                         SAME WEB FRONTEND
                                │
                     REST / polling / SSE
                                │
                                ▼
                    FASTAPI RCA BACKEND /api/v1
                                │
       ┌────────────────────────┼────────────────────────┐
       │                        │                        │
       ▼                        ▼                        ▼
 Async Run Manager       RCA Core v0.8.10      Storage / Sessions
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
       LM Studio/etc.    llama.cpp/vLLM/etc.  compatible provider
```

Hardware location changes deployment configuration and endpoints, not RCA semantics or frontend code.

## 3. Frontend boundary

`web/` is a dependency-light browser SPA. It contains **zero RCA decision logic**.

It may:

- collect case/configuration input;
- manage backend profiles;
- discover/test configured model endpoints;
- start/cancel runs;
- render backend-authoritative pipeline state, logs, results and telemetry;
- render structured Stage Input/Output in a human-readable way while preserving Raw JSON;
- select a testcase inside a sequential batch and render that case's complete result surfaces;
- present per-case/per-stage statistics;
- capability-gate settings that the backend/provider cannot actively control.

It never decides applicability, compliance, evidence sufficiency, repair, retry, arbitration, RCA routing or hypothesis validity.

## 4. Backend boundary

`rca_server/` remains a modular monolith built with FastAPI. Redis/Celery/database infrastructure is intentionally not introduced for the POC.

Responsibilities include:

- versioned REST API;
- authentication/CORS;
- immutable per-run configuration snapshots;
- background run lifetime;
- cooperative cancellation;
- persistent run journal;
- dynamic pipeline event capture;
- model discovery/test through provider-neutral endpoints;
- per-case/per-stage telemetry aggregation;
- file/session/report services;
- best-effort system telemetry;
- ModelGateway construction;
- deployment configuration.

The API schemas remain separate from RCA core domain models.

## 5. Long-running execution and reconnect

`POST /api/v1/runs` returns a `run_id` quickly. Execution continues in the backend independently of browser lifetime.

Backend-authoritative states:

- `QUEUED`
- `INITIALIZING`
- `RUNNING`
- `CANCELLING`
- `CANCELLED`
- `COMPLETED`
- `FAILED`

Browser reload/disconnect does not cancel a run. Backend-process crash recovery preserves artifacts but does not claim semantic mid-stage resume.

## 6. Pipeline persistence and inspection

v1.8.6 fixed the v1.8.5 stage-replacement bug. Repeated events for one stage are **merged**, so later completion/status events do not erase earlier Stage Input or Output.

Persisted stage data includes:

- stage ID/title/status/summary;
- start/end/elapsed time;
- text input/output;
- structured `input_data` / `output_data` where available;
- metadata;
- per-stage model-call statistics.

The frontend renders structured data as nested labeled sections/tables and keeps Raw JSON available for forensic inspection.

## 7. Batch result architecture

Batch runs publish results incrementally after each testcase, including failed cases. The aggregate run result is not delayed until the final testcase.

A selected testcase drives:

- Final Report;
- Validation;
- Canonical Input;
- Structured JSON;
- LLM Attempts;
- Repair Routing;
- logs;
- pipeline;
- statistics.

The Sequential Batch tab is an overall dashboard, not a substitute for per-case result parity.

## 8. ModelGateway and semantic-role routing

The RCA core consumes the provider-neutral `ModelClient` protocol. `PipelineFactory` constructs clients through `ModelGateway`.

v1.8.6 added **Critical Semantic Model Routing**:

- semantic preparation (Requirement IR compilation + evidence annotation) can use `small` or `primary`;
- independent semantic verification can separately use `small` or `primary`.

This is a capacity/transport selection only. Python remains authoritative for deterministic compliance.

Utility tasks may remain on the configured Small / Utility model while a stronger model is assigned to critical semantic roles.

### v1.8.7 semantic-call execution

OpenAI-compatible Qwen/llama.cpp requests propagate explicit thinking state through chat-template kwargs. Reasoning text is observed independently from provider token accounting. Requirement structural completion is a targeted patch call: Python supplies exact broken fields, the model returns only those fields, and Python rejects any untargeted overwrite. This keeps a correct condition AST from being regenerated because another field is incomplete.

## 9. Configuration model

### 9.1 RCA configuration

Hardware-independent RCA behavior and legacy compatibility fields.

### 9.2 Model-role configuration

Primary and Small / Utility roles independently define:

- provider;
- endpoint;
- model ID;
- temperature;
- reasoning effort;
- max output tokens;
- expected context metadata;
- timeout;
- thinking mode;
- transport;
- API-token environment variable.

### 9.3 Critical semantic routing

`model_routing` contains:

- `semantic_preparation_role`: `small | primary`;
- `semantic_verification_role`: `small | primary`;
- independent reasoning/thinking overrides for those roles.

### 9.4 Inference-engine configuration

CPU threads, GPU layers/offload, tensor split, Flash Attention, batch sizes, slots, context override and provider options remain capability-gated metadata unless a deployment adapter explicitly owns the external model-server process.

**Important:** v1.8.9 does not restart/reconfigure an externally launched llama.cpp/LM Studio/vLLM process. A server launched with `llama-server -c 8192` remains 8K regardless of a Web form value.

## 10. Model discovery and environment overrides

`POST /api/v1/models/discover` discovers models from the endpoint currently entered in the form; saving first is not required.

`POST /api/v1/models/test` can test explicit role configuration supplied in the request.

Deployment environment variables remain deployment defaults. Active `RCA_*` model overrides are surfaced to the frontend instead of silently making a save appear to revert.

A run can carry an explicit `config_override` snapshot from the current form so a controlled run is reproducible and independent of later UI changes.

## 11. Storage and sessions

Default local storage:

```text
~/.rca_analyst_poc/web_backend/
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
    cases/<case_id>/...
  sessions/
  reports/
  logs/
  tmp/
```

RunPod typically uses `/workspace/rca-data` through `RCA_STORAGE_ROOT`.

There remains one hardware-independent session concept. Legacy desktop payloads are preserved during migration rather than silently discarded.

## 12. Metrics and benchmarking

Per model call, capture where available:

- case ID;
- role/stage;
- provider/model/endpoint;
- prompt/completion/reasoning/total tokens;
- request duration;
- generation throughput;
- finish reason;
- retry count;
- transport.

Per testcase, aggregate:

- elapsed time;
- model time;
- estimated non-model/Python time;
- call counts;
- tokens;
- retries;
- weighted throughput;
- role breakdown;
- requirement-result counts.

Per stage, aggregate elapsed/model time, calls, tokens, retries, throughput and models/endpoints used. Failed calls contribute to statistics rather than disappearing from the benchmark.

## 13. Security

Local loopback may run without auth. Remote profiles support:

- bearer token through `RCA_API_TOKEN`;
- explicit CORS;
- HTTPS/TLS at the RunPod/reverse-proxy edge;
- private model endpoints wherever practical.

Secrets are not committed in source.

## 14. Desktop fallback and migration safety

The PySide desktop application remains packaged through `run_desktop.py` / `run_desktop.bat` as a fallback/reference until Web/live parity is explicitly accepted.

Application defects must not be solved by weakening RCA semantics. Semantic changes require real failure evidence and regression coverage.

## 15. Python 3.9 compatibility

The server layer continues to avoid runtime-evaluated PEP 604 annotations in FastAPI/Pydantic paths so the supported Dell Python 3.9 environment remains valid.
## 16. v1.8.9 deterministic integration and testcase lifecycle hardening

v1.8.8 preserved the Web/FastAPI modular-monolith boundary and added two coordinated contracts.

**RCA Core v0.8.8 (carried by v1.8.9):** compiler batches are completeness-checked with one bounded missing-ID recovery; provenance/source-clause inventories become structural-completion targets; independent verification reconstructs normative polarity; source grounding tolerates formatting-only differences and explicit source-order ellipsis; evidence materiality requires an authoritative structured dependency; arbitration receives an issue-scoped exact source packet; VERIFIED semantic fact IDs are accepted as RCA provenance. Python remains deterministic compliance authority.

**Testcase lifecycle:** the Run Manager registers each testcase as RUNNING before pipeline execution and updates the same record to PASS/FAILED/CANCELLED. `/runs/{run_id}/result` therefore exposes the current case immediately for both single and batch runs. The Web Tests selector is a lifecycle selector, not merely a completed-results selector.

A running testcase can be selected after browsing completed cases. Live Pipeline, Logs and partial Stats remain available; final-only views explicitly report that no final testcase result exists yet. The browser does not infer lifecycle state from pipeline labels.



## v1.8.9 reconnect and live-view state

The backend Run Manager remains authoritative for run lifecycle. On connection, the Web client reads `/runs` and rediscoveries active non-terminal runs rather than relying on browser state. A live run can therefore survive tab closure/reopening as long as the backend process itself remains alive.

Structured pipeline Input/Output rendering preserves UI state using stable semantic tree paths scoped by profile/run/testcase/stage/view. Polling can replace live data without collapsing objects the user is inspecting. Selected testcase and selected stage are stored per run.


## v1.8.10 testcase failure containment

Sequential testcase execution treats the testcase as the isolation unit. Pipeline construction and execution are inside one testcase-local `try` boundary. `AnalysisCancelled` remains run-level and stops the suite; `PipelineValidationError` and unexpected testcase exceptions are persisted on the affected case and execution continues.

Unexpected failures persist exception type/message/traceback plus the partial testcase pipeline. A batch is `COMPLETED` when all requested testcase slots were attempted; testcase `FAILED` and semantic acceptance remain independent dimensions.

Session autosave preserves partial `result` data and augments it with `run_failure` when an unrecoverable run-level failure also exists.

## v1.8.10 semantic-repair containment

Semantic arbitration is not allowed to become an application-liveness dependency. Contract-invalid field patches are rejected atomically and the original semantic preparation remains in force. The raw arbitration attempt is retained and the pipeline continues with unresolved material semantics. Field omission is accepted only when every governing material issue for that exact field is explicitly unresolved.

Independent verifier equality uses executable behavior semantics and normalized structured persistence scope, not descriptive prose fields.


## v1.8.11 live-suite contract hardening

The application topology is unchanged. v1.8.11 carries Core v0.8.10 and preserves v1.8.10 testcase isolation/session forensics. New core-facing observability persists arbitration contract-rejection reasons with the raw model attempt. The full v1.8.10 RunPod session completed 17/17 cases with 11/17 semantic PASS, proving batch continuation and TC12/TC17 behavior before this patch.


## v1.8.12 Models & Inference endpoint contract

The backend distinguishes endpoint reachability from model readiness. `/models/discover` reports `AVAILABLE`, `NO_MODELS`, or `UNAVAILABLE`; compatible provider catalog aliases are normalized structurally; optional provider metadata probes enrich runtime context without controlling the external server. The Web UI invalidates endpoint-specific model/context data when an endpoint is edited and displays persistent discovery/test status. Model Test performs a minimal actual inference request. No RCA semantic logic moved into the browser or backend model-discovery layer.
