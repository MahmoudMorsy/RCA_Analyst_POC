# RCA Analyst Version History

## Current release — v1.8.11 / RCA Core v0.8.10 candidate

- The exact v1.8.10 27B RunPod suite completed all 17 cases; 11/17 passed semantic acceptance. TC12 and TC17 passed their live targets.
- v1.8.11 rejects structurally incomplete VERIFIED verifier fingerprints instead of converting missing verifier fields into false compiler disagreements.
- RCA Core v0.8.10 introduces canonical requirement persistence scope, atomic-equivalence handling for redundant unchanged arbitration fields, provenance companion targeting for newly-created semantics, and canonical direct-observation closure in RCA packets.
- Arbitration rejection reasons are now persisted with the raw attempt.
- Release validation: **241 passed** in the working tree and **241 passed** from a clean fresh extraction of the exact final ZIP; live full-suite v1.8.11 validation remains required before freezing v0.8.10.

## v1.8.10 → v1.8.11

See `docs/V1.8.11_RELEASE_NOTES.md` and `docs/RCA_CORE_ARCHITECTURE_v0.8.10.md`.

## v1.8.9 → v1.8.10

See `docs/V1.8.10_RELEASE_NOTES.md` and `docs/RCA_CORE_ARCHITECTURE_v0.8.9.md`.

## v1.8.8 → v1.8.9

See `docs/V1.8.9_RELEASE_NOTES.md` and `docs/RCA_CORE_ARCHITECTURE_v0.8.8.md`.

## Current version model

- **Application version:** v1.8.11 — live-full-suite semantic-contract hardening on the v1.8.10 failure-containment application baseline.
- **Embedded RCA Core:** v0.8.10 candidate — verifier-completeness, canonical persistence scope, arbitration equivalence/provenance and RCA packet closure on v0.8.9.
- **Validation:** v1.8.10 completed 17/17 live executions with 11/17 semantic PASS and clean TC12/TC17 anchors. Automated v1.8.11 release gates must pass, then the exact package must rerun the full suite before v0.8.10 can freeze.
- Frozen regression anchors remain v0.4.3 TEST-003 and v0.5.2 TC1–TC3, with v0.3.6 TEST-001 retained as an earlier checkpoint.

## v1.8.7 → v1.8.8

- Ran the complete 17-case RunPod regression after v1.8.7 fixed Qwen Thinking Off and reduced semantic-call runtime. All 17 cases executed, but only 2 met the old semantic-acceptance manifest; the suite exposed systemic defects beyond TC17.
- Added authoritative expected-ID completeness checks to every Requirement Compilation batch and one bounded missing-ID semantic recovery call, fixing the TC20 class where entire requirements disappeared.
- Expanded targeted structural completion to repair complete source-clause provenance inventories plus timing/persistence linkage, with at most two compact passes and no full-IR regeneration.
- Strengthened compiler and independent-verifier contracts for executable trigger/behavior/timing/persistence fields and independent normative polarity; Python still does not interpret modality prose.
- Relaxed only formatting-level source-grounding differences (bullets, line breaks, punctuation, explicit ordered ellipsis) while retaining hard failure for invented source content.
- Corrected compliance materiality so narrative/same-signal overlap alone cannot block deterministic compliance; authoritative structured evidence dependencies remain conservative.
- Scoped semantic arbitration to exact issue-related authoritative source fields to reduce repeated prompt bloat/truncation while keeping the replacement validator strict.
- Fixed RCA hypothesis provenance so VERIFIED semantic fact IDs are valid references and unknown/unresolved fact IDs are not.
- Strengthened semantic acceptance with an always-on final internal-ERROR check so TC4/TC11-style false-clean conservative verdicts cannot pass.
- Added backend testcase lifecycle records before execution and a universal Web Tests selector so running single/batch cases remain visible and selectable.
- Added nine v1.8.8 regressions covering these failure classes.
- Release validation: **216 passed** in the working tree and **216 passed** from a clean fresh extraction.

## v1.8.6 → v1.8.7

- Live RunPod TC17 proved the 27B could reconstruct the nested Boolean requirement correctly, but exposed ineffective Thinking Off propagation, hidden reasoning-content cost, incomplete behavior shells, full-IR structural-repair token explosions, unresolved persistence scope, over-broad narrative materiality and arbitration provenance gaps.
- Added request-level llama.cpp/Qwen `enable_thinking` propagation with bounded compatibility fallback and explicit reasoning-content observability.
- Replaced full Requirement IR structural completion with targeted field patches guarded by Python against untargeted overwrite.
- Strengthened compiler/verifier executability contracts for required behavior, simple negative predicates, literal comparison values and explicit persistence.
- Made unresolved persistent scope a structural evidence defect and added explicit whole evaluated-interval scope semantics only when grounded by the source.
- Corrected materiality so requirement association alone does not turn narrative ambiguity into a compliance blocker; structured Requirement-IR dependencies remain conservative.
- Kept strict arbitration validation and tightened the model contract so provenance must be attached to the executable repaired node.
- Added live-TC17-derived v0.8.6 regressions.
- Release validation: **207 passed** in the working tree and **207 passed** from a clean fresh extraction.

## v1.8.5 → v1.8.6

