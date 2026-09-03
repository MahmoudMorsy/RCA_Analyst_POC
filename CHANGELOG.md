# Changelog

## 1.8.11

- Promote application to **v1.8.11** with embedded **RCA Core v0.8.10 candidate** after the exact v1.8.10 27B RunPod suite completed 17/17 executions and achieved 11/17 semantic acceptance.
- Require structurally complete `resolution=VERIFIED` independent-verifier fingerprints; incomplete behavior/trigger/timing/relationship identity now enters structured-output recovery rather than becoming a false semantic mismatch.
- Introduce canonical Requirement persistence-scope categories and reject evidence-domain values such as `INTERVAL_STATE`.
- Allow redundant unchanged untargeted arbitration fields while continuing to reject changed untargeted fields and merge only Python-approved targets.
- Automatically couple newly-created executable semantic elements to `source_clauses` repair when the corresponding provenance role is absent.
- Add referenced canonical structural direct observations to the RCA Evidence Packet even when no language annotation was needed.
- Persist exact arbitration contract-rejection reasons in attempt diagnostics/validation issues.
- Add v1.8.11 regressions for TEST-007/015/016/018/019/021 failure classes.
- TC12 and TC17 are live-confirmed 27B anchors from the v1.8.10 suite; v0.8.10 remains candidate pending exact-package v1.8.11 full-suite acceptance.

## 1.8.10

- Promote application to **v1.8.10** with embedded **RCA Core v0.8.9 candidate**.
- Isolate generic testcase exceptions and pipeline-construction failures so sequential regression/bundle execution continues.
- Preserve generic testcase exception type/message/traceback/partial pipeline and keep partial result plus run-level failure metadata in session exports.
- Reject invalid semantic-arbitration responses atomically and continue conservatively rather than crashing the RCA pipeline.
- Allow an omitted arbitration target field only when all material issue IDs governing that field are explicitly unresolved.
- Persist rejected arbitration responses through pipeline attempts/trace output.
- Remove descriptive `process_description` from semantic-verifier equality and normalize structured persistence-scope categories.
- Surface testcase exception/traceback details in the Web result views.
- Add v1.8.10 regressions; release suite is **232 tests**.

## 1.8.9

- Promote application to **v1.8.9** with embedded **RCA Core v0.8.8 candidate**.
- Fix VERIFIED fact reuse across structurally matching requirements; `related_requirement_ids` is linkage metadata rather than an execution whitelist.
- Require all targeted fields from structural completion patches.
- Make semantic arbitration field-atomic and non-regressive, with backward-compatible target-only merging from legacy full IRs.
- Make free-form case ambiguity advisory unless a structured material issue exists.
- Route diagnostic/historical RCA packet facts by canonical source class.
- Preserve materially unresolved requirements as explicit RCA context.
- Separate strict hypothesis machine IDs from human-readable source-reference labels.
- Rediscover active backend runs after Web reconnect and expose multiple active runs through a selector.
- Preserve expanded pipeline Input/Output objects and run/testcase/stage UI selection during live polling.
- Add v1.8.9 regressions; release suite is **225 tests**.

## 1.8.8

- Promote application to **v1.8.8** with embedded **RCA Core v0.8.7 candidate** after the complete 17-case RunPod suite exposed systemic semantic-contract defects beyond TC17.
- Validate every Requirement Compilation batch against its authoritative expected IDs and perform one bounded semantic recovery call for missing IDs only; preserve source order and never create missing semantics in Python.
- Make complete `source_clauses` provenance inventories first-class targeted structural-completion fields and allow at most two compact completion passes when provenance repair reveals another missing top-level semantic object.
- Strengthen Requirement IR structural integrity for condition/trigger/behavior/timing/persistence semantic-ID and source-clause linkage.
- Strengthen compiler/verifier contracts for executable behavior/trigger/timing/persistence and independent normative-polarity reconstruction, including prohibitive obligations.
- Make exact-source grounding tolerant of bullet/line-break/punctuation layout and explicit source-order ellipsis while continuing to reject invented source text.
- Remove same-signal/loose narrative linkage as a sufficient compliance-materiality path; require authoritative structured evidence dependencies.
- Compact semantic arbitration to the exact authoritative requirements/evidence implicated by material issues, reducing prompt growth without weakening the strict replacement validator.
- Accept VERIFIED semantic evidence fact IDs as RCA hypothesis provenance while rejecting unknown or unresolved fact IDs.
- Make semantic acceptance fail whenever final semantic-integrity ERRORs remain, preventing an expected conservative verdict from passing through a broken semantic path.
- Add authoritative testcase lifecycle persistence: single and batch cases appear as `RUNNING` before completion and update in place to terminal status.
- Make the Web **Tests** selector universal for single/batch runs and keep the current running testcase selectable after browsing completed results.
- Add v1.8.8 regressions for source grounding, narrative materiality, complete provenance repair, missing-ID recovery, normative-polarity/provenance prompt contracts, RCA fact-ID provenance, internal-error acceptance gating and live testcase lifecycle.
- Release validation: **216 passed** in the working tree and **216 passed** from a clean fresh extraction.

