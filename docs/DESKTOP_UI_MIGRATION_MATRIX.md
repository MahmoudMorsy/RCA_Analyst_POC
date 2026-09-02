# RCA Analyst v1.8.4 — Desktop UI → Web UI/API Migration Matrix

Baseline: frozen desktop RCA Analyst v0.8.4. This matrix is the functional migration contract for the v1.8.4 Web/backend refactor. RCA semantics are out of scope.

## Connection / backend

| Desktop control/function | Current source/config | Current coupling | v1.8.4 API | Web UI |
|---|---|---|---|---|
| LM Studio Base URL | `AppConfig.base_url`, `MainWindow.base_url` | Qt directly constructs `LMStudioClient` | `GET/PUT /api/v1/config`, backend profile model endpoint | Backend Profiles panel + Model Endpoints |
| Primary model | `AppConfig.model`, `model_combo` | Qt/CLI constructs primary client | `GET /models`, `GET/PUT /config` | Primary Model selector |
| Refresh Models | `refresh_models()` | Direct LM Studio HTTP call from desktop | `GET /api/v1/models?refresh=true` | Refresh Models button |
| Test Connection | `test_connection()` | Direct LM Studio HTTP call from desktop | `POST /api/v1/models/test` + `GET /health` | Test Connection button |
| Theme | `AppConfig.theme` | Qt stylesheet | frontend-only preference; excluded from RCA config | Dark/Light selector |

## Primary model / RCA configuration

| Desktop control | Config field | v1.8.4 config section | Web control |
|---|---|---|---|
| Primary temperature | `temperature` | `rca.primary.temperature` | numeric input |
| Primary reasoning | `reasoning_effort` | `rca.primary.reasoning_effort` | select |
| Primary output tokens | `max_tokens` | `rca.primary.max_tokens` | numeric input |
| Request timeout | `request_timeout_seconds` (not visible) | `rca.request_timeout_seconds` | advanced numeric input |
| Semantic preparation | `semantic_preparation_enabled` | `rca.semantic_preparation_enabled` | checkbox |
| Semantic token budget | `semantic_preparation_max_tokens` | `rca.semantic_preparation_max_tokens` | numeric input |
| 27B semantic arbitration | `semantic_arbitration_enabled` | `rca.semantic_arbitration_enabled` | checkbox |
| 27B RCA when justified | `rca_synthesis_enabled` | `rca.rca_synthesis_enabled` | checkbox |
| 4B intake | `fast_intake_enabled` | `rca.fast_intake_enabled` | checkbox |
| Intake routing Auto/Always/Off | `fast_intake_mode` | `rca.fast_intake_mode` | select |
| Availability tokens | `fast_source_availability_max_tokens` | `rca.fast_source_availability_max_tokens` | numeric input |
| Content classification tokens | `fast_content_classification_max_tokens` | `rca.fast_content_classification_max_tokens` | numeric input |
| 4B hypothesis review | `fast_hypothesis_review_enabled` | `rca.fast_hypothesis_review_enabled` | checkbox |
| Hypothesis review tokens | `fast_hypothesis_review_max_tokens` | `rca.fast_hypothesis_review_max_tokens` | numeric input |
| 4B wording audit | `fast_final_review_enabled` | `rca.fast_final_review_enabled` | checkbox |
| Wording audit tokens | `fast_final_review_max_tokens` | `rca.fast_final_review_max_tokens` | numeric input |
| Final review reasoning | `fast_final_review_reasoning_effort` | `rca.fast_final_review_reasoning_effort` | select |
| Final review thinking | `fast_final_review_thinking_mode` | `rca.fast_final_review_thinking_mode` | select |
| Final review transport | `fast_final_review_transport` | `rca.fast_final_review_transport` | select |
| Shared 4B model | `fast_repair_model` | `rca.small_model.model` | model selector |
| Shared 4B reasoning | `fast_repair_reasoning_effort` | `rca.small_model.reasoning_effort` | select |
| Shared 4B thinking | `fast_repair_thinking_mode` | `rca.small_model.thinking_mode` | select |
| Shared 4B transport | `fast_repair_transport` | `rca.small_model.transport` | select |

### Legacy/hidden configuration preserved for compatibility

These fields are not active v0.8.4 topology controls, but existing saved config/session data must continue to load and round-trip without loss: `primary_large_case_max_tokens`, `primary_large_case_requirement_threshold`, `primary_phase_a_chunk_size`, `max_repair_passes`, `deterministic_repair_enabled`, `fast_intake_max_tokens`, `fast_atomic_claim_enabled`, `fast_atomic_claim_max_tokens`, `fast_requirement_language_enabled`, `fast_requirement_language_max_tokens`, `fast_repair_enabled`, `fast_repair_max_tokens`, `fallback_to_primary_repair`, `fast_repair_temperature`.