- Fixed the Web Live Pipeline persistence defect where a later COMPLETE event replaced a RUNNING stage record and erased the earlier Stage Input. Stage updates now merge non-empty state and preserve structured input/output.
- Added human-readable structured pipeline inspection, including Verified Semantic Representation, while retaining raw JSON for exact forensic review.
- Repaired batch Web parity: results are published case-by-case and a selected testcase drives Final Report, Validation, Canonical Input, Structured JSON, LLM Attempts, Repair Routing, logs, pipeline and statistics.
- Added per-testcase and per-stage telemetry aggregation, including failed model calls, role/model/endpoint/token/retry/throughput data and requirement-result counts.
- Fixed model discovery/test UX so the endpoint currently typed in the Web form can be queried directly; saving first is no longer required.
- Exposed active deployment environment overrides and added per-run `config_override` snapshots so environment defaults no longer silently prevent controlled experiments.
- Corrected inference-engine UX: external llama.cpp/LM Studio/vLLM launch parameters are not represented as backend-controlled when the backend does not own those processes.
- Added capacity-neutral Critical Semantic Model Routing. Semantic preparation and independent semantic verification can independently route to the configured Small / Utility or Primary role. Python compliance authority is unchanged.
- Promoted embedded RCA Core from v0.8.4 candidate to **v0.8.5 candidate** after live Dell/RunPod TC17/TC12 evidence invalidated v0.8.4 as a freeze candidate.
- Added independent verifier structured fingerprints so Boolean/source semantics are reconstructed separately from compiler IR; a `VERIFIED` label cannot hide a structural mismatch such as TC17 `A AND (B OR C) AND D` regrouping.
- Hardened semantic arbitration: compliance-linked evidence repairs must be executable structured facts and cannot resolve material issues using notes-only explanations or `OTHER` placeholders.
- Tightened Evidence Semantic Annotation output contract to legal enum values without Python NLP mappings for model-invented operators.
- Retained all frozen evidence/timing rules, Python 3.9 support, provider-neutral ModelGateway, backend-owned run lifetime and desktop fallback.
- Added v1.8.6 release notes, RCA Core v0.8.5 architecture, updated API/config/deployment/application architecture documentation and new regression coverage.
- Release validation: **201 passed** in the working tree and **201 passed** from a clean fresh extraction.

## v1.8.4 → v1.8.5

- Maintenance compatibility release for the Web/backend architecture.
- Fixed Python 3.9 FastAPI startup failure caused by `T | None` annotations in `rca_server`.
- Replaced only server-layer optional annotations with `typing.Optional`; RCA Core v0.8.4 semantics remain unchanged.
- Strengthened compatibility tests so future Web/backend changes are checked against the supported Dell Python 3.9 runtime.

# RCA Analyst POC — Version History

## v0.8.4 → v1.8.4

- Promoted the application major version to **v1.8.4**, intentionally retaining minor/patch `8.4` while marking the major Web/backend/deployment refactor.
- Frozen RCA semantic baseline remains **RCA Core v0.8.4**; requirement semantics, evidence semantics, deterministic compliance/timing, repairs, arbitration, RCA routing, validation and report semantics are not redesigned.
- Replaced the primary monolithic desktop execution shell with a browser Web UI and versioned FastAPI `/api/v1` backend.
- Added backend-owned asynchronous run jobs and explicit `QUEUED / INITIALIZING / RUNNING / CANCELLING / CANCELLED / COMPLETED / FAILED` states. Browser connections no longer own RCA execution lifetime.
- Added persistent run metadata, logs, dynamic pipeline stages, metrics, results and report/session artifacts; clients can reconnect after reload/disconnection.
- Added provider-neutral `ModelClient` protocol and `ModelGateway`. `RCAPipeline` no longer directly imports the LM Studio transport; LM Studio/llama.cpp/vLLM-compatible endpoints are deployment adapters.
- Added configuration separation between hardware-independent RCA behavior, model endpoint/role configuration, inference-engine settings and detected infrastructure.
- Added capability discovery and capability-gated inference settings.
- Added backend-managed file storage and configurable storage roots for Dell local disks, RunPod persistent mounts and future home-server storage.
- Added session schema v2 with deployment/hardware/inference metadata and deterministic legacy desktop-session wrapping with original payload preservation.
- Added run history and benchmarking metadata for cross-hardware TC comparisons.
- Added telemetry for CPU/RAM/GPU/VRAM/utilization/temperature/power/disk where available; telemetry remains observational.
- Added bearer-auth/CORS support for remote backends and deployment profiles/guides for Local Dell, RunPod and Home AI Server.
- Added Dockerfile/docker-compose and environment overrides for model endpoints/providers/storage.
- Preserved the complete desktop UI as a frozen fallback/reference while the Web UI is validated.
- Added Desktop UI → Web UI/API migration matrix, risk/coupling inventory, API/config/deployment documentation and v1.8.4 release notes.
- Existing 175 RCA tests remain green; expanded application/backend suite totals **191 passed**.

## v0.8.3 → v0.8.4

- Removed the small-case combined semantic-preparation response. Requirement IR compilation and evidence semantic annotation are now always separate fast-model components so a malformed evidence envelope cannot invalidate otherwise usable Requirement IR output.
- Added specialized v0.8.4 system prompts for Requirement Semantic Compilation and Evidence Semantic Annotation.
- Added narrow evidence transport canonicalization for the live TC17 v0.8.2 envelope failure where explicit `facts`/`unresolved_semantics` were nested under annotation `resolution`. This repair is schema-only; Python does not infer evidence meaning from prose.
- Stray annotation-level `scope_id` is never assigned to a fact by Python. Empty values are discarded; non-empty values are retained as unresolved transport information.
- Added one conditional targeted 4B Evidence Semantic Completion pass for structured evidence defects; only affected evidence IDs are reannotated and Requirement IR compilation is not repeated.
- Tightened natural-language persistence execution: `PERSISTENT_STATE` becomes executable interval evidence only with `scope.resolution=RESOLVED` and a concrete non-empty `scope_id`.
- Extended strict 27B arbitration replacement validation to evidence annotations. Persistent evidence repairs without a concrete resolved scope are rejected; genuinely unresolved items must remain in `unresolved_issue_ids`.
- Added TC17 live-failure-shape regressions for malformed evidence envelopes, scope safety, always-separated small-case semantic calls, and targeted evidence completion.
- Preserved v0.8.3 Requirement IR transport/execution separation and targeted structural IR completion.
- Automated local suite at release-candidate packaging: **175 passed**.

## v0.8.2 → v0.8.3

- Corrected the live TC12 v0.8.2 compiler-transport failure where multiple PREDICATE nodes carried grounded source phrases, operators and values but omitted the explicit `signal` field, causing Pydantic to abort the whole RequirementCompilationBatch before verification/arbitration.
- Separated transport-valid Requirement IR from executable Requirement IR. Partial compiler AST objects are preserved for inspection/repair, but Python semantic integrity marks malformed nodes material and blocks deterministic execution.
- Added structural checks for missing predicate signal/operator, invalid Boolean node shapes, incomplete trigger/required-behavior objects and timing objects without `limit_ms`.
- Added one bounded targeted 4B structural-completion recompilation for only the affected requirements before the independent semantic verifier and before any 27B semantic arbitration. Python does not infer missing semantics from natural-language source text.
- Strengthened the fast compiler contract so every PREDICATE explicitly returns `signal`, `operator` and `value`; `source_phrase`/`semantic_id` are provenance, not substitutes for executable fields.
- Kept the v0.8.2 27B arbitration replacement boundary strict: arbitration still rejects missing predicate signals/operators and malformed Boolean structure.
- Preserved the live-verified TC12 timestamp parser correction (`99.900`, `100.000`, `100.600`, `101.100`) and deterministic transition metadata.
- Added v0.8.3 regressions proving transport-partial IR no longer aborts the case, remains non-executable, can receive one cheap fast-model structural completion, and does not force a 27B call when that completion succeeds.
- Working-tree automated suite after implementation: **168 passed**.