## 1.8.7

- Promote application to **v1.8.7** with embedded **RCA Core v0.8.6 candidate**; v0.8.6 remains unfrozen pending live TC17 then TC12 acceptance.
- Propagate explicit Qwen/llama.cpp thinking mode through `chat_template_kwargs.enable_thinking` for OpenAI-compatible requests, with one bounded compatibility fallback when a provider rejects that optional field.
- Add reasoning-content observability (`reasoning_content_present`, character counts and requested thinking mode) without fabricating reasoning-token counts.
- Replace full Requirement IR structural regeneration with targeted `RequirementStructuralPatchBatch` repair; Python permits only explicitly requested fields to change.
- Bound targeted Requirement/evidence completion outputs so a small structural defect cannot consume the full semantic-preparation budget repeatedly.
- Tighten Requirement IR executability for signal/value required behavior, grounded negative predicates, literal comparison values and explicit persistence.
- Route all non-executable `PERSISTENT_STATE` scope shapes to semantic completion; whole evaluated-interval persistence is executable only with explicit resolved `CASE_EVALUATED_INTERVAL` grounding.
- Correct unresolved-evidence materiality so narrative/title/reporting ambiguity is not blocking merely because it references a requirement, while structured facts used by Requirement IR remain material when semantics/scope are unresolved.
- Tighten arbitration provenance: executable repaired nodes must themselves carry matching semantic IDs and grounded source phrases; notes or separately named clauses cannot substitute.
- Preserve v0.8.5 independent semantic fingerprint verification, strict Python compliance authority, frozen evidence semantics and v1.8.6 Web/configuration improvements.
- Add regressions derived from the live v1.8.6 TC17 compiler/evidence outputs and provider reasoning behavior.
- Release validation: **207 passed** in the working tree and **207 passed** from a clean fresh extraction.

## 1.8.6

- Promote application to **v1.8.6** with embedded **RCA Core v0.8.5 candidate**; v0.8.5 remains unfrozen pending live TC17/TC12 acceptance.
- Preserve completed pipeline Stage Input/Output by merging repeated stage events instead of replacing prior state.
- Persist structured stage input/output and render nested human-readable stage data with Raw JSON available for forensic inspection.
- Restore full per-testcase result parity for sequential batches: Final Report, Validation, Canonical Input, Structured JSON, LLM Attempts, Repair Routing, pipeline/logs and statistics.
- Publish batch results incrementally after each successful or failed testcase rather than only at batch completion.
- Add per-testcase and per-stage statistics, including failed model calls, token/latency/retry/throughput data, role/model/endpoint breakdown and requirement-result counts.
- Add endpoint-current model discovery/test (`POST /api/v1/models/discover`) so model selection no longer requires saving stale backend configuration first.
- Expose active `RCA_*` deployment environment overrides instead of silently making saved model configuration appear to revert.
- Add immutable per-run `config_override` snapshots from the current Web form.
- Clarify that external llama.cpp/LM Studio/vLLM context/offload settings are server-managed unless a provider adapter explicitly owns process lifecycle.
- Add Critical Semantic Model Routing so semantic preparation and independent verification can each use the configured Small / Utility or Primary model without changing RCA authority.
- Harden the independent verifier with a source-derived structured semantic fingerprint; Python detects TC17-style Boolean regrouping even if the verifier label says `VERIFIED`.
- Reject arbitration evidence pseudo-repairs that explain correct meaning only in notes while leaving compliance-linked facts non-executable (`OTHER`/missing subject/value/scope).
- Tighten evidence annotation prompts to the legal schema enum; Python does not translate invented operators such as `HAS`, `REACHES`, `WAS`, or `CONTAINS`.
- Preserve Python 3.9 backend compatibility, frozen evidence semantics, deterministic compliance authority and desktop fallback.
- Add v1.8.6 live-failure-shape/application regressions and release documentation.
- Release validation: **201 passed** in the working tree and **201 passed** from a clean fresh extraction.

