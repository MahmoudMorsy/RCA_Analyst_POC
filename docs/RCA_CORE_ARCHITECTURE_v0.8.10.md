# RCA Analyst POC RCA Core v0.8.10 Architecture

**Status:** candidate; not frozen  
**Carried by:** RCA Analyst application v1.8.11

## 1. Governing authority

> LLMs interpret human language into structured semantics. Python executes verified semantics deterministically. Model capacity and routing do not transfer compliance authority away from Python.

Original source text remains immutable provenance. Python owns structural executability, timestamp mechanics, Boolean execution, state/transition/interval semantics, timing calculation, evidence bucketing, applicability/compliance verdicts and final consistency.

No v0.8.10 fix introduces Python natural-language interpretation or weakens frozen evidence rules.

## 2. Pipeline topology

```text
RAW CASE
  ↓
Python structural ingestion / intake routing
  ↓
optional Utility model free-form sectioning
  ↓
Python canonicalization
  ↓
Critical Semantic Preparation model
  ├─ Requirement IR compilation in bounded batches
  ├─ targeted RequirementStructuralPatch completion [conditional]
  ├─ evidence semantic annotation
  └─ targeted evidence completion [conditional]
  ↓
Independent Semantic Verification model
  └─ source-derived structured semantic fingerprint
  ↓
Python semantic integrity + materiality
  ↓
optional one Primary semantic arbitration
  ↓
post-arbitration verification + Python integrity
  ↓
Verified Semantic Representation
  ↓
Python deterministic compliance
  ↓
RCA router
  ↓
optional one Primary RCA synthesis when mechanism evidence justifies it
  ↓
optional utility hypothesis/wording reviews
  ↓
Python final gate
  ↓
deterministic 11-section report
```

Critical semantic preparation and verification remain capacity-neutral roles: either may be routed to Small / Utility or Primary. The intended RunPod validation after v1.8.10 uses the stronger Primary 27B for both critical semantic roles while retaining utility tasks on the smaller model where appropriate.

## 3. Transport thinking control

Reasoning/thinking selection is a model-transport concern, not an RCA semantic rule.

When Thinking Off is selected for an OpenAI-compatible Qwen/llama.cpp request, v1.8.10 sends request-level chat-template control equivalent to:

```json
{"chat_template_kwargs": {"enable_thinking": false}}
```

Thinking On sends `true`. Provider-default leaves the option unspecified. A bounded compatibility retry may remove the optional field only if the provider rejects it as unsupported.

Reasoning text presence is observable independently from provider-reported reasoning token count.

## 4. Requirement semantic compilation

The compiler produces declarative Requirement IR. Every material source clause must be represented both in provenance and in executable fields.

### 4.1 Conditions

Conditions use a recursive Boolean AST:

- TRUE;
- PREDICATE;
- AND;
- OR;
- NOT.

Nested grouping must be preserved exactly. `A AND (B OR C) AND D` is not equivalent to `A AND [B AND (C OR D)]`.

Simple source negatives such as `X is not Y` are represented as grounded `NEQ` predicates. NOT is reserved for negation where a compound expression is genuinely needed.

### 4.2 Required behavior

A signal/value obligation is executable only when the behavior contains:

- semantic ID;
- exact grounded source phrase;
- signal;
- executable operator;
- value.

Provenance-only shells are non-executable.

### 4.3 Timing and persistence

Exact timing limits are structured, then executed by Python from verified timestamps.

Persistence exists only when explicitly supported by the source. It requires `required=true` and a concrete scope representation. A plain `shall be X` obligation does not gain invented persistence.

## 5. Compiler batch completeness

Every bounded Requirement Compilation request has an authoritative expected requirement-ID set. Python checks the returned IDs before accepting the batch. Missing IDs receive exactly one bounded semantic recompilation for the missing requirements only; recovered objects are merged in original source order.

Unknown extra Requirement IRs are not promoted. Any ID still missing after recovery remains a material semantic-integrity failure. Python never reconstructs the missing requirement from natural language.

## 6. Targeted structural completion

v0.8.8 keeps targeted field patches and expands them to complete provenance/audit repair. Source-clause inventories, timing and persistence provenance are first-class completion targets.

Python determines exact incomplete fields from structured IR/source-clause integrity. It sends only those targets to the semantic model. The response is `RequirementStructuralPatchBatch`.

Python accepts a patch only when it:

- identifies a known requirement;
- changes only requested target fields;
- does not duplicate a requirement patch;
- contains an actual targeted repair.

Already-valid IR is preserved byte-for-byte at the semantic field level. This prevents an incomplete behavior object from causing a correct Boolean condition to be regenerated and potentially corrupted.

At most two compact completion passes are allowed. A second pass is permitted only when the first provenance repair reveals a wholly missing top-level semantic object. The completion call uses a compact bounded output budget because it is a repair, not a second full compilation.

## 7. Evidence semantic annotation

Language-derived evidence is annotated into structured facts. Raw structured timestamped trace facts remain read-only evidence context.

Allowed operators remain bounded by schema. Unknown model words such as `HAS`, `REACHES`, `WAS`, or `CONTAINS` are not interpreted by Python.