They are exposed in the Web UI under **Legacy / Compatibility Settings**, collapsed by default.

## New inference-engine configuration surface

The v0.8.4 Qt source does not expose engine-load controls, but the deployment refactor requires a stable place for hardware/provider-dependent settings. They are explicitly **not RCA decision logic** and are capability-gated:

- CPU threads
- GPU layers/offload
- tensor split
- Flash Attention
- physical batch size
- eval batch size
- parallel/concurrency slots
- context size override
- provider-specific options

API: `GET /api/v1/capabilities`, `GET/PUT /api/v1/config` (`inference` section). Unsupported settings are disabled in the Web UI and rejected by backend validation if explicitly forced.

## Case execution controls

| Desktop action | Current implementation | v1.8.4 API | Web UI |
|---|---|---|---|
| Paste complete testcase | `composer` | `POST /runs` body | Case Input editor |
| Load TEST-001 | local `examples/TEST-001.txt` | `GET /examples/TEST-001` | Load TEST-001 |
| Load TEST-002 | local file | `GET /examples/TEST-002` | Load TEST-002 |
| Load TEST-003 | local file | `GET /examples/TEST-003` | Load TEST-003 |
| Analyze Case | `AnalysisWorker` QThread | `POST /runs` (`run_type=single`) | Analyze Case |
| Run TEST-001→TEST-003 | `BatchAnalysisWorker` | `POST /runs` (`run_type=builtin_regression`) | Run TEST-001→TEST-003 |
| Run Test Bundle ZIP | QFileDialog + `load_test_bundle_zip` | `POST /files`, then `POST /runs` (`run_type=bundle`) | Upload/Run Bundle |
| Stop/Abort | cooperative `CancellationToken` + active HTTP close | `POST /runs/{id}/cancel` | Stop button |
| New/Clear | local UI reset | frontend state only | New/Clear |

## Result/inspection tabs

| Desktop tab | Data source | v1.8.4 endpoint | Web tab |
|---|---|---|---|
| Final Report | `PipelineResult.final_report` | `/runs/{id}/result`, report download | Final Report |
| Live Pipeline | trace callback events | `/runs/{id}/pipeline`, `/runs/{id}/events` SSE | Live Pipeline |
| Stage Input/Output | trace event fields | pipeline stage detail | Stage Inspector |
| Stage Log | progress callback | `/runs/{id}/logs` | Stage Log |
| Sequential Batch | batch records + summaries | run result/status for batch | Sequential Batch |
| Validation | `validated.issues` | `/runs/{id}/result` | Validation |
| Canonical Input | `canonical_case` | `/runs/{id}/result` | Canonical Input |
| Structured JSON | `validated.semantic` / result payload | `/runs/{id}/result` | Structured JSON |
| API Stats | `stats` | `/runs/{id}/metrics` | Metrics |
| LLM Attempts | `attempts` | `/runs/{id}/result` / metrics | LLM Attempts |
| Repair Routing | `repair_log` | `/runs/{id}/result` | Repair Routing |

## Export / session / history

| Desktop capability | Current implementation | v1.8.4 migration |
|---|---|---|
| Export report `.md` | direct local write | backend-generated report + `GET /runs/{id}/report/download` |
| Export session `.json` | direct local write of result/failure | `POST /sessions/save`, `GET /sessions/{id}/download` |
| Failed-session export | GUI `failure_diagnostics` | persisted automatically per failed run; downloadable |
| Batch output directory | direct `batch_results/` | storage abstraction `runs/<run_id>/...` |
| Run history | batch filesystem only | persistent backend run index + `GET /runs` |
| Session load | not exposed by v0.8.4 Qt UI | added in v1.8.4 per migration prompt; legacy session migration supported |

## Footer/status behavior

Desktop `stage_label` + indeterminate/progress bar become the Web **Run Status Bar** driven only by backend run state and pipeline events. Explicit backend states: `QUEUED`, `INITIALIZING`, `RUNNING`, `CANCELLING`, `CANCELLED`, `COMPLETED`, `FAILED`.

## Functional parity rule

The Web frontend has zero RCA decision logic. It may capability-gate controls and render backend state, but all RCA routing, retries, repairs, compliance, validation and model-role decisions remain backend/core responsibilities.