## 1.8.5

- Fixed FastAPI/Pydantic startup failure on Python 3.9 caused by runtime evaluation of PEP 604 annotations such as `str | None` in the new `rca_server` layer.
- Replaced server-layer optional unions with `typing.Optional[...]`; no RCA semantic code changed.
- Expanded Python 3.9 compatibility regression coverage from `rca_app` to both `rca_app` and `rca_server`.
- Added backend import/startup regression coverage for the Web application.

## 1.8.4

- Major application architecture/deployment refactor from monolithic PySide desktop execution to Web UI + fixed FastAPI backend while preserving RCA Core v0.8.4 semantics.
- Add stable `/api/v1` health/system/capabilities/models/config/files/runs/sessions APIs.
- Add asynchronous backend-owned run jobs with explicit states, persistent run journals, browser disconnect/reconnect recovery and remote cancellation.
- Preserve dynamic Live Pipeline events, stage input/output, logs, results, validation, canonical input, structured JSON, attempts, repair routing and statistics through backend APIs.
- Add provider-neutral `ModelClient`/`ModelGateway`; `RCAPipeline` no longer imports LM Studio directly.
- Separate RCA configuration, model endpoint/provider configuration, inference-engine configuration and infrastructure telemetry.
- Add Local Dell, RunPod, Home AI Server and Custom browser backend profiles plus deployment YAMLs for the three backend targets.
- Add backend-managed storage, file uploads/downloads, run history/benchmarking metrics, reports and session envelope schema v2.
- Add deterministic legacy desktop-session migration that retains the complete original payload.
- Add best-effort CPU/RAM/GPU/VRAM/utilization/temperature/power/disk telemetry without making telemetry correctness-critical.
- Add bearer authentication, explicit CORS and remote deployment guidance.
- Add Dockerfile/docker-compose and complete Dell/RunPod/home deployment guides.
- Preserve the desktop application as a frozen fallback/reference via `run_desktop.py` / `run_desktop.bat`.
- Add mandatory Desktop UI → Web UI/API migration matrix and application-architecture documentation.
- Original RCA regression suite remains green; expanded v1.8.4 suite: **191 passed**.

## 0.8.4

- Always split Requirement IR compilation from evidence semantic annotation, including small cases.
- Add specialized 4B requirement/evidence semantic prompts.
- Canonicalize the TC17-style malformed evidence annotation envelope without interpreting prose.
- Never assign annotation-level scope IDs to facts in Python.
- Add targeted 4B Evidence Semantic Completion for structured evidence defects only.
- Require non-empty resolved scope IDs before language-derived persistent facts can execute as interval evidence.
- Extend strict 27B arbitration replacement checks to evidence repairs.
- Add v0.8.4 regression coverage for TC17 evidence-envelope/scope failures and split-call topology.
- Automated local suite: **175 passed**.

## 0.8.3

- Fix live TC12 v0.8.2 RequirementCompilationBatch abort caused by semantically useful PREDICATE nodes omitting the `signal` field while still providing grounded `source_phrase`, operator and value.
- Separate transport-valid Requirement IR from executable Requirement IR: partial compiler AST objects are preserved for verification/repair instead of aborting the entire batch at Pydantic transport validation.
- Add Python structural IR checks for missing predicate signal/operator, malformed Boolean node shape, incomplete trigger/required-behavior/timing objects, all treated as material and non-executable.
- Add one bounded targeted 4B structural-completion recompilation for affected requirements before the independent semantic verifier and before any 27B arbitration. Python does not infer the missing semantic field from prose.
- Strengthen the compiler prompt so every PREDICATE explicitly returns `signal`, `operator`, and `value`.
- Keep the v0.8.2 27B arbitration replacement contract strict: arbitration repairs still reject missing predicate signals/operators or malformed Boolean structure.
- Preserve the live-verified TC12 decimal timestamp correction and deterministic transition metadata.
- Add regressions for transport-partial predicates, structural materiality, strict arbitration rejection, and cheap 4B structural completion avoiding unnecessary 27B escalation.
- Automated working-tree suite: **168 passed** before final release gating.

## 0.8.2