## v0.8.1 → v0.8.2

- Corrected the live TC17 v0.8.0 failure in which semantic compilation and 27B arbitration recognized the nested requirement logic in prose but failed to materialize it into executable Requirement IR fields.
- Tightened the semantic compiler prompt so mixed German/English wording, nested AND/OR logic, or unusual sentence order are not treated as ambiguity when the meaning is actually clear. If the model can explain the semantic structure, it must encode it into the condition/behavior/timing/persistence IR fields.
- Made `SemanticArbitrationResponse` a strict repair boundary: returned replacement IRs must be executable and VERIFIED; genuine ambiguity is represented only through unresolved issue IDs. This blocks the TC17 pseudo-repair pattern (`AMBIGUOUS`, null executable fields, prose-only source clauses).
- Added explicit `MECHANISM` evidence role and changed RCA routing so contextual text, ticket titles, symptom statements, and failed output observations do not by themselves justify a 27B RCA call.
- Cross-check diagnostic and historical semantic roles against authoritative source classes before routing or packet inclusion.
- Prevented output point-state symptoms from being promoted to mechanism evidence.
- Added TC17 regressions for arbitration-repair strictness and no-RCA routing of context/symptom evidence.
- Working-tree automated suite after implementation: **165 passed**.

## v0.8.0 → v0.8.1

- Corrected the first live TC12 v0.8.0 failure while preserving the v0.8 semantic-compiler / deterministic-compliance architecture.
- Replaced the single oversized TC12 semantic-preparation response with bounded fast-model Requirement IR batches and one narrow evidence-language annotation batch; small cases still use one compact preparation call.
- Added null-safe envelope normalization for optional semantic strings such as `required_behavior.event`, preventing JSON `null` from aborting otherwise usable structured output.
- Added an independent compact 4B semantic verifier after IR compilation because the live retry demonstrated that a compiler can omit an IF condition from both the IR and its own source-clause audit.
- Verifier mismatches become material semantic issues and are resolved together by the existing one-call 27B semantic arbitration path. Repaired IR is fast-verified once more, with no second 27B semantic retry.
- Compacted semantic prompts to reduce schema/context pressure on the local Qwen3.5-4B model.
- Confirmed that the v0.8.0 decimal timestamp parser fix worked in the live TC12 run.
- Working-tree automated suite after implementation: **163 passed**.

## v0.7.1 → v0.8.0

- Replaced the v0.7.x always-on decomposed 27B topology with an adaptive semantic-compiler architecture after live TC12/TC17 invalidated v0.7.1 on both latency and correctness.
- Added one normal case-level 4B semantic-preparation stage that compiles free-form requirements into declarative Requirement IR and annotates language-derived evidence in shared context.
- Replaced flat requirement DNF hints with recursive Boolean AST conditions plus explicit trigger, behavior, timing, persistence and relationship objects.
- Added compiler source-clause self-audit with `semantic_id` linkage and Python integrity checks so a TC17-style dropped condition clause is detected before compliance.
- Stopped deterministic Python from promoting natural-language `remained ... throughout ...` statements into interval evidence in the v0.8 production path; contextual scope must be resolved by the LLM before persistent evidence becomes executable.
- Added one bounded case-level 27B semantic arbitration call for all materially unresolved compliance semantics; no per-sentence calls and no repeated primary semantic retry loop.
- Added a new Python deterministic compliance engine that executes verified Requirement IR/facts and owns applicability, state/transition/persistence semantics, timing, relationships, evidence bucketing and final verdicts.
- Removed mandatory 27B Phase A and requirement-count-driven 27B chunking from the production path.
- Added RCA routing so a bare violation does not trigger deep RCA; mechanism-oriented evidence is required.
- Added compact RCA Evidence Packets and removed original natural-language requirement wording from the default 27B RCA prompt, preventing RCA synthesis from reopening verified requirement semantics.
- Made 27B RCA synthesis conditional and kept hypothesis review/wording audit semantically read-only.
- Fixed decimal timestamp corruption in intake canonicalization by requiring whitespace after numbered-list prefixes; `99.900 s`/`100.000 s` are preserved.
- Added CLI/GUI controls for semantic preparation, semantic arbitration and conditional RCA; hid v0.7 Phase-A/large-case/repair tuning controls from the v0.8 production GUI while preserving config compatibility.
- Added exact v1.3 TC12/TC17 regression fixtures and routing tests. TC12 now deterministically protects 1100/800/+300 ms; TC17 protects nested-condition violation and override non-applicability.
- Working-tree automated suite: **160 passed**.

This file is the chronological release-history log for the RCA Analyst POC. It complements `CHANGELOG.md`, which is ordered newest-first. Every known release is presented as a transition from the preceding release so architectural evolution can be followed directly.

For v0.1, which predates the formal changelog, the entry is reconstructed from the repository README section **Why v0.2 exists**. All later entries come from the maintained changelog/release notes.

**Earliest known release:** v0.1
**Previous release:** v1.8.8

## v0.1 — Earliest known baseline

- First real local Qwen3.8-27B Q6_K + Medium RCA POC run; reduced the previously observed runtime from roughly 70 minutes to roughly 32 minutes.
- Used the early model/validator architecture before deterministic source-boundary parsing.
- The run exposed the gaps that motivated v0.2: ticket-description prose could be promoted as an observation, the dedicated Reported Test Result was not authoritative, requirement decomposition could be incomplete without failing validation, evidence mapping could be missing/misbucketed, and Section 10 evidence closure was incomplete.
- This release predates the formal changelog; its baseline description is reconstructed from the repository README section "Why v0.2 exists."