### 7.1 Temporal semantics

STATE_SAMPLE, TRANSITION and PERSISTENT_STATE remain distinct. A point state proves only a point. Repeated point samples never become an interval automatically.

For PERSISTENT_STATE to be executable:

```text
scope.resolution == RESOLVED
AND
scope.scope_id is concrete and non-empty
```

When the source explicitly resolves persistence to the complete evaluated case/test interval, semantic annotation may use `CASE_EVALUATED_INTERVAL`. An unresolved phrase such as `throughout the interval` remains unresolved when its referent is not supplied.

## 8. Evidence materiality

Materiality is determined from authoritative structured roles and dependencies, not prose similarity, same-signal overlap, or a loose requirement association alone.

Narrative title/description/reported-result/history ambiguity is not automatically compliance-material. Direct observations explicitly linked to a requirement, explicit current-ticket scope metadata, and material evidence roles remain conservative when unresolved. Same-signal overlap alone never creates materiality.

## 9. Independent semantic verification

The verifier independently reconstructs source semantics into a structured fingerprint before comparing against candidate IR. Candidate compiler IR is untrusted input.

Python compares the verifier fingerprint and compiler IR. A model label of `VERIFIED` cannot override a structural mismatch. The TC17 nested-Boolean regression remains protected.

v0.8.8 additionally requires independent normative-polarity reconstruction. Positive obligations, prohibitions and permissions must be reconstructed from source rather than copied from candidate IR. This remains an LLM semantic contract; Python compares the structured result and does not classify natural-language modality itself.

## 10. Semantic arbitration

At most one material semantic arbitration call is allowed before deterministic compliance. v0.8.8 constructs an issue-scoped exact authoritative source packet so routine unrelated requirements/evidence do not inflate the arbitration prompt.

Arbitration replacement objects must be executable and source-grounded. Every material executable element must itself carry the matching semantic ID and exact source phrase. A separate `source_clauses` list or explanatory notes cannot substitute for provenance on anonymous executable nodes.

A notes-only repair, `OTHER` pseudo-fact, missing signal/value/scope, or malformed Boolean tree cannot clear a material integrity issue.

## 11. Deterministic compliance

Only verified executable semantics reach deterministic compliance. Python owns:

- applicability;
- condition evaluation;
- Boolean logic;
- transitions;
- point/interval evidence mechanics;
- timing math;
- persistence evaluation;
- relationship handling;
- evidence bucket closure;
- SATISFIED / VIOLATED / NOT EVALUABLE / NOT APPLICABLE outcomes.

Missing executable evidence remains conservative rather than guessed.

## 12. RCA routing

A bare requirement violation or output symptom is insufficient to justify deep RCA. Primary RCA synthesis requires positive current-case mechanism evidence. Historical evidence remains supporting context only. Hypothesis provenance may reference either a canonical evidence ID or a VERIFIED semantic fact ID; unknown/unresolved fact IDs remain invalid.

## 13. Frozen invariants

v0.8.8 preserves all previously accepted invariants, including:

- point state only proves point;
- distinct samples are not simultaneous without correlation/aligned timestamp;
- one opposite point cannot prove case-wide non-applicability;
- persistence/scoped absence requires interval evidence or a verified resolved language scope;
- state sample is not a transition;
- applicability and evaluation evidence are separate;
- missing evidence yields UNKNOWN / NOT EVALUABLE;
- historical tickets are non-normative;
- unsupported hypotheses are forbidden;
- assignments remain assignments and transitions require ordered same-signal value change;
- Python final truth;
- no Python arbitrary-language NLP phrase lists;
- simple IF state conditions are applicability, not event triggers;
- arbitrary `throughout interval` prose is not executable without resolved scope;
- transport-valid does not mean executable.

## 14. Acceptance state

RCA Core v0.8.10 is a **candidate**. Automated regressions are necessary but insufficient.

Live acceptance sequence:

1. Deploy the exact v1.8.11 package and rerun the complete regression bundle with the same stable 27B critical-semantic routing used for the v1.8.10 validation run.
2. TC17 must produce REQ-1701 APPLICABLE/VIOLATED, REQ-1702 NOT APPLICABLE, REQ-1703 NOT APPLICABLE, with no unsupported hypotheses.
3. TC12 must meet its documented ten-requirement target, including deterministic REQ-1204 1100 ms vs 800 ms (+300 ms).
4. Routine schema/provenance defects should no longer force arbitration in every case.

Until those live targets pass, v0.4.3 TEST-003 and v0.5.2 TC1–TC3 remain the frozen semantic anchors.


## v0.8.8 confirmed 27B-rerun fixes retained in v0.8.9

v0.8.8 is based on controlled 27B reruns of TEST-006, TEST-012, TEST-017 and TEST-021. Those reruns separated model-capacity failures from deterministic/core integration defects.

### Verified fact reuse is requirement-independent

`related_requirement_ids` is linkage/materiality metadata, not an execution whitelist. A VERIFIED structured fact can satisfy any Requirement IR predicate that matches its signal/value/operator/temporal semantics. This fixes the TEST-017 ServiceMode fact being visible to REQ-1703 but incorrectly hidden from REQ-1701, and the equivalent TEST-021 SeatPosition reuse problem.