- Fix live TC17 v0.8.0 semantic-arbitration failure where both 4B and 27B correctly described requirement meaning in prose/source clauses but returned non-executable IR fields (`condition=null`, `required_behavior=null`).
- Strengthen the fast semantic compiler contract: mixed language and nested Boolean logic are not ambiguity by themselves; if semantics are understood in notes they must be encoded into the actual IR fields.
- Make 27B arbitration repairs strict replacement objects: returned repair IRs may not remain `AMBIGUOUS`, may not contain non-VERIFIED material source clauses, and must represent every material source-clause semantic ID in executable IR fields. Genuine ambiguity must stay in `unresolved_issue_ids` instead of being returned as a pseudo-repair.
- Add explicit `MECHANISM` evidence role. `RCA_CONTEXT` is now non-routing, and semantic `DIAGNOSTIC`/`HISTORICAL` roles are cross-checked against the authoritative source class before they can trigger deep RCA.
- Prevent a point-state observation of a requirement output signal from being treated as mechanism evidence merely because the model tags it as such.
- Harden RCA Evidence Packet construction so ordinary direct observations mislabelled as diagnostic/history do not appear in diagnostic/historical packet sections.
- Add live-TC17 regressions for prose-only pseudo-repair rejection and for preventing the unnecessary second 27B RCA call.
- Automated working-tree suite: **165 passed** before final release gating.

## 0.8.1

- Fix first-live-run TC12 v0.8.0 semantic-preparation failure without changing the v0.8 ownership architecture.
- Add bounded 4B Requirement IR compilation batches plus one narrow evidence-language annotation batch for cases that do not fit a single small-model structured response.
- Keep small cases on one compact case-level semantic-preparation call.
- Normalize JSON `null` to existing empty-string sentinels only for optional semantic string fields; semantic omissions remain subject to integrity checks.
- Add one compact independent 4B requirement-vs-IR semantic verification pass so a compiler cannot silently omit a source condition from both its IR and its own self-audit.
- Route all verifier mismatches into the existing single case-level 27B semantic arbitration call; re-verify repaired IR once without allowing a second 27B semantic retry.
- Compact semantic-preparation payloads to reduce local Qwen3.5 context pressure.
- Preserve the v0.8.0 decimal timestamp correction verified by the live TC12 failure session.
- Add v0.8.1 null-contract, TC12 batching, prompt-size and silent-condition-omission regressions.
- Automated working-tree suite: **163 passed** before final release gating.

## 0.8.0

- Introduce the adaptive semantic-compiler architecture: one normal 4B case-level semantic preparation, deterministic Python compliance, conditional one-call 27B semantic arbitration, and conditional 27B RCA synthesis.
- Add declarative Requirement IR with recursive Boolean AST, trigger, required behavior, timing, persistence, relationships, source-clause provenance, and unresolved semantic state.
- Add context-safe evidence semantic annotations; unresolved natural-language interval scope is no longer promoted to executable interval evidence.
- Add semantic integrity/materiality validation and compiler self-audit checks for missing semantic IDs/source clauses.
- Add Python deterministic compliance engine and make model-produced compliance labels non-authoritative.
- Add RCA routing and compact verified RCA Evidence Packet; original natural-language requirements are not resent to the RCA model by default.
- Remove mandatory v0.7 27B Phase A/Phase B and requirement-count-driven primary-model chunking from the production path.
- Fix decimal timestamp/list-marker corruption (`99.900`, `100.000`).
- Add exact TC12/TC17 regressions and adaptive call-routing tests.
- Update GUI/CLI for v0.8 topology and retain a compatibility-only v0.7.1 branch for old adapters/tests.
- Automated working-tree suite: **160 passed**.

## 0.7.1

- Correct v0.7.0 live TC12 integration defects without changing the decomposed architecture topology.
- Normalize compact 4B source-availability statement strings into the structured `IntakeField` envelope after the model correctly classifies source presence/absence.
- Safely accept bare top-level arrays for single-array structured schemas and strengthen Atomic Claims to request the normal object envelope.
- Tighten requirement-language normalization: applicability contains only preconditions; event triggers stay separate; `becomes` is represented as `BECOMES`; persistence target equality is preserved.
- Project normalized trigger, numeric timing and persistence semantics into Phase-A decomposition fields before Python validation, while keeping natural-language interpretation LLM-owned.
- Supplement missing-evidence target validation from the normalized requirement contract when a required response signal is absent from current observations.
- Normalize applicability-labelled evidence needs out of the evaluation bucket and defer trigger-timestamp needs until trigger decomposition is present.
- Escalate deterministic repair `NO_CHANGE` to 27B semantic arbitration instead of terminating the requirement repair loop.
- Retain the 16k large-case Phase-A budget; the live TC12 v0.7.0 failure showed both Phase-A calls ended with `finish_reason=stop`, so token expansion was not the corrective action.
- Add `docs/V0.7.1_RELEASE_NOTES.md` and v0.7.1 contract/regression tests.
- Automated local suite: **151 passed**.