## v0.1 → v0.2.0

Changes introduced in **v0.2.0** relative to **v0.1**:

- Added deterministic manual-case parser and authoritative `CanonicalCase`.
- `Reported Test Result` now maps deterministically to `REPORTED_OBSERVATION`.
- Ticket Description is no longer auto-promoted to a confirmed finding.
- LLM response changed from full `SemanticAnalysis` to semantic-only `SemanticReasoning`.
- Added `applicability_condition` to requirement decomposition.
- Added strict decomposition completeness validation.
- Added relevant current-observation mapping validation.
- Added applicability/evaluation bucket separation checks.
- Added timing trigger-timestamp and persistence-coverage evidence checks.
- Reworked Section-10 evidence selection to dependency closure across applicability + conditional evaluation evidence.
- Added Canonical Input GUI tab and canonical data to session exports.
- Added parser, regression, formatter and fake-LLM repair-flow tests.

## v0.2.0 → v0.2.1

Changes introduced in **v0.2.1** relative to **v0.2.0**:

- Fixed a false-fatal `MISSING_CONDITION_APPLICABILITY_NEED` failure seen on REQ-003-style `if` requirements.
- Missing applicability evidence is now normalized deterministically once condition/trigger decomposition is known.
- A condition need incorrectly labelled `TRIGGER` is corrected to `APPLICABILITY` when the requirement has no true trigger.
- If a model omits the missing applicability need entirely, the validator derives a neutral evidence request from the decomposed condition/trigger instead of wasting a repair pass.
- Added regression tests for condition relabelling, omitted condition needs, and omitted trigger needs.

## v0.2.1 → v0.3.0

Changes introduced in **v0.3.0** relative to **v0.2.1**:

- Added persistent per-call attempt/audit records: raw LLM JSON, reasoning content when returned, semantic object before validation, normalized semantic object, validation issues, and API stats.
- Added **Attempts / Repair Log** GUI tab.
- Failed runs now retain diagnostics and can export `RCA_Failed_Session.json`.
- Added compact requirement-only repair schema so requirement validation failures do not regenerate the entire semantic response.
- Normalizes applicability evidence labels for permissive requirements too.
- Removes unsupported Case-Validity evidence requests unless tied to explicitly tagged ticket scope metadata.
- Reworked Section 10 into a concise deterministic evidence plan with duplicate trigger/timestamp merging and conditional timing/persistence closure.
- Removes internal evidence-class/debug terminology from analyst-facing evidence requests.
- Expands bare relevance labels (`PRIMARY`, `SECONDARY`, `PERIPHERAL`) deterministically instead of repairing them with the LLM.
- Added v0.3 regression tests and targeted-repair tests.

## v0.3.0 → v0.3.1

Changes introduced in **v0.3.1** relative to **v0.3.0**:

- Fixed false `MISSING_PERSISTENCE_EVALUATION_NEED` / `MINIMUM_EVIDENCE_PERSISTENCE_CLOSURE_FAILED` errors for timed transition requirements that merely require 500 ms observation coverage.
- Added explicit distinction between true persistence semantics (`remain`, `stay`, prohibitive non-occurrence) and ordinary timing-window coverage.
- Auto-maps supplied reported/direct observations that mechanically match a requirement response instead of spending an LLM repair pass.
- Derives missing true-persistence `OBSERVATION_INTERVAL` evidence needs deterministically.
- Prevents derived `validated.*` errors from being sent to the LLM for repair.
- Global derived errors no longer disable targeted repair for requirement-local semantic defects.
- Normalizes unsafe relevance prose that introduces causal/cross-requirement interpretation.
- Added regression tests and replayed the real failed v0.3 session: first-pass semantic output now validates with zero critical errors.

## v0.3.1 → v0.3.2

Changes introduced in **v0.3.2** relative to **v0.3.1**:

- Normalize timed-requirement evidence needs deterministically instead of requesting an LLM repair for missing/mislabelled `TIMING` bookkeeping.
- Collapse duplicate trigger/timestamp/window/timebase requests into a concise canonical evidence bundle.
- Add a relevance guard that prevents non-timestamped observations from being described as proving a timing-bound failure.
- Preserve the v0.3.1 separation between true persistence and ordinary timed-window coverage.

## v0.3.2 → v0.3.3

Changes introduced in **v0.3.3** relative to **v0.3.2**:

- Add a soft-converse guard for PERMISSIVE relevance prose so one-way permissions cannot become gates, prerequisites, or necessity/exclusivity claims.
- Remove causal/alternative-failure wording from requirement relevance; relevance remains requirement-local and descriptive.
- Compact true-persistence missing evidence into one observation-interval acquisition need instead of duplicate RESPONSE + OBSERVATION_INTERVAL prose.
- Extend the semantic prompt with the same relevance constraints to reduce normalization work while keeping Python authoritative.
- Replay the v0.3.2 TEST-001 first response with zero critical errors and no repair requirement.

## v0.3.3 → v0.3.4

Changes introduced in **v0.3.4** relative to **v0.3.3**:

- Add `NOT_REQUIRED` as the canonical evaluation-sufficiency state for PERMISSIVE requirements; normalize `SUFFICIENT_CONFORMANCE`/`INSUFFICIENT` to it without an LLM repair.
- Reject `NOT_REQUIRED` for MANDATORY/PROHIBITIVE requirements.
- Broaden the timing-relevance guard to catch statements that a complete timed response "did not occur" when timestamps/full-window coverage are missing.
- Extend semantic/repair prompts with the same invariants.
- Replay the real v0.3.3 TEST-001 first response with zero critical errors and no repair requirement.

## v0.3.4 → v0.3.5

Changes introduced in **v0.3.5** relative to **v0.3.4**:

- Stop deterministic response-observation auto-mapping for PERMISSIVE requirements; clear any supplied ordinary evaluation evidence and keep `evaluation_sufficiency = NOT_REQUIRED`.
- Tighten relevance normalization for phrases that require a condition to be excluded/confirmed before attributing the symptom to a failure/violation.
- Preserve already-correct timed relevance prose when it explicitly states that timing remains unevaluable because timestamp/window evidence is missing.
- Extend semantic/repair prompts with the same invariants.
- Replay the real v0.3.4 TEST-001 first response with zero critical errors and no LLM repair.