### Structural completion is all-target or rejected

For a targeted Requirement IR repair, every requested field must be present in the returned patch. Partial patches that silently omit trigger, timing, source-clause inventory or another requested field are rejected and leave the current IR intact for verifier/arbitration escalation.

### Atomic semantic arbitration

Existing Requirement IRs are no longer replaced wholesale by arbitration. Python computes exact target fields from structured integrity/verifier issues. Arbitration returns field patches; only those fields are merged. Legacy full IR responses remain transport-compatible, but Python copies only the approved target fields. This prevents a repair of condition/timing from degrading a previously correct required behavior.

### Case-level ambiguity is advisory unless structurally materialized

Free-form `unresolved_case_semantics` no longer globally blocks compliance. Blocking authority comes from concrete structured requirement/evidence integrity issues. Deterministic evidence insufficiency remains Python-owned.

### RCA packet source authority and provenance

Canonical evidence class/source determines diagnostic and historical packet classification. The LLM does not need to rediscover an already-known source class via `possible_roles`. Materially unresolved requirements remain visible in the RCA packet as unresolved normative context rather than disappearing. Machine evidence IDs in `supporting_evidence_ids` / `weakening_evidence_ids` are the strict provenance namespace; human-readable `source_references` are display context and cannot invalidate an otherwise grounded hypothesis.

### Frozen evidence invariants remain unchanged

No v0.8.9 change weakens STATE_SAMPLE / TRANSITION / INTERVAL_STATE separation, correlation requirements, persistence scope, applicability/evaluation separation, or Python final authority. No Python natural-language phrase classifier was added.


## v0.8.9 failure-containment and verifier-equivalence delta

The first exact-package v1.8.9 27B suite run established that a field-contract failure inside semantic arbitration could still escape the semantic-repair boundary and terminate a testcase/batch. The same run showed false verifier disagreements when descriptive fields differed even though executable semantics matched.

### Arbitration is a repair, not a liveness dependency

A schema-valid but contract-invalid arbitration response is now rejected atomically. The pre-arbitration verified/partially verified semantics stay unchanged, material issues remain material, and deterministic compliance proceeds conservatively. No second 27B arbitration retry is introduced.

### Field-specific unresolved decisions

For each omitted target field Python derives the governing issue IDs from explicit verifier `target_fields` plus the same structured target mapping used to construct the arbitration request. Omission is allowed only if all governing issue IDs are explicitly present in `unresolved_issue_ids`. This is field-scoped; an unresolved issue for another field cannot authorize omission.

### Verifier semantic fingerprint

Required-behavior equality is limited to executable `(signal, operator, value, event)` semantics. `process_description`, source text, IDs and notes remain auditable but non-semantic for equality.

Persistence scope is compared through a structural normalization of the already-structured scope field rather than arbitrary generated wording. This normalization does not parse original requirement prose and does not alter deterministic evidence scope rules.

### Observability

The arbitration response is recorded as a pipeline attempt before field-contract validation. A rejected response is emitted as `ATTENTION` with the rejection reason and returned structured object, allowing live/session forensics without converting repair failure into an exception.


## v0.8.10 live-full-suite contract delta

The exact v1.8.10 / v0.8.9 RunPod suite completed all 17 cases and achieved 11/17 semantic acceptance. TC12 and TC17 passed cleanly. The six remaining failures were traced to bounded implementation contracts rather than a topology failure. v0.8.10 therefore keeps the same architecture and changes only these interfaces:

1. **Verifier fingerprint completeness:** `resolution=VERIFIED` is admissible only when the independently reconstructed structured identity is complete enough for comparison. Incomplete VERIFIED fingerprints are structured-output failures, not semantic disagreements.
2. **Canonical requirement persistence scope:** requirement persistence uses a dedicated four-value semantic domain. Evidence observation types such as `INTERVAL_STATE` cannot inhabit this field.
3. **Atomic arbitration equivalence:** an untargeted field may be echoed only when structurally identical to the current value; changed untargeted fields remain rejected.
4. **Repair/provenance dependency:** creation of a missing executable semantic field automatically couples the repair to `source_clauses` when the audit role is absent. The LLM still authors the provenance; Python only declares the dependency.
5. **RCA packet structural evidence closure:** canonical direct observations referenced by deterministic results are copied as structured evidence into the compact RCA packet even when they required no language annotation.
6. **Rejected-repair observability:** contract rejection reason is persisted with the raw arbitration attempt.

These changes preserve all frozen evidence invariants, Python final compliance authority, one-call arbitration budget, and conditional RCA synthesis.

### Live status after v1.8.10

- Batch execution: 17/17 completed.
- Semantic acceptance: 11/17 PASS.
- TC12: live-confirmed target.
- TC17: live-confirmed target.
- Failures addressed by v0.8.10: TEST-007, TEST-015, TEST-016, TEST-018, TEST-019, TEST-021.

The next freeze decision depends on the exact v1.8.11 full-suite RunPod result, not automated tests alone.
