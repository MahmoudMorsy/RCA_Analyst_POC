# RCA Analyst — Product Requirements Document (PRD)

**Current application release:** v1.8.7  
**Current RCA semantic-core baseline:** v0.8.6 candidate  
**Validation status:** automated release gates are required and live TC17/TC12 validation remains pending. RCA Core v0.8.6 must not be declared frozen until those live reruns meet expected semantic targets.

## 1. Product vision

RCA Analyst is a generic automotive root-cause-analysis application for heterogeneous engineering evidence with strict provenance, conservative uncertainty handling and portable deployment across Dell, RunPod and future home AI hardware.

Governing rule:

> LLMs interpret language and engineering context into structured semantics. Python executes verified semantics deterministically. Stronger models are capacity/escalation resources, not owners of compliance truth.

## 2. Core RCA requirements

The product shall:

1. preserve original requirement/evidence source text and provenance;
2. distinguish structural parsing from language semantics;
3. compile free-form/mixed-language requirements into executable Requirement IR;
4. annotate free-text evidence into structured semantic facts without Python NLP invention;
5. independently verify semantic fidelity before deterministic execution;
6. execute applicability, Boolean logic, state/transition/interval, timing and persistence deterministically in Python;
7. remain conservative for missing/uncorrelated/unresolved evidence;
8. use semantic arbitration only for material unresolved issues;
9. route deep RCA only when actual mechanism-oriented evidence justifies it;
10. produce auditable structured results, report, attempts, repair history, metrics and sessions.

## 3. Application requirements

The Web application shall:

- keep the browser free of RCA decision logic;
- use versioned FastAPI `/api/v1` backend contracts;
- keep long runs backend-owned and reconnectable;
- preserve cooperative Stop/Abort;
- expose dynamic pipeline stages with persistent inputs/outputs;
- render structured stage data human-readably while preserving Raw JSON;
- provide full result parity for each testcase inside a batch;
- expose per-case/per-stage/model-call statistics;
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
Authoritative for structural executability, timestamps, Boolean IR execution, timing math, evidence scope/correlation, applicability/compliance verdicts, materiality and final consistency.

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
- transport-valid IR is not automatically executable IR.

## 7. Current RCA Core v0.8.6 pipeline

```text
RAW CASE
→ Python structural ingestion / intake routing
→ optional utility-model source/content sectioning
→ Python canonicalization
→ Requirement IR compilation (Small / Utility OR Primary role)
→ targeted structural semantic completion if needed
→ Evidence Semantic Annotation (same selected preparation role)
→ narrow schema-envelope canonicalization
→ targeted evidence completion if needed
→ independent Requirement Semantic Verification (Small / Utility OR Primary role)
→ Python semantic integrity/materiality + structured fingerprint comparison
→ optional one Primary semantic arbitration
→ verified semantic representation
→ Python deterministic compliance engine
→ RCA router
→ optional one Primary RCA synthesis when mechanism evidence exists
→ optional utility hypothesis/wording reviews
→ Python final consistency gate
→ deterministic 11-section report
```

## 8. v0.8.5 semantic hardening

Live v1.8.5 Dell/RunPod evidence established that v0.8.4 could not be frozen:

- TC17 Boolean grouping was miscompiled while the same verifier returned `VERIFIED`;
- arbitration could explain evidence in notes while returning non-executable structured facts;
- Qwen3.5-4B repeatedly invented evidence schema enum values after context was increased beyond 8K.

v0.8.5 therefore:

- adds capacity-neutral Critical Semantic Model Routing;
- requires an independent source-derived structured semantic fingerprint from the verifier and Python structural comparison;
- rejects notes-only/non-executable arbitration evidence replacements;
- tightens evidence prompt enums without Python phrase/operator mappings.

### v0.8.6 live-TC17 hardening

The v1.8.6 live TC17 run showed that stronger 27B semantics alone were insufficient: Thinking Off was not reaching llama.cpp, reasoning text was invisible in token telemetry, structural completion regenerated too much IR, persistent evidence scope remained non-executable, narrative ambiguity was over-materialized, and arbitration provenance was separated from executable nodes. v0.8.6 therefore adds request-level thinking control, targeted structural patches, reasoning-content observability, explicit persistent-scope completion, structured-dependency materiality and stricter executable-node provenance. Python evidence/compliance rules remain unchanged.

## 9. Current application architecture v1.8.7

```text
Same Web UI
→ FastAPI /api/v1
→ backend-owned Run Manager / Storage / Sessions / Telemetry
→ RCA Core v0.8.6
→ ModelGateway
→ OpenAI-compatible LM Studio / llama.cpp / vLLM / future provider
→ Dell / RunPod / Home
```

v1.8.7 retains the v1.8.6 Web repairs and adds:

- request-level Qwen/llama.cpp Thinking Off/On propagation for critical semantic roles;
- reasoning-content presence/character telemetry independent of provider reasoning-token accounting;
- targeted Requirement IR structural patches instead of full-IR regeneration;
- bounded targeted semantic-completion budgets;
- persistent evidence scope completion and structured-dependency materiality;
- arbitration provenance attached directly to executable repaired nodes.

The v1.8.6 Stage Input persistence, readable structured I/O, batch testcase parity, incremental results, statistics, current-endpoint discovery/test, environment-override visibility, per-run snapshots and external-server authority UX remain required.

## 10. Configuration requirements

Separate:

- RCA behavior configuration;
- Primary and Small / Utility model-role configuration;
- critical semantic routing (`semantic_preparation_role`, `semantic_verification_role`);
- inference-engine/provider metadata;
- detected infrastructure.

External model-server launch settings such as llama.cpp `-c`, GPU layers or Flash Attention remain server-managed unless a future adapter explicitly owns process lifecycle.

## 11. Telemetry/benchmarking

Capture per call: role/stage/model/provider/endpoint, prompt/completion/reasoning/total tokens, duration, finish reason, retries, transport and throughput.

Aggregate per testcase and stage. Failed calls must remain visible. Compare semantic acceptance separately from execution status.

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

## 13. Release acceptance

Every release must:

1. increment versions intentionally;
2. update README/CHANGELOG/VERSION_HISTORY;
3. update semantic/application architecture docs when affected;
4. include release notes;
5. pass full working-tree tests;
6. pass compile/static checks;
7. build a clean ZIP;
8. pass full tests from a fresh extraction;
9. contain no caches/pyc/Git junk;
10. include required docs;
11. record SHA-256.