## v0.3.5 → v0.3.6

Changes introduced in **v0.3.6** relative to **v0.3.5**:

- Generalize logical-direction protection to every one-way `if` / `when` / `upon` requirement, not only PERMISSIVE requirements.
- Normalize relevance prose that invents `only if` / `only when` / necessary-condition semantics absent from the source.
- Reject converse/exclusivity invention in `faithful_meaning` so genuine semantic reversal triggers targeted repair instead of being silently accepted.
- Preserve explicit source exclusivity such as `only if`, `only when`, and `if and only if`.
- Remove generic explain/explanation wording from requirement relevance; causal explanation remains hypothesis-only.
- Extend analyzer/repair prompts with the same general invariants.
- Replay the real v0.3.5 TEST-001 first response with zero critical errors and no LLM repair.

## v0.3.6 → v0.4.0

Changes introduced in **v0.4.0** relative to **v0.3.6**:

- Introduce explicit applicability evidence binding as an architectural contract: `applicability_evidence_ids` is required in LLM structured output, and resolved applicability without a valid current-case evidence citation is downgraded to UNKNOWN.
- Atomize conservative direct-observation lines and preserve `signal_name` / `signal_value` metadata.
- Parse optional direct-observation `Clock ID` / `Timebase`, `Coverage Complete`, and numeric timestamps into deterministic evidence metadata.
- Preserve evidence-backed APPLICABLE and NOT APPLICABLE decisions when the LLM supplies explicit valid current-case evidence bindings; unresolved/unbound decisions are downgraded to UNKNOWN.
- Normalize NOT APPLICABLE evaluation sufficiency to `NOT_REQUIRED` and remove irrelevant response evidence/needs.
- Split Section-7 applicability evidence from evaluation evidence.
- Fix minimum-evidence closure so resolved SATISFIED / VIOLATED / NOT APPLICABLE requirements do not request further compliance evidence.
- Add TEST-002 and v0.4.0 regressions for atomic evidence provenance and the expected `VIOLATED / SATISFIED / NOT APPLICABLE` path.

## v0.4.0 → v0.4.1

Changes introduced in **v0.4.1** relative to **v0.4.0**:

- Fix startup failure on Python 3.9 caused by Python 3.10-only PEP 604 type annotations such as `float | None`.
- Replace all runtime-evaluated `X | None` annotations with `typing.Optional[X]`.
- Restore documented minimum runtime to Python 3.9+.
- No semantic-analysis, validator, evidence-binding, or report-generation behavior changed from v0.4.0.

## v0.4.1 → v0.4.2

Changes introduced in **v0.4.2** relative to **v0.4.1**:

- Add deterministic observation semantics: `STATE_SAMPLE`, `TRANSITION`, `INTERVAL_STATE`, and `UNSPECIFIED`.
- Parse explicit transition forms such as `10.100 s FunctionRequest transitioned to ACTIVE` / `Signal became Value` while retaining `Signal = Value` as a state sample.
- Require explicit transition evidence for transition-trigger applicability (`when X becomes Y`); state samples no longer prove that event occurred.
- Add deterministic `TimingFact` with trigger/response IDs, timestamps, elapsed ms, limit ms, margin, clock, coverage, and within/exceeds outcome.
- Compute timed verdict sufficiency mechanically from explicit transition timestamps once the LLM has decomposed the requirement.
- Require complete event coverage for late-response violations so an earlier unobserved response transition cannot be excluded.
- Prevent qualitative reported wording such as `later than expected` from bridging ambiguous quantitative timing evidence.
- Enforce `SUFFICIENT_*` versus `missing_evaluation_evidence` consistency and clear timing needs after a deterministic timing fact resolves the requirement.
- Fix Section-10 planning for resolved timed requirements.
- Add TEST-003 GUI loader and regressions for a 550 ms violation, a 450 ms satisfied response, and state-sample ambiguity suppression.

## v0.4.2 → v0.4.3

Changes introduced in **v0.4.3** relative to **v0.4.2**:

- Separate generic `coverage_complete` from explicit `event_coverage_complete`; legacy `Coverage Complete: true` no longer implies complete transition capture.
- Add explicit `Event Coverage Complete: true` trace metadata and require it for deterministic late-response timing violations.
- Formalize evidence scope: `STATE_SAMPLE` proves only an instant, `TRANSITION` proves a change event, and `INTERVAL_STATE` proves persistence across an interval.
- Downgrade condition-only `NOT APPLICABLE` decisions to `APPLICABILITY UNKNOWN` when they are supported only by point state samples; interval-state or authoritative scope evidence is required for case-wide non-applicability.
- Require explicit `INTERVAL_STATE` evaluation evidence for persistence `SATISFIED` / `VIOLATED` verdicts; generic/event coverage metadata cannot substitute.
- Add deterministic normalization for persistence sufficiency and resolved persistence evidence needs.
- Update TEST-003 to use explicit event coverage and interval-state AvailabilityStatus evidence.
- Add regression tests for legacy generic-coverage rejection, point-sample NOT-APPLICABLE suppression, and persistence interval-state enforcement.

## v0.4.3 → v0.5.0

Changes introduced in **v0.5.0** relative to **v0.4.3**:

- Freeze v0.4.3 as the validated TEST-003 timing/evidence baseline.
- Introduce tiered repair routing: deterministic Python -> fast repair model -> primary-model repair/fallback.
- Add configurable fast repair model settings to GUI and CLI.
- Add persisted repair-routing audit events separate from LLM attempt logs.
- Add `Snapshot ID` / `Observation Group` parsing and point-observation correlation checks.
- Prevent sufficient point-state verdicts when applicability and response samples are not explicitly correlated.
- Add asymmetric applicability-scope semantics: positive occurrence can be established at a point; case-wide absence requires interval/scope evidence.
- Normalize over-strict positive applicability evidence requests that incorrectly demand `INTERVAL_STATE`.
- Preserve interval/correlation specificity in Section 10 minimum-next-evidence output.
- Update TEST-002 example with an explicit verification snapshot.
- Add v0.5.0 regression tests for correlation, applicability asymmetry, deterministic repair, routing, fast-model repair, and evidence-plan specificity.

