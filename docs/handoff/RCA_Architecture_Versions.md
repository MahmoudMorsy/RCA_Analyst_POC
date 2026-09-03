# RCA Architecture Versions

**Current RCA architecture carried by application v1.8.9:** RCA Core v0.8.8 candidate.

## 1. Persistent invariants

Original source is immutable provenance. LLMs interpret language into structured semantics. Python owns deterministic structural executability, evidence mechanics, timing, applicability/compliance and final consistency. Model capacity never transfers compliance authority away from Python.

## 2. A0 — Early monolithic reasoning (v0.1 → v0.3.6)

Large-model case reasoning with progressively stronger deterministic parsing/validation. v0.3.6 TEST-001 remains an early validated checkpoint.

## 3. A1 — Explicit evidence semantics (v0.4.0 → v0.4.3)

Introduced explicit state/transition/interval semantics and deterministic timing. v0.4.3 TEST-003 is frozen: 550 ms vs 500 ms VIOLATED, REQ-202 NOT APPLICABLE from INTERVAL_STATE evidence, no unsupported hypotheses.

## 4. A2 — Tiered repair/correlation/batch (v0.5.0 → v0.5.5)

Added deterministic repair first, small-model targeted repair second, primary model only when necessary; strengthened evidence correlation and sequential batch validation. v0.5.2 TC1–TC3 are frozen anchors.

## 5. A3 — Multi-model intake/review (v0.6.0 → v0.6.5)

Introduced small-model intake/review and provider behavior controls. Thinking-heavy small-model review was rejected when it consumed output budget without usable structured output.

## 6. A4 — Mandatory decomposed Phase A/B (v0.7.0 → v0.7.1)

Explored decomposed primary-model architecture. Live TC12/TC17 showed unacceptable cost and semantic reliability, motivating v0.8.

## 7. A5 — Semantic compiler + deterministic compliance (v0.8.0 → v0.8.4)

Current governing architecture established:

- bounded Requirement IR compiler;
- language evidence semantic annotation;
- Python semantic integrity/materiality;
- conditional semantic arbitration;
- Python deterministic compliance;
- RCA routing and conditional synthesis.

v0.8.4 preserved split requirement/evidence calls and strict persistent-scope executability, but live Dell/RunPod validation showed it could not be frozen.

## 8. A6 — v0.8.5 semantic verification/routing hardening

- Critical Semantic Model Routing allows semantic preparation and verification to use Small / Utility or Primary independently.
- Independent verifier reconstructs source semantics into a structured fingerprint.
- Python compares verifier fingerprint against compiler IR; a `VERIFIED` label cannot hide Boolean regrouping.
- Notes-only/`OTHER` arbitration evidence pseudo-repairs are rejected.
- Illegal evidence operators are not mapped by Python.

## 9. A7 — v0.8.6 live-TC17 transport/completion hardening

- explicit llama.cpp/Qwen Thinking Off/On propagation;
- reasoning-content presence telemetry;
- targeted RequirementStructuralPatch completion instead of full-IR regeneration;
- bounded completion budgets;
- explicit persistent-scope executability;
- stricter executable-node arbitration provenance.

This solved the dominant reasoning/token explosion and made a complete live regression practical.

## 10. A8 — v0.8.7 full-suite semantic-contract hardening

The complete v1.8.7 RunPod suite exposed additional systemic failures. v0.8.7 added:

### 10.1 Compiler batch completeness

Every batch has authoritative expected Requirement IDs. Missing IDs receive one bounded semantic recovery call for missing requirements only. Python never invents a missing Requirement IR.

### 10.2 Provenance-aware targeted completion

`source_clauses` is a first-class structural repair target. Condition predicates, trigger, required behavior, timing and persistence require semantic-ID/source-clause linkage. At most two compact completion passes are allowed; the second is only for a top-level semantic object exposed by pass-1 provenance repair.

### 10.3 Independent normative polarity

Verifier reconstructs normative type from source independently. Positive obligation, prohibition and permission semantics are model-semantic output, then compared structurally by Python. No modality phrase list is implemented in Python.

### 10.4 Source grounding

Grounding tolerates formatting-only bullet/line/punctuation differences. Explicit ellipsis can omit source text only when retained segments occur in source order. Invented words remain ungrounded.

### 10.5 Evidence materiality

Same-signal overlap and loose narrative requirement association alone are insufficient. Unresolved evidence blocks compliance only through authoritative structured dependencies/material roles. Direct evidence and explicit scope metadata remain conservative.

### 10.6 Issue-scoped arbitration

At most one Primary arbitration call remains. Its deterministic source packet contains exact authoritative requirement/evidence fields implicated by material issues, reducing unrelated prompt growth without weakening replacement validation.

### 10.7 RCA provenance

Final hypothesis validation accepts canonical evidence IDs and VERIFIED semantic fact IDs. Unknown/unresolved fact IDs are rejected.

### 10.8 Regression acceptance

A final semantic-integrity ERROR makes semantic acceptance FAIL even if conservative requirement verdicts happen to match an expected manifest.

## 11. Current topology

```text
RAW CASE
→ structural ingestion / intake routing
→ canonicalization
→ bounded Requirement compiler
→ expected-ID completeness check + one missing-ID recovery [conditional]
→ targeted structural completion pass 1 [conditional]
→ targeted structural completion pass 2 [strictly conditional]
→ evidence annotation + targeted evidence completion
→ independent semantic verification
→ Python fingerprint/integrity/materiality
→ optional one issue-scoped Primary arbitration
→ verified semantics
→ Python deterministic compliance
→ RCA router
→ optional Primary RCA synthesis
→ optional utility reviews
→ Python final gate/report
```

## 12. Frozen evidence rules

Do not weaken state/transition/interval distinctions, point-vs-scope semantics, correlation requirements, event coverage, persistence scope, applicability/evaluation separation, missing-evidence conservatism, historical non-normativity, hypothesis support requirements, raw assignment semantics, same-signal materiality prohibition, Python final authority or the prohibition on Python arbitrary-language NLP heuristics.

## 13. Validation status

RCA Core v0.8.8 is a **candidate**, not frozen.

Deploy the exact v1.8.9 package and rerun the complete regression bundle with stable model settings. TC17 and TC12 remain explicit semantic anchors. Freeze only after live full-suite acceptance and frozen-anchor regression confirmation.


## A9 — v0.8.8 deterministic integration hardening

Controlled 27B reruns isolated deterministic/integration failures after semantic interpretation became correct. v0.8.8 removes requirement-ID execution whitelisting on verified facts, enforces all-target completion, field-atomic arbitration, advisory free-text case ambiguity, canonical RCA source classification, unresolved requirement context and machine-ID hypothesis provenance.
