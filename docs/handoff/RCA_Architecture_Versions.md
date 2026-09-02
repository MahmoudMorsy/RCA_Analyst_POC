# RCA Architecture Versions

**Current RCA architecture carried by application v1.8.7:** RCA Core v0.8.6 candidate.

## 1. Persistent invariants

Across all generations: preserve raw source/provenance; separate applicability/evaluation evidence; distinguish point/transition/interval; keep deterministic timing/math in Python; keep historical tickets non-normative; require positive mechanism support for hypotheses; keep repairs bounded/revalidated; later LLM stages cannot overwrite Python compliance truth.

## 2. A0 — Early monolithic reasoning (v0.1 → v0.3.6)

27B performed broad semantic reasoning after basic parsing; Python validated/normalized. CanonicalCase, source boundaries, decomposition completeness, evidence buckets and auditable repair were progressively introduced. v0.3.6 remains an early TEST-001 checkpoint.

## 3. A1 — Explicit evidence semantics (v0.4.0 → v0.4.3)

Introduced applicability evidence binding, `STATE_SAMPLE`/`TRANSITION`/`INTERVAL_STATE`, deterministic `TimingFact`, event coverage and strict point-vs-scope semantics.

**Frozen:** v0.4.3 TEST-003, including deterministic 550 ms vs 500 ms violation.

## 4. A2 — Tiered repair/correlation/batch (v0.5.0 → v0.5.5)

Deterministic → fast-model → primary repair routing; snapshot correlation; asymmetric conformance; batch execution; assignment-only transition safeguards; persisted attempt data; Live Pipeline.

**Frozen:** v0.5.2 TC1–TC3.

## 5. A3 — Multi-model intake/review (v0.6.0 → v0.6.5)

Small model handled conditional intake/repair/review; Python retained final authority. Source availability became model-interpreted rather than Python phrase matching. Cooperative cancellation and structured review contracts matured.

## 6. A4 — Mandatory decomposed Phase A/B (v0.7.0 → v0.7.1)

Always-on decomposed 4B stages + mandatory 27B requirement reasoning and RCA synthesis. Live TC12 exposed high cost and interface-contract failures; this topology was retired.

## 7. A5 — Semantic compiler + deterministic compliance (v0.8.0 → v0.8.4)

Requirement IR became the LLM→Python contract; independent verification, targeted structural/evidence completion, conditional one-call semantic arbitration and mechanism-gated RCA were introduced. v0.8.4 separated requirement/evidence semantic calls and hardened scope execution.

Live TC12/TC17 remained pending, so v0.8.4 was never frozen.

## 8. A6 — v0.8.5 semantic verification/routing hardening

Live v1.8.5 Dell/RunPod sessions established three concrete defects:

1. TC17 compiler repeatedly regrouped `A AND (B OR C) AND D` while the independent verifier returned `VERIFIED`.
2. Arbitration could put correct meaning in notes but return compliance-linked facts with `OTHER`/missing executable fields and still claim resolution.
3. Qwen3.5-4B evidence annotation repeatedly emitted invalid enum words even after RunPod context exceeded 8K.

v0.8.5 adds:

### 8.1 Critical Semantic Model Routing

Semantic preparation and semantic verification independently select configured `small` or `primary` capacity. This changes transport/capacity only; Python remains compliance authority.

### 8.2 Structured verifier fingerprint

The verifier reconstructs source semantics independently into structured normative type, Boolean AST, trigger, behavior, timing, persistence and relationships. Python compares fingerprint to candidate IR. Commutative child order may normalize; Boolean regrouping cannot.

A textual `VERIFIED` label is insufficient if structured semantics differ.

### 8.3 Arbitration replacement hardening

Compliance-linked replacement evidence cannot resolve a material issue if it is empty/unresolved, has missing subject/value, uses `operator=OTHER` for executable state meaning, remains `temporal_semantics=OTHER`, or claims persistence without resolved concrete scope.

Notes do not substitute for executable fields.

### 8.4 Evidence enum contract

Evidence prompts enumerate legal schema values. Python does not translate invented words (`HAS`, `REACHES`, `WAS`, `CONTAINS`) into semantics.

## 9. A7 — v0.8.6 live-TC17 transport/completion hardening

The first v1.8.6 live TC17 run with Qwen3.8-27B for semantic preparation/verification and a 32K server context proved the model could reconstruct the central nested Boolean condition correctly, but exposed additional integration/contract defects:

1. Thinking Off did not reach llama.cpp and large `reasoning_content` consumed output budget while telemetry still reported zero reasoning tokens.
2. Requirement behavior shells could carry provenance but omit executable signal/operator/value.
3. Structural completion regenerated full IR and hit the 12K output limit twice instead of repairing only broken fields.
4. Persistent language evidence could be correctly understood yet remain non-executable because scope resolution was missing.
5. Narrative/title/reporting ambiguity was made material too broadly.
6. Arbitration could understand the correct repair but separate source-clause IDs from anonymous executable nodes, causing strict validation rejection.

v0.8.6 adds:

- request-level llama.cpp/Qwen thinking propagation and reasoning-content observability;
- targeted `RequirementStructuralPatchBatch` completion protected against untargeted overwrite;
- stronger required-behavior/negative-predicate/persistence executability contracts;
- structural detection/completion of unresolved persistent scope;
- materiality based on explicit roles and actual Requirement-IR structured dependencies;
- stricter arbitration prompt provenance while retaining the existing Python validator.

No Python NLP heuristics or evidence-rule weakening are introduced.

## 10. Current topology

```text
RAW CASE
→ Python structural ingestion/routing
→ optional utility sectioning
→ Python canonicalization
→ semantic preparation role: Requirement IR compilation + targeted completion
→ semantic preparation role: Evidence annotation + targeted completion
→ semantic verification role: independent structured source fingerprint
→ Python semantic integrity/materiality/fingerprint comparison
→ optional ONE Primary semantic arbitration
→ verified semantics
→ Python deterministic compliance
→ RCA router
→ optional ONE Primary RCA synthesis
→ optional utility reviews
→ Python final consistency
→ deterministic report
```

## 11. Validation status

RCA Core v0.8.6 is a **candidate**, not frozen. Live TC17 and TC12 must pass current expected targets before promotion.

Frozen anchors remain v0.4.3 TEST-003 and v0.5.2 TC1–TC3.