## v0.5.0 → v0.5.1

Changes introduced in **v0.5.1** relative to **v0.5.0**:

- Integrate the validated Fast Repair Harness v1.8 architecture into the main RCA Analyst POC.
- Replace whole-RequirementAnalysis fast repairs with field-level `RequirementPatchResponse` updates and deterministic writable-field allowlists.
- Route `APPLICABILITY_NEED_IN_EVALUATION_BUCKET`, `NONEXISTENT_TRIGGER_IN_EVALUATION_BUCKET`, converse/permissive wording, invented-process wording, relevance wording, rule-ID leakage, and narrow evidence mapping to the fast model.
- Keep mechanically provable fixes in Python and core decomposition defects with the primary model.
- Add `EVALUATION_NEED_TARGET_MISMATCH` validation so evaluation evidence cannot re-request already-established applicability/trigger coverage instead of the required response.
- Revalidate after every repair action and allow newly exposed defects to be routed sequentially within the same repair round.
- Add primary batching when only core semantic defects remain, avoiding unnecessary multiple 27B calls.
- Add Qwen3.5 non-thinking manual `/v1/completions` transport; `auto` selects it for Qwen3.5 with Thinking OFF.
- Update validated fast-model defaults to Qwen3.5-4B, temperature 0.0, Thinking OFF, Auto transport, 1400 max tokens.
- Add v0.5.1 repair-integration regressions including semantic-target rejection, allowlisted patch enforcement, and second-pass fast repair.
- Test suite: 58 passed.

## v0.5.1 → v0.5.2

Changes introduced in **v0.5.2** relative to **v0.5.1**:

- Add deterministic `STATE_CONFORMANCE_COVERAGE_INSUFFICIENT` normalization: interval-scoped applicability plus only point-level matching response evidence can no longer yield `SUFFICIENT_CONFORMANCE` / `SATISFIED`.
- Preserve the asymmetric counterexample rule: a correlated contradictory point sample may still establish `SUFFICIENT_NONCONFORMANCE` / `VIOLATED`.
- Derive a targeted `OBSERVATION_INTERVAL` evidence need for the required response/state when conformance coverage is incomplete.
- Add TC2 regression coverage for REQ-101 = VIOLATED, REQ-102 = NOT EVALUABLE, REQ-103 = NOT APPLICABLE while preserving TC1/TC3 semantics.
- Add a GUI button to run TEST-001, TEST-002, and TEST-003 strictly sequentially with a fresh pipeline per case.
- Auto-save all batch reports/sessions and create JSON/Markdown batch summaries under `batch_results/<timestamp>/`.
- Add persisted Dark/Light theme selection.
- Improve Section 11 confirmed-finding readability with bullet formatting.
- Automated test suite: 63 passed.

## v0.5.2 → v0.5.2.1

Changes introduced in **v0.5.2.1** relative to **v0.5.2**:

- Preserve v0.5.2 analysis/validator/repair behavior unchanged.
- Add **Run Test Bundle…** to select a ZIP containing an arbitrary number of `.txt` test cases.
- Discover `.txt` cases recursively, natural-sort them, read `Ticket ID:` when present, and reject duplicate IDs.
- Execute every loaded case strictly sequentially with a fresh `RCAPipeline`/LLM context per case; no parallel model calls are introduced.
- Continue the bundle after an individual case validation failure and save both successful and failed sessions.
- Generalize the v0.5.2 three-case batch UI/results tab to **Sequential Batch**.
- Auto-save versioned per-case reports/sessions plus JSON/Markdown bundle summaries under `batch_results/<timestamp>_<bundle-name>/`.
- Keep the built-in TEST-001 → TEST-003 regression button, now routed through the same generic batch engine.
- Add pure-Python ZIP bundle loader tests.
- Automated test suite: 82 passed.

## v0.5.2.1 → v0.5.3

Changes introduced in **v0.5.3** relative to **v0.5.2.1**:

- Preserve the v0.5.2 semantic baseline and v1.8 tiered repair architecture.
- Accept assignment-only current-trace rows and infer internal transition metadata only from an actual timestamped value change for the same signal/clock; raw evidence text remains `Signal = Value`.
- Fix prohibitive/persistence point-counterexample handling so a witnessed forbidden state can prove nonconformance without interval-wide response evidence.
- Promote safely observed simple positive IF-conditions from APPLICABILITY UNKNOWN to APPLICABLE while retaining interval evidence requirements for persistence conformance.
- Add deterministic source-accounting validation for supplied historical tickets and explicit relationship context; auto-account supplied diagnostic IDs.
- Add explicit deterministic timing conflict reporting when reported results disagree with complete direct timing evidence.
- Tighten exact signal matching/evidence-bucket cleanup for dotted variant namespaces.
- Add non-causal before/after BZD temporal classification.
- Add one bounded structured-output retry for empty/malformed primary output and malformed Qwen3.5 repair JSON.
- Persist forensic details for failed LLM calls: canonical case, reasoning/raw response, finish reason, transport, retry diagnostics, and usage.
- Add v0.5.3 regression tests for the overnight defects and assignment-only trace behavior.

## v0.5.3 → v0.5.4

Changes introduced in **v0.5.4** relative to **v0.5.3**:

### Result-driven finalization after the first real-model v0.5.3 batch

- Separate batch `EXECUTION_STATUS` from `SEMANTIC_ACCEPTANCE`, loading the regression ZIP expected-results manifest and persisting machine-readable expected-vs-actual checks.
- Correct transition-trigger `NOT APPLICABLE` overreach: a target-state sample, even with complete event capture inside the supplied trace, cannot prove a `becomes` trigger never occurred before trace start.
- Derive conformance for non-persistent point-state obligations when positive applicability and required-state observations are correlated by snapshot or aligned timestamp; persistence obligations still require interval proof.
- Normalize late-response/incomplete-event-coverage cases to request only complete response-event coverage when trigger/response timestamps and timebase are already known, preventing unnecessary fast-model repair.
- Route mechanically visible persistence decomposition (`remain` / `shall not` / `must not` / `never`) to deterministic repair instead of a full primary-model repair.
- Persist every bounded structured-output transport attempt, including raw API payload, final content, reasoning content, finish reason, per-attempt usage/timing, parse error, and retry reason.
- Constrain Qwen3.5 malformed-JSON recovery to one bounded retry plus terminal-delimiter completion only; no broad heuristic semantic repair.
- Reduce primary structured-output recovery expansion to modest output headroom with lower retry reasoning effort.
- Preserve explicit inherited parent scope for child requirements while applying the new trigger-applicability guard.
- Automated local suite: **94 passed**.