## 0.7.0

- Split Qwen3.5-4B language processing into dedicated source-availability, content-classification, atomic-claim, requirement-language, hypothesis-epistemic-review, and final-wording stages.
- Split Qwen3.8-27B deep analysis into Phase A requirement reasoning and Phase B RCA synthesis, with Python-validated compliance truth as an immutable boundary between them.
- Add relationship-preserving requirement chunking and a 16k large-case Phase-A output budget for TC12/TC21-class inputs.
- Treat `finish_reason=length` explicitly as token exhaustion and make bounded retry output-oriented with reduced reasoning effort.
- Execute 4B-normalized applicability predicates deterministically to remove TC4-style evaluation evidence observed at a point where the requirement condition is explicitly false.
- Use 4B atomic claims for proposition-level reported/direct timing conflict comparison, fixing TC8-style compound-sentence false conflicts.
- Add 4B hypothesis semantic/epistemic classification with Python-gated KEEP/REWRITE/DROP actions to distinguish mechanism candidates from compliance restatements and excessive causal wording.
- Harden cancellation translation for read/transport failures caused by closing an active stream.
- Expand Live Pipeline observability to the complete v0.7.0 18-stage architecture plus dynamic chunk/repair children.
- Preserve v0.6.x session compatibility through optional new intermediate fields and retained legacy fields.
- Add dedicated `docs/V0.7.0_RELEASE_NOTES.md`; every release from v0.7.0 onward must include its own release-note file.
- Automated local suite: **142 passed**.

## 0.6.5

- Revert the final Qwen3.5-4B linguistic reviewer to the validated non-thinking default: reasoning `provider_default`, Thinking `off`, transport `auto` (which resolves Qwen3.5 to the manual `/v1/completions` structured path).
- Preserve the v0.6.4 structured relevance/sufficiency/verdict review contract; only the execution policy changed.
- Add one bounded recovery path for users who explicitly enable chat/thinking: if the OpenAI-chat final review exhausts structured output/returns empty assistant content, retry once through the non-thinking Qwen3.5 manual path. Network/request failures are not duplicated through the fallback.
- Add a deterministic unresolved-compliance hypothesis guard: a `NOT EVALUABLE` timing requirement with incomplete event coverage cannot be restated as a supported hypothesis using only the same trigger/response observations already declared insufficient. Independent diagnostic/historical/mechanism evidence can still support a candidate hypothesis.
- Keep `validated.semantic.hypotheses` synchronized with the validator-filtered hypothesis list.
- Fix double terminal punctuation in the Section 11 supported-hypotheses summary.
- Add v0.6.5 regressions for TC5 hypothesis removal, independent mechanism evidence, reviewer fallback construction/execution, non-thinking defaults, punctuation, and version-history continuity.
- Automated local suite: **132 passed**.

## 0.6.4

- Replace the broad final 4B contradiction judgment with a structured per-requirement review contract that separately extracts evidence relevance, evidence sufficiency, and any implied evaluation status from the current relevance wording.
- Add deterministic comparison of those extracted language claims against the authoritative validated structure before any relevance rewrite can be accepted.
- Treat `RELEVANT + INSUFFICIENT + NOT_EVALUABLE` as an explicit valid combination so TC5-style relevant-but-insufficient evidence cannot be flagged as a contradiction merely because the requirement remains unevaluable.
- Keep Python as the final gate while preserving the 4B role as the natural-language interpreter: the model reads what the sentence claims; Python checks those structured claims against authoritative facts.
- Give the final 4B reviewer its own model settings, independent from intake/repair: default reasoning `Low`, thinking `provider/default`, and OpenAI-chat transport. Intake and field repair remain non-thinking by default.
- Expose separate final-review reasoning, thinking, and transport controls in the GUI and persist them in application configuration.
- Add cumulative `VERSION_HISTORY.md`, ordered chronologically and describing every tracked transition from one RCA Analyst POC version to the next.
- Add v0.6.4 regressions for TC5 relevance/sufficiency separation, unsafe structured reviewer claims, final-review client defaults, and version-history completeness.
- Automated local suite: **125 passed**.

