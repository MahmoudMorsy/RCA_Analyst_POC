# RCA Analyst — Product Requirements Document (PRD)

**Current application release:** v1.8.11  
**Current RCA semantic-core baseline:** v0.8.10 candidate  
**Validation status:** v1.8.10 completed the full 17-case 27B RunPod suite: 17/17 executions completed, 11/17 semantic acceptance passed, and TC12/TC17 hit their expected targets. v1.8.11 fixes the six remaining contract failures and remains candidate until its exact package passes the full live suite.

## 1. Product vision

RCA Analyst is a generic automotive root-cause-analysis application for heterogeneous engineering evidence with strict provenance, conservative uncertainty handling and portable deployment across Dell, RunPod and future home AI hardware.

Governing rule:

> LLMs interpret language and engineering context into structured semantics. Python executes verified semantics deterministically. Stronger models are capacity/escalation resources, not owners of compliance truth.

## 2. Core RCA requirements

The product shall:

1. preserve original requirement/evidence source text and provenance;
2. distinguish structural parsing from language semantics;
3. compile free-form/mixed-language requirements into executable Requirement IR;
4. guarantee bounded compiler batch completeness against authoritative Requirement IDs;
5. annotate free-text evidence into structured semantic facts without Python NLP invention;
6. independently reconstruct and verify source semantics before deterministic execution;
7. execute applicability, Boolean logic, state/transition/interval, timing and persistence deterministically in Python;
8. remain conservative for missing/uncorrelated/unresolved evidence;
9. make evidence materiality depend on authoritative structured relationships, not same-signal similarity alone;
10. use semantic arbitration only for material unresolved issues rather than routine schema/provenance repair;
11. route deep RCA only when positive mechanism-oriented evidence justifies it;
12. accept only grounded canonical evidence or VERIFIED semantic facts as hypothesis provenance;
13. produce auditable structured results, reports, attempts, repair history, metrics and sessions.

## 3. Application requirements

The Web application shall:

- keep the browser free of RCA decision logic;
- use versioned FastAPI `/api/v1` backend contracts;
- keep long runs backend-owned and reconnectable;
- preserve cooperative Stop/Abort;
- expose dynamic pipeline stages with persistent inputs/outputs;
- render structured stage data human-readably while preserving Raw JSON;
- expose testcase lifecycle from `RUNNING` through terminal status for both single and batch runs;
- keep the current running testcase selectable even after the user browses a completed result;
- provide full result parity for each testcase inside a batch;
- expose per-case/per-stage/model-call statistics, including failed calls;
- keep model/provider logic behind ModelGateway;
- support Dell/RunPod/Home through configuration, not forks;
- preserve desktop fallback until Web/live parity is accepted.

## 4. Scope boundary

Specialized Stage-1 parsers remain a separate workstream: EA exports/relationships, OneNote historical tickets, Excel/KPM metadata, BZD XML/HTML, CAPL signal logs and canonical bundle construction.

Do not move these parser responsibilities into RCA semantic core.

## 5. Authority model

### Original source
Authoritative for what was written/measured; immutable provenance.

### Language model roles
Own language interpretation, Requirement IR compilation, evidence annotation, targeted semantic completion and independent semantic verification. Model capacity is configurable per role.

### Python
Authoritative for structural executability, expected-ID batch completeness, timestamps, Boolean IR execution, timing math, evidence scope/correlation, materiality, applicability/compliance verdicts and final consistency.

Python may normalize source formatting for provenance matching, but must not add automotive/natural-language semantic mappings.

### Primary/deep model
May provide material semantic arbitration and RCA synthesis when routed. It cannot override Python compliance truth.

## 6. Frozen evidence/compliance invariants

Preserve all established rules, including:

- `STATE_SAMPLE`, `TRANSITION`, `INTERVAL_STATE` remain distinct;
- point state proves only the point;
- separate points do not prove simultaneity without correlation;
- one opposite point cannot prove case-wide NOT APPLICABLE;
- interval evidence is required where persistence/scope demands it;
- state sample is not a transition;
- matching point evidence does not prove persistent conformance;
- contradictory correlated point can prove violation asymmetrically;
- applicability and evaluation evidence remain separate;
- historical tickets are non-normative;
- missing evidence remains UNKNOWN / NOT EVALUABLE;
- hypotheses require positive mechanism support;
- unresolved compliance propositions cannot be repackaged as RCA using the same incomplete evidence;
- assignments remain raw; transitions are inferred only from actual ordered value changes;
- repeated points never become interval evidence automatically;
- Python owns final compliance truth and must not grow multilingual NLP heuristics;
- simple IF state conditions are applicability, not transition triggers;
- global coverage is not automatically signal-specific evidence;
- NL “throughout” scope is non-executable until resolved with concrete scope;
- raw source is never discarded;
- transport-valid IR is not automatically executable IR;
- same-signal overlap alone is insufficient evidence materiality.

## 7. Current RCA Core v0.8.10 pipeline

```text
RAW CASE
→ Python structural ingestion / intake routing
→ optional utility-model source/content sectioning
→ Python canonicalization
→ bounded Requirement IR compilation (Small / Utility OR Primary)
→ Python expected-ID completeness check
→ one missing-ID semantic recovery call if needed
→ targeted structural semantic completion pass 1 if needed
→ optional targeted structural completion pass 2 only if pass 1 exposes another missing top-level object
→ Evidence Semantic Annotation
→ narrow schema-envelope canonicalization
→ targeted evidence completion if needed
→ independent Requirement Semantic Verification (Small / Utility OR Primary)
→ Python structured fingerprint comparison + semantic integrity/materiality
→ optional one issue-scoped Primary semantic arbitration
→ verified semantic representation
→ Python deterministic compliance engine
→ RCA router
→ optional one Primary RCA synthesis when mechanism evidence exists
→ optional utility hypothesis/wording reviews
→ Python final consistency gate
→ deterministic 11-section report
```

## 8. Semantic architecture evolution

### v0.8.5

- capacity-neutral Critical Semantic Model Routing;
- independent source-derived structured verifier fingerprint;
- Python detection of TC17-style Boolean regrouping despite a `VERIFIED` model label;
- rejection of notes-only/non-executable arbitration evidence repairs;
- strict evidence enum contract without Python model-word mappings.

### v0.8.6

- request-level Qwen/llama.cpp Thinking Off/On propagation;
- reasoning-content observability;
- targeted Requirement structural patches instead of full-IR regeneration;
- bounded semantic-completion budgets;
- executable persistent-scope completion;
- stronger arbitration provenance attached directly to executable nodes.

### v0.8.7 full-suite hardening

The complete v1.8.7 RunPod regression executed all 17 cases but exposed systemic semantic-contract failures. v0.8.7 therefore added:

- expected Requirement-ID completeness validation and one bounded missing-ID recompilation;
- complete source-clause audit inventory as a structural-completion target;
- semantic-ID/source-clause linkage checks for condition, trigger, behavior, timing and persistence;
- independent verifier normative-polarity reconstruction;
- safe formatting-insensitive source grounding with explicit ordered ellipsis support;
- authoritative structured materiality instead of same-signal/loose narrative materiality;
- compact issue-scoped exact-source arbitration packets;
- VERIFIED semantic fact IDs as valid RCA provenance;
- semantic acceptance rejection when internal semantic-integrity ERRORs remain.

None of these changes add Python natural-language meaning extraction or weaken evidence/compliance conservatism.

## 9. Current application architecture v1.8.10

```text
Same Web UI
→ FastAPI /api/v1
→ backend-owned Run Manager / Storage / Sessions / Telemetry
→ RCA Core v0.8.10
→ ModelGateway
→ OpenAI-compatible LM Studio / llama.cpp / vLLM / future provider
→ Dell / RunPod / Home
```

v1.8.11 retains all v1.8.10 Web/model/reconnect/failure-containment improvements and adds live-suite semantic contract hardening:

- case enters the Tests list as `RUNNING` before pipeline execution;
- the same lifecycle row updates to PASS/FAILED/CANCELLED;
- single and batch runs use the same Tests selector concept;
- live running case remains selectable after browsing finished cases;
- live Pipeline/Logs/partial Stats remain available before final result;
- final-only tabs explicitly show that the result is not yet available.

## 10. Configuration requirements

Separate:

- RCA behavior configuration;
- Primary and Small / Utility model-role configuration;
- critical semantic routing (`semantic_preparation_role`, `semantic_verification_role`);
- inference-engine/provider metadata;
- detected infrastructure.

External model-server launch settings such as llama.cpp `-c`, GPU layers or Flash Attention remain server-managed unless a future adapter explicitly owns process lifecycle.

## 11. Telemetry/benchmarking

Capture per call: role/stage/model/provider/endpoint, prompt/completion/reasoning/total tokens, reasoning-content presence, duration, finish reason, retries, transport and throughput.

Aggregate per testcase and stage. Failed calls must remain visible. Compare semantic acceptance separately from execution status. Preserve lifecycle status for the currently running testcase.

## 12. Live validation targets

TC12 target remains:

- REQ-1201 APPLICABLE / NOT EVALUABLE
- REQ-1202 NOT APPLICABLE
- REQ-1203 UNKNOWN / NOT EVALUABLE
- REQ-1204 APPLICABLE / VIOLATED; deterministic 1100 ms vs 800 ms, +300 ms
- REQ-1205 UNKNOWN / NOT EVALUABLE
- REQ-1206 NOT APPLICABLE
- REQ-1207 APPLICABLE / SATISFIED
- REQ-1208/1209/1210 UNKNOWN / NOT EVALUABLE
- no unsupported hypotheses.

TC17 target remains:

- REQ-1701 APPLICABLE / VIOLATED
- REQ-1702 NOT APPLICABLE
- REQ-1703 NOT APPLICABLE
- no unsupported hypotheses.

The next acceptance run should be the complete regression bundle with stable model settings, not testcase-specific code/config changes.

## 13. Release acceptance

Every release must:

1. increment versions intentionally;
2. update README/CHANGELOG/VERSION_HISTORY;
3. update semantic/application architecture docs when affected;
4. include release notes and synchronized handoff;
5. pass full working-tree tests;
6. pass compile/static/JS/FastAPI smoke checks;
7. build a clean ZIP;
8. pass full tests from a fresh extraction of that ZIP;
9. contain no caches/pyc/Git/virtualenv junk;
10. include required docs;
11. record SHA-256.


## v1.8.10 acceptance delta

In addition to all v1.8.9 requirements, sequential regression/bundle execution must continue after a testcase-local unexpected exception. Pipeline construction is inside testcase isolation. Generic failure records must preserve exception type/message/traceback and partial pipeline. Session export must preserve partial results plus any run-level failure.

RCA Core arbitration is a repair mechanism, not a liveness dependency: a contract-invalid arbitration response is rejected atomically, its raw attempt is retained, material issues remain unresolved, and compliance continues conservatively. A target field may be omitted only when every material issue governing that field is explicitly unresolved. Independent verifier equality must compare executable semantics rather than descriptive `process_description` text, and persistence scope comparison must use normalized structured categories rather than arbitrary model wording.


## v1.8.11 acceptance delta

The exact v1.8.10 27B suite proved the application-level batch continuation fix and live-confirmed TC12/TC17. v1.8.11 acceptance additionally requires:

- `resolution=VERIFIED` verifier fingerprints are structurally complete before comparison;
- requirement persistence scope is canonical and distinct from evidence observation types;
- redundant unchanged untargeted arbitration fields are ignored, while changed untargeted fields remain rejected;
- creating a missing executable semantic field also targets `source_clauses` when its audit role is absent;
- referenced canonical structural direct observations are present in the RCA Evidence Packet;
- arbitration contract rejection reason is preserved in attempt diagnostics.

The next live full-suite focus is TEST-007/015/016/018/019/021 while TC12 and TC17 remain non-regression anchors.