## v0.5.4 → v0.5.5

Changes introduced in **v0.5.5** relative to **v0.5.4**:

- Fixed false timebase requests in Section 10 when trigger and response are already on the same clock/source.
- Added actual evidence-clock inspection before adding a clock-alignment acquisition need.
- Added the Live Pipeline GUI inspector with stage-by-stage status, user-friendly summaries, and exact input/output views.
- Added live trace callbacks to single-case and sequential-batch pipeline execution, including repair stages and failures.
- Added regressions for same-clock suppression, true multi-clock alignment requests, and complete live stage tracing.

## v0.5.5 → v0.6.0

Changes introduced in **v0.6.0** relative to **v0.5.5**:

- Introduce a multi-model RCA pipeline while preserving the frozen evidence semantics and Python final authority.
- Add conditional Qwen3.5-4B intake normalization for inconsistent human testcase formats; clean formal inputs bypass it in `auto` mode.
- Add source-span enforcement and Python canonicalization so the 4B intake model cannot invent evidence IDs, transitions, timestamps, clocks, event coverage, or verdicts.
- Reuse the same Qwen3.5-4B model for three isolated services with separate budgets: intake normalization, field-level repair, and final linguistic consistency review.
- Add a compact post-validation 4B review that may patch `relevance` wording only; every patch is deterministically revalidated and Python remains the final gate.
- Refine TC5-style timing output so known same-clock trigger/response timestamps are acknowledged and only missing transition-event coverage is requested.
- Expand Live Pipeline stages to show input classification, optional 4B intake, Python canonicalization, 27B semantic reasoning, repairs, 4B review, Python final gate, formatting, and final output.
- Add v0.6.0 regression guards proving unsupported 4B intake spans are rejected and unsafe final-review wording cannot override deterministic truth.
- Automated local suite: **104 passed**.

## v0.6.0 → v0.6.1

Changes introduced in **v0.6.1** relative to **v0.6.0**:

- Add a GUI **Stop** control for both single-case analysis and sequential batches.
- Add a shared thread-safe cancellation token across GUI workers, `RCAPipeline`, and all LM Studio clients.
- Use cancellable OpenAI-compatible SSE streaming for GUI model calls and close the active response when Stop is requested.
- Reject interrupted/partial structured output instead of treating it as malformed output eligible for repair/retry.
- Stop batch execution after the active case, preserving completed cases and preventing queued cases from starting.
- Mark interrupted Live Pipeline stages as `CANCELLED`.
- Add cancellation regression tests; full suite now passes 109 tests.

## v0.6.1 → v0.6.2

Changes introduced in **v0.6.2** relative to **v0.6.1**:

- Fix forced 4B intake failure exposed by TC5 when Qwen3.5 returned YAML-like section output instead of the requested JSON object.
- Embed the exact response-model JSON Schema into manual Qwen3.5 `/v1/completions` prompts.
- Reject YAML/prose wrappers and arbitrary embedded JSON fragments; structured output must be one top-level JSON object.
- Preserve the existing one bounded 4B structured retry for malformed output, now with generic schema-specific JSON-only guidance.
- Prevent a structurally valid but empty 4B intake object from erasing deterministic requirements when `Intake Routing = Always`; retain the deterministic parse and mark intake as attention.
- Add v0.6.2 regressions for the exact TC5 intake failure and forced-intake fallback.
- Automated local suite: **111 passed**.

## v0.6.2 → v0.6.3

Changes introduced in **v0.6.3** relative to **v0.6.2**:

- Give Qwen3.5 intake explicit semantic source-availability states: `PRESENT`, `ABSENT`, `UNKNOWN`, `NOT_MENTIONED`.
- Add structured requirement/historical/diagnostics/trace availability sections and separate `user_instructions` from evidence/unclassified text.
- Teach the 4B intake prompt multilingual/paraphrased absence and presence distinctions, including `not available` / `nicht verfügbar` versus `no DTCs present` / `Keine Fehler im Fehlerspeicher`.
- Keep natural-language absence understanding in the 4B intake model; Python canonicalization only enforces normalized invariants such as non-PRESENT sources containing no evidence blocks. The legacy template-only deterministic path remains available when intake is bypassed/off.
- Preserve source-availability metadata and its verbatim source statement in the canonical case without promoting it to engineering evidence.
- Clarify final-review policy that relevance and sufficiency are independent, preventing TC5-style false contradiction findings.
- Explicitly decode cancellable SSE streams as UTF-8 to prevent mojibake in arrows, punctuation, and German characters.
- Keep 4B Thinking OFF by default pending benchmark evidence that it improves intake classification enough to justify additional latency.
- Automated local suite: **119 passed**.

## v0.6.3 → v0.6.4

Changes introduced in **v0.6.4** relative to **v0.6.3**:

- Replace the broad final 4B contradiction judgment with a structured per-requirement review contract that separately extracts evidence relevance, evidence sufficiency, and any implied evaluation status from the current relevance wording.
- Add deterministic comparison of those extracted language claims against the authoritative validated structure before any relevance rewrite can be accepted.
- Treat `RELEVANT + INSUFFICIENT + NOT_EVALUABLE` as an explicit valid combination so TC5-style relevant-but-insufficient evidence cannot be flagged as a contradiction merely because the requirement remains unevaluable.
- Keep Python as the final gate while preserving the 4B role as the natural-language interpreter: the model reads what the sentence claims; Python checks those structured claims against authoritative facts.
- Give the final 4B reviewer its own model settings, independent from intake/repair: default reasoning `Low`, thinking `provider/default`, and OpenAI-chat transport. Intake and field repair remain non-thinking by default.
- Expose separate final-review reasoning, thinking, and transport controls in the GUI and persist them in application configuration.
- Add cumulative `VERSION_HISTORY.md`, ordered chronologically and describing every tracked transition from one RCA Analyst POC version to the next.
- Add v0.6.4 regressions for TC5 relevance/sufficiency separation, unsafe structured reviewer claims, final-review client defaults, and version-history completeness.
- Automated local suite: **125 passed**.