## 0.6.3

- Give Qwen3.5 intake explicit semantic source-availability states: `PRESENT`, `ABSENT`, `UNKNOWN`, `NOT_MENTIONED`.
- Add structured requirement/historical/diagnostics/trace availability sections and separate `user_instructions` from evidence/unclassified text.
- Teach the 4B intake prompt multilingual/paraphrased absence and presence distinctions, including `not available` / `nicht verfügbar` versus `no DTCs present` / `Keine Fehler im Fehlerspeicher`.
- Keep natural-language absence understanding in the 4B intake model; Python canonicalization only enforces normalized invariants such as non-PRESENT sources containing no evidence blocks. The legacy template-only deterministic path remains available when intake is bypassed/off.
- Preserve source-availability metadata and its verbatim source statement in the canonical case without promoting it to engineering evidence.
- Clarify final-review policy that relevance and sufficiency are independent, preventing TC5-style false contradiction findings.
- Explicitly decode cancellable SSE streams as UTF-8 to prevent mojibake in arrows, punctuation, and German characters.
- Keep 4B Thinking OFF by default pending benchmark evidence that it improves intake classification enough to justify additional latency.
- Automated local suite: **119 passed**.

## 0.6.2

- Fix forced 4B intake failure exposed by TC5 when Qwen3.5 returned YAML-like section output instead of the requested JSON object.
- Embed the exact response-model JSON Schema into manual Qwen3.5 `/v1/completions` prompts.
- Reject YAML/prose wrappers and arbitrary embedded JSON fragments; structured output must be one top-level JSON object.
- Preserve the existing one bounded 4B structured retry for malformed output, now with generic schema-specific JSON-only guidance.
- Prevent a structurally valid but empty 4B intake object from erasing deterministic requirements when `Intake Routing = Always`; retain the deterministic parse and mark intake as attention.
- Add v0.6.2 regressions for the exact TC5 intake failure and forced-intake fallback.
- Automated local suite: **111 passed**.

## 0.6.1

- Add a GUI **Stop** control for both single-case analysis and sequential batches.
- Add a shared thread-safe cancellation token across GUI workers, `RCAPipeline`, and all LM Studio clients.
- Use cancellable OpenAI-compatible SSE streaming for GUI model calls and close the active response when Stop is requested.
- Reject interrupted/partial structured output instead of treating it as malformed output eligible for repair/retry.
- Stop batch execution after the active case, preserving completed cases and preventing queued cases from starting.
- Mark interrupted Live Pipeline stages as `CANCELLED`.
- Add cancellation regression tests; full suite now passes 109 tests.

## 0.6.0

- Introduce a multi-model RCA pipeline while preserving the frozen evidence semantics and Python final authority.
- Add conditional Qwen3.5-4B intake normalization for inconsistent human testcase formats; clean formal inputs bypass it in `auto` mode.
- Add source-span enforcement and Python canonicalization so the 4B intake model cannot invent evidence IDs, transitions, timestamps, clocks, event coverage, or verdicts.
- Reuse the same Qwen3.5-4B model for three isolated services with separate budgets: intake normalization, field-level repair, and final linguistic consistency review.
- Add a compact post-validation 4B review that may patch `relevance` wording only; every patch is deterministically revalidated and Python remains the final gate.
- Refine TC5-style timing output so known same-clock trigger/response timestamps are acknowledged and only missing transition-event coverage is requested.
- Expand Live Pipeline stages to show input classification, optional 4B intake, Python canonicalization, 27B semantic reasoning, repairs, 4B review, Python final gate, formatting, and final output.
- Add v0.6.0 regression guards proving unsupported 4B intake spans are rejected and unsafe final-review wording cannot override deterministic truth.
- Automated local suite: **104 passed**.

## 0.5.5

- Fixed false timebase requests in Section 10 when trigger and response are already on the same clock/source.
- Added actual evidence-clock inspection before adding a clock-alignment acquisition need.
- Added the Live Pipeline GUI inspector with stage-by-stage status, user-friendly summaries, and exact input/output views.
- Added live trace callbacks to single-case and sequential-batch pipeline execution, including repair stages and failures.
- Added regressions for same-clock suppression, true multi-clock alignment requests, and complete live stage tracing.


## 0.5.4

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

## 0.5.3

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

## 0.5.2.1

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

## 0.5.2

- Add deterministic `STATE_CONFORMANCE_COVERAGE_INSUFFICIENT` normalization: interval-scoped applicability plus only point-level matching response evidence can no longer yield `SUFFICIENT_CONFORMANCE` / `SATISFIED`.
- Preserve the asymmetric counterexample rule: a correlated contradictory point sample may still establish `SUFFICIENT_NONCONFORMANCE` / `VIOLATED`.
- Derive a targeted `OBSERVATION_INTERVAL` evidence need for the required response/state when conformance coverage is incomplete.
- Add TC2 regression coverage for REQ-101 = VIOLATED, REQ-102 = NOT EVALUABLE, REQ-103 = NOT APPLICABLE while preserving TC1/TC3 semantics.
- Add a GUI button to run TEST-001, TEST-002, and TEST-003 strictly sequentially with a fresh pipeline per case.
- Auto-save all batch reports/sessions and create JSON/Markdown batch summaries under `batch_results/<timestamp>/`.
- Add persisted Dark/Light theme selection.
- Improve Section 11 confirmed-finding readability with bullet formatting.
- Automated test suite: 63 passed.

## 0.5.1

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

## 0.5.0

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

## 0.4.3

- Separate generic `coverage_complete` from explicit `event_coverage_complete`; legacy `Coverage Complete: true` no longer implies complete transition capture.
- Add explicit `Event Coverage Complete: true` trace metadata and require it for deterministic late-response timing violations.
- Formalize evidence scope: `STATE_SAMPLE` proves only an instant, `TRANSITION` proves a change event, and `INTERVAL_STATE` proves persistence across an interval.
- Downgrade condition-only `NOT APPLICABLE` decisions to `APPLICABILITY UNKNOWN` when they are supported only by point state samples; interval-state or authoritative scope evidence is required for case-wide non-applicability.
- Require explicit `INTERVAL_STATE` evaluation evidence for persistence `SATISFIED` / `VIOLATED` verdicts; generic/event coverage metadata cannot substitute.
- Add deterministic normalization for persistence sufficiency and resolved persistence evidence needs.
- Update TEST-003 to use explicit event coverage and interval-state AvailabilityStatus evidence.
- Add regression tests for legacy generic-coverage rejection, point-sample NOT-APPLICABLE suppression, and persistence interval-state enforcement.

## 0.4.2

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

## 0.4.1

- Fix startup failure on Python 3.9 caused by Python 3.10-only PEP 604 type annotations such as `float | None`.
- Replace all runtime-evaluated `X | None` annotations with `typing.Optional[X]`.
- Restore documented minimum runtime to Python 3.9+.
- No semantic-analysis, validator, evidence-binding, or report-generation behavior changed from v0.4.0.

## 0.4.0

- Introduce explicit applicability evidence binding as an architectural contract: `applicability_evidence_ids` is required in LLM structured output, and resolved applicability without a valid current-case evidence citation is downgraded to UNKNOWN.
- Atomize conservative direct-observation lines and preserve `signal_name` / `signal_value` metadata.
- Parse optional direct-observation `Clock ID` / `Timebase`, `Coverage Complete`, and numeric timestamps into deterministic evidence metadata.
- Preserve evidence-backed APPLICABLE and NOT APPLICABLE decisions when the LLM supplies explicit valid current-case evidence bindings; unresolved/unbound decisions are downgraded to UNKNOWN.
- Normalize NOT APPLICABLE evaluation sufficiency to `NOT_REQUIRED` and remove irrelevant response evidence/needs.
- Split Section-7 applicability evidence from evaluation evidence.
- Fix minimum-evidence closure so resolved SATISFIED / VIOLATED / NOT APPLICABLE requirements do not request further compliance evidence.
- Add TEST-002 and v0.4.0 regressions for atomic evidence provenance and the expected `VIOLATED / SATISFIED / NOT APPLICABLE` path.

## 0.3.6

- Generalize logical-direction protection to every one-way `if` / `when` / `upon` requirement, not only PERMISSIVE requirements.
- Normalize relevance prose that invents `only if` / `only when` / necessary-condition semantics absent from the source.
- Reject converse/exclusivity invention in `faithful_meaning` so genuine semantic reversal triggers targeted repair instead of being silently accepted.
- Preserve explicit source exclusivity such as `only if`, `only when`, and `if and only if`.
- Remove generic explain/explanation wording from requirement relevance; causal explanation remains hypothesis-only.
- Extend analyzer/repair prompts with the same general invariants.
- Replay the real v0.3.5 TEST-001 first response with zero critical errors and no LLM repair.

## 0.3.5

- Stop deterministic response-observation auto-mapping for PERMISSIVE requirements; clear any supplied ordinary evaluation evidence and keep `evaluation_sufficiency = NOT_REQUIRED`.
- Tighten relevance normalization for phrases that require a condition to be excluded/confirmed before attributing the symptom to a failure/violation.
- Preserve already-correct timed relevance prose when it explicitly states that timing remains unevaluable because timestamp/window evidence is missing.
- Extend semantic/repair prompts with the same invariants.
- Replay the real v0.3.4 TEST-001 first response with zero critical errors and no LLM repair.

## 0.3.4

- Add `NOT_REQUIRED` as the canonical evaluation-sufficiency state for PERMISSIVE requirements; normalize `SUFFICIENT_CONFORMANCE`/`INSUFFICIENT` to it without an LLM repair.
- Reject `NOT_REQUIRED` for MANDATORY/PROHIBITIVE requirements.
- Broaden the timing-relevance guard to catch statements that a complete timed response "did not occur" when timestamps/full-window coverage are missing.
- Extend semantic/repair prompts with the same invariants.
- Replay the real v0.3.3 TEST-001 first response with zero critical errors and no repair requirement.

## 0.3.3

- Add a soft-converse guard for PERMISSIVE relevance prose so one-way permissions cannot become gates, prerequisites, or necessity/exclusivity claims.
- Remove causal/alternative-failure wording from requirement relevance; relevance remains requirement-local and descriptive.
- Compact true-persistence missing evidence into one observation-interval acquisition need instead of duplicate RESPONSE + OBSERVATION_INTERVAL prose.
- Extend the semantic prompt with the same relevance constraints to reduce normalization work while keeping Python authoritative.
- Replay the v0.3.2 TEST-001 first response with zero critical errors and no repair requirement.

## 0.3.2

- Normalize timed-requirement evidence needs deterministically instead of requesting an LLM repair for missing/mislabelled `TIMING` bookkeeping.
- Collapse duplicate trigger/timestamp/window/timebase requests into a concise canonical evidence bundle.
- Add a relevance guard that prevents non-timestamped observations from being described as proving a timing-bound failure.
- Preserve the v0.3.1 separation between true persistence and ordinary timed-window coverage.

## 0.3.1

- Fixed false `MISSING_PERSISTENCE_EVALUATION_NEED` / `MINIMUM_EVIDENCE_PERSISTENCE_CLOSURE_FAILED` errors for timed transition requirements that merely require 500 ms observation coverage.
- Added explicit distinction between true persistence semantics (`remain`, `stay`, prohibitive non-occurrence) and ordinary timing-window coverage.
- Auto-maps supplied reported/direct observations that mechanically match a requirement response instead of spending an LLM repair pass.
- Derives missing true-persistence `OBSERVATION_INTERVAL` evidence needs deterministically.
- Prevents derived `validated.*` errors from being sent to the LLM for repair.
- Global derived errors no longer disable targeted repair for requirement-local semantic defects.
- Normalizes unsafe relevance prose that introduces causal/cross-requirement interpretation.
- Added regression tests and replayed the real failed v0.3 session: first-pass semantic output now validates with zero critical errors.

## 0.3.0

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

## 0.2.1

- Fixed a false-fatal `MISSING_CONDITION_APPLICABILITY_NEED` failure seen on REQ-003-style `if` requirements.
- Missing applicability evidence is now normalized deterministically once condition/trigger decomposition is known.
- A condition need incorrectly labelled `TRIGGER` is corrected to `APPLICABILITY` when the requirement has no true trigger.
- If a model omits the missing applicability need entirely, the validator derives a neutral evidence request from the decomposed condition/trigger instead of wasting a repair pass.
- Added regression tests for condition relabelling, omitted condition needs, and omitted trigger needs.

## 0.2.0

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

## 0.1

- First real local Qwen3.8-27B Q6_K + Medium RCA POC run; reduced the previously observed runtime from roughly 70 minutes to roughly 32 minutes.
- Used the early model/validator architecture before deterministic source-boundary parsing.
- The run exposed the gaps that motivated v0.2: ticket-description prose could be promoted as an observation, the dedicated Reported Test Result was not authoritative, requirement decomposition could be incomplete without failing validation, evidence mapping could be missing/misbucketed, and Section 10 evidence closure was incomplete.
- This release predates the formal changelog; its baseline description is reconstructed from the repository README section "Why v0.2 exists."