## v0.6.4 → v0.6.5

Changes introduced in **v0.6.5** relative to **v0.6.4**:

- Keep the structured final-review contract introduced in v0.6.4, but revert the Qwen3.5 reviewer execution defaults to Thinking OFF / Auto transport after the real TC5 run showed Low-thinking chat consumed its entire output budget in reasoning and returned no usable JSON.
- Add a bounded non-thinking manual recovery path when a user explicitly enables chat/thinking and the final-review structured output is exhausted or empty.
- Add a deterministic hypothesis safety rule for unresolved timing requirements: the same incomplete trigger/response evidence that leaves a requirement `NOT EVALUABLE` cannot independently support a hypothesis that effectively asserts the unresolved timing proposition.
- Preserve legitimate candidate mechanisms when independent diagnostic, historical, or otherwise separate evidence is supplied.
- Synchronize the filtered hypothesis list back into the authoritative semantic object/session export.
- Fix duplicate terminal punctuation in the final supported-hypotheses summary.
- Add v0.6.5 regression coverage for the TC5 hypothesis regression, reviewer fallback, current reviewer defaults, punctuation, and history continuity.
- Automated local suite: **132 passed**.

## v0.6.5 → v0.7.0

Changes introduced in **v0.7.0** relative to **v0.6.5**:

- Promote the architecture change to a minor release and split language/reasoning responsibilities instead of expanding Python natural-language heuristics.
- Split Qwen3.5-4B preprocessing into source availability, content classification, atomic-claim extraction, and requirement-language normalization. Availability language remains LLM-owned; Python enforces only the resulting structured contract and provenance.
- Split Qwen3.8-27B deep analysis into **Phase A requirement reasoning** and **Phase B RCA synthesis**, separated by an authoritative Python compliance checkpoint. Phase B receives requirement results as immutable facts and cannot modify requirement truth.
- Retain existing primary semantic repair as conditional 27B arbitration for genuine requirement-semantics defects after deterministic/fast repair routing.
- Add relationship-preserving Phase-A chunking for large cases. Default large-case threshold is 8 requirements, nominal chunk size is 6, and explicitly connected requirements stay together.
- Add a 16,000-token Phase-A completion budget for large cases such as TC12/TC21 while normal cases retain their existing primary output budget. `finish_reason=length` is explicitly classified as output-token exhaustion for bounded recovery.
- Add a 4B hypothesis epistemic-review stage that classifies mechanism candidates, compliance restatements, root-cause claims and evidence summaries, then proposes allowlisted KEEP/REWRITE/DROP actions subject to Python revalidation.
- Add structured requirement predicates as non-authoritative 4B language hints. Python can execute those predicates against canonical correlated observations, fixing TC4-style response evidence mapped from a point where applicability is explicitly false without parsing natural-language requirement text itself.
- Add source-backed atomic claims and proposition-level reported/direct timing conflict comparison, addressing TC8-style compound sentences.
- Harden cooperative cancellation so transport/read exceptions caused by closing an active stream are translated to cancellation when the cancellation token is set.
- Expand the Live Pipeline to 18 explicit architectural stages plus dynamic Phase-A chunk/repair child stages.
- Extend session exports with optional decomposed-stage objects while retaining v0.6.x-compatible fields.
- Add explicit GUI/config controls for large-case tokens/chunking and each new fast-language stage.
- Establish a release-document policy: every release from v0.7.0 onward includes `docs/V<version>_RELEASE_NOTES.md` in addition to this cumulative history and `CHANGELOG.md`.
- Add v0.7.0 regressions covering availability structure, TC4 context mapping, TC8 atomic claims, chunk integrity, Phase-B immutability, hypothesis epistemic review, large-case 16k routing, Live Pipeline visibility and release-document continuity.
- Automated local suite: **142 passed**.



## v0.7.0 → v0.7.1

Changes introduced in **v0.7.1** relative to **v0.7.0**:

- Keep the v0.7.0 decomposed 4B/27B architecture intact and correct interface-contract defects exposed by the first live TC12 run.
- Preserve LLM ownership of source-availability meaning. The TC12 4B correctly returned requirements/trace PRESENT and historical/diagnostics ABSENT, but its compact string `availability_statement` fields were rejected by the Pydantic envelope. v0.7.1 structurally normalizes that compact representation rather than replacing language understanding with Python sentinel matching.
- Preserve LLM ownership of atomic claim decomposition. A valid bare JSON claim array can now be safely wrapped only for response schemas containing exactly one array property, while the prompt requests an explicit object envelope by default.
- Tighten the 4B requirement-language contract so applicability DNF contains only preconditions, WHEN/UPON event triggers are separate, `becomes` produces `trigger_event=BECOMES`, required behavior is not mixed into applicability, and positive persistence states are represented with positive equality.
- Use the already-normalized requirement-language object as a non-authoritative structured bridge into Phase A: missing trigger/timing/persistence decomposition is projected mechanically before validation. Python does not parse the raw requirement sentence to create those semantics.
- Canonicalize numeric timing hints into machine-readable `within N ms` form so deterministic timing can evaluate cases such as TC12 REQ-1204.
- Improve missing-evidence semantic-target validation when the required response signal has no current observation, using the normalized 4B signal contract to avoid false `EVALUATION_NEED_TARGET_MISMATCH` errors.
- Mechanically remove/move APPLICABILITY-labelled needs from the evaluation bucket and defer trigger-timestamp needs until the trigger itself has been decomposed.
- Fix requirement-repair control flow: a deterministic repair that cannot mechanically change its target now marks that task for primary semantic arbitration and continues, instead of terminating the whole repair loop with unrelated critical defects still pending.
- Retain the 16,000-token large-case Phase-A budget. For the failed live TC12 v0.7.0 run, both Phase-A chunks returned `finish_reason=stop` well below the budget, proving the failure was decomposition/integration rather than output exhaustion.
- Add targeted v0.7.1 regressions for compact source availability, atomic-array envelopes, applicability/behavior separation, trigger/timing projection, persistence projection, evaluation-bucket structure, absent response-signal targeting, and repair dependency ordering.
- Automated local suite: **151 passed**.