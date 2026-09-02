# RCA Analyst POC RCA Core v0.8.5 Architecture

## 1. Architecture objective

The v0.8 architecture separates **language understanding**, **deterministic compliance execution**, and **deep root-cause synthesis**.

The governing rule is:

> **LLMs interpret human language into structured semantics. Python executes verified semantics deterministically. The 27B model is an escalation resource, not the routine compliance engine.**

This release replaces the v0.7.x topology in which several always-on 4B stages fed mandatory 27B Phase-A requirement reasoning and mandatory 27B Phase-B RCA synthesis. Live TC12 and TC17 demonstrated that this topology was both too slow and semantically unsafe.

## 2. Authority boundaries

### Original source

The original requirement/evidence text is immutable provenance. Structured representations never replace it in storage.

### 4B semantic preparation and verification

The fast model owns natural-language interpretation. From v0.8.4, Requirement IR compilation and evidence semantic annotation are **always separate components**, even for small cases. In v0.8.5 the critical semantic-preparation and verification roles are capacity-neutral: each can be routed to the configured Small / Utility or Primary model. Requirement sets remain bounded for transport/context safety. The independent verifier now reconstructs source semantics into a structured fingerprint before Python compares it with the compiler IR.

This separation is deliberate: a malformed evidence annotation must not invalidate an otherwise useful Requirement IR response, and a malformed Requirement IR must not require evidence reannotation. Component-specific repair calls are therefore bounded to the failed semantic component.

The fast semantic stages own:

- free-form German, English, or mixed-language requirement wording;
- Boolean conditions, including nested AND/OR/NOT;
- trigger/event semantics;
- required behavior;
- timing constraints;
- persistence semantics;
- exceptions and explicit relationships;
- free-text evidence subject/value/temporal semantics;
- contextual references such as `the interval`, `it`, or `afterwards`.

It does **not** assign compliance verdicts or calculate trace timing.

### Python

Python owns only structured/deterministic operations:

- source IDs and provenance;
- exact structured timestamps;
- structural signal assignments/snapshots;
- transition inference from ordered same-signal value changes;
- semantic-contract integrity checks;
- dependency-based materiality over LLM-produced links;
- Boolean IR execution;
- numeric comparison;
- timing arithmetic;
- state/transition/interval evidence semantics;
- parent/inherited applicability execution;
- evidence bucketing;
- authoritative applicability and compliance verdicts;
- final structural consistency.

Python does **not** interpret arbitrary requirement prose or contextual natural-language references.

### 27B semantic arbitration

The primary model is used at most once per case for semantic arbitration when a material unresolved semantic issue blocks compliance. All such issues are batched into one call.

From v0.8.2, arbitration has a strict replacement contract: any Requirement IR returned by the arbitrator must be a complete executable repair with VERIFIED material source clauses. A mixed-language or nested requirement is not considered ambiguous merely because it is linguistically complex. If the source is genuinely unresolved, the arbitrator leaves the requirement out of the repair list and returns the blocking issue IDs as unresolved instead of returning another prose-only pseudo-IR.

### 27B RCA synthesis

The primary model performs deep RCA only when mechanism-oriented evidence justifies it. A bare requirement violation is not enough.

From v0.8.2, `RCA_CONTEXT` is explicitly non-routing. `DIAGNOSTIC` and `HISTORICAL` semantic labels are cross-checked against their authoritative source classes, and a failed output point-state is treated as a symptom rather than mechanism evidence. Positive current-case mechanism observations use the dedicated `MECHANISM` semantic role.


## 2.1 v0.8.2 live-TC17 hardening

The live TC17 v0.8.0 run revealed a distinct failure mode from TC12: the 4B compiler and the 27B arbitrator could correctly describe the nested requirement logic in source-clause notes while leaving `condition`, `required_behavior`, and related executable fields null. Python correctly refused to execute the result, but the arbitration call therefore consumed primary-model time without repairing the case. The same run also triggered an unnecessary RCA call because contextual/symptom evidence was labelled as RCA context/diagnostic evidence.

v0.8.2 hardens both boundaries:

- semantic compilation must materialize understood meaning into the Requirement IR, not only into prose notes;
- arbitration repair IRs are schema-validated as complete executable replacements;
- genuinely unresolved source meaning remains unresolved rather than being disguised as a repair;
- deep RCA routing requires actual diagnostic/history sources or explicit positive mechanism evidence;
- ticket titles, generic RCA context and output symptoms do not justify a 27B RCA call.

## 2.2 v0.8.3 live-TC12 transport hardening

The live TC12 v0.8.2 run exposed a compiler-transport defect rather than a semantic/timing defect. The 4B returned grounded PREDICATE source phrases and correct operators/values but omitted the explicit `signal` field on several condition nodes. The model calls completed normally, yet the hidden Pydantic cross-field validator rejected the whole batch before semantic verification or arbitration.

v0.8.3 separates two states that were previously conflated:

- **transport-valid IR**: structured model output can be preserved even when a node is incomplete;
- **executable IR**: every node satisfies the deterministic semantic-integrity contract and may be consumed by Python compliance.

Python never fills the missing semantic field from prose. Instead, one bounded targeted 4B structural-completion pass recompiles only requirements with transport defects from their original requirement text. If that cheap pass succeeds, normal semantic verification continues without 27B. If it fails or remains incomplete, the standard verifier/materiality/single-arbitration path handles the defect conservatively.

The 27B arbitration contract remains strict: an arbitration replacement is not accepted unless its Boolean AST is executable, including explicit PREDICATE `signal` and operator fields.

## 2.3 v0.8.4 live-TC17 semantic-transport and scope hardening

The TC17 v0.8.2 live run exposed a second transport-contract problem beyond the Requirement IR defects addressed in v0.8.3. The 4B correctly understood most of the mixed German/English semantics, but the combined small-case response contained malformed evidence annotation objects: `facts` were nested under the annotation `resolution` field, and an annotation-level `scope_id` was emitted even though scope belongs to individual semantic facts. Because requirement and evidence semantics shared one response model, those evidence errors caused the entire semantic-preparation call to be rejected before requirement verification or arbitration could run.

v0.8.4 makes four changes:

- Requirement compilation and evidence annotation are always separate fast-model calls;
- evidence annotations have a narrow transport-canonicalization layer that may relocate already-explicit structured fields but may not infer semantic meaning from prose;
- one targeted evidence-semantic completion call can repair structured evidence defects without recompiling requirements;
- language-derived `PERSISTENT_STATE` evidence is executable as interval evidence only when scope is `RESOLVED` **and** a concrete non-empty `scope_id` is supplied.

The 27B arbitration evidence contract is equally strict: a returned evidence repair must be fully VERIFIED, and persistent evidence must contain a concrete resolved scope. Otherwise the blocking issue remains unresolved.

## 2.4 v0.8.5 live TC17/TC12 semantic-verification hardening

The v1.8.5 Dell/RunPod validation campaign proved that context sizing was not the only blocker. After the RunPod small-model context was increased beyond 8K, Qwen3.5-4B still produced invalid evidence enums and repeatedly mis-grouped the TC17 Boolean condition while its own verifier returned `VERIFIED`. A later 27B arbitration correctly explained several facts in notes but could return non-executable evidence fields.

v0.8.5 therefore adds three bounded contracts:

1. **Critical Semantic Model Routing** — Requirement/evidence preparation and independent verification may each use the Small / Utility or Primary configured model. Model capacity is a deployment/runtime choice; Python authority is unchanged.
2. **Independent structured fingerprint** — the verifier reconstructs normative type, condition AST, trigger, required behavior, timing, persistence and relationships from the original requirement. Python compares this structured reconstruction with the compiler IR. A `VERIFIED` label cannot override a structural mismatch such as `A AND (B OR C) AND D` being regrouped as `A AND (B AND (C OR D))`.
3. **Strict arbitration evidence materialization** — compliance-linked evidence repairs must materialize executable subject/operator/value/temporal semantics and, for persistent state, a resolved concrete scope. Correct prose in notes is insufficient.

Evidence-annotation enum failures remain model/schema failures. Python does not add language mappings for invented operators such as `HAS`, `REACHES`, `WAS`, or `CONTAINS`.


## 3. Production pipeline

```text
RAW CASE
Requirements / ticket / test result / trace / diagnostics / history
                         │
                         ▼
┌─────────────────────────────────────────────────────────┐
│ 1. PYTHON STRUCTURAL INGESTION                          │
│ • sections / IDs / provenance                           │
│ • exact timestamps                                      │
│ • snapshots and structural trace facts                  │
│ • known source boundaries                               │
│ NO natural-language semantic interpretation             │
└─────────────────────────┬───────────────────────────────┘
                          │
                          ▼
┌─────────────────────────────────────────────────────────┐
│ 2. OPTIONAL 4B SOURCE/CONTENT SECTIONING                │
│ Only for genuinely free-form source organization.       │
│ Structured testcase templates skip these calls.         │
└─────────────────────────┬───────────────────────────────┘
                          │
                          ▼
┌─────────────────────────────────────────────────────────┐
│ 3. BOUNDED 4B REQUIREMENT SEMANTIC COMPILATION          │
│ • free-form requirement language -> Requirement IR      │
│ • one bounded batch for small cases; multiple bounded   │
│   batches only when output sizing requires it           │
│ • no evidence annotation in this response contract      │
│ • NO verdicts / NO RCA                                  │
└─────────────────────────┬───────────────────────────────┘
                          │
                          ▼
┌─────────────────────────────────────────────────────────┐
│ 4. CONDITIONAL 4B REQUIREMENT IR COMPLETION             │
│ • only if compiler output is transport-valid but        │
│   structurally non-executable                           │
│ • Python identifies missing structured fields only      │
│ • affected requirements are recompiled from source      │
│ • at most one cheap targeted pass                       │
│ • NO Python language inference / NO 27B                 │
└─────────────────────────┬───────────────────────────────┘
                          │
                          ▼
┌─────────────────────────────────────────────────────────┐
│ 5. 4B EVIDENCE SEMANTIC ANNOTATION                      │
│ • separate component for language-derived evidence      │
│ • resolved / partial / unresolved semantic facts        │
│ • structured trace facts remain Python-owned/read-only  │
│ • persistent evidence needs explicit scope semantics    │
└─────────────────────────┬───────────────────────────────┘
                          │
                          ▼
┌─────────────────────────────────────────────────────────┐
│ 6. CONDITIONAL 4B EVIDENCE SEMANTIC COMPLETION          │
│ • only targeted evidence IDs are reannotated            │
│ • used for structured annotation/scope defects          │
│ • requirement compilation is NOT repeated               │
│ • at most one cheap targeted pass                       │
└─────────────────────────┬───────────────────────────────┘
                          │
                          ▼
┌─────────────────────────────────────────────────────────┐
│ 7. INDEPENDENT 4B REQUIREMENT SEMANTIC VERIFICATION     │
│ • original requirement vs compiled IR                   │
│ • candidate IR is treated as untrusted                  │
│ • detects silent omitted/altered conditions, triggers,  │
│   timing, persistence, exceptions and relationships     │
│ • NO compliance decision                                │
└─────────────────────────┬───────────────────────────────┘
                          │
                          ▼
┌─────────────────────────────────────────────────────────┐
│ 8. PYTHON SEMANTIC INTEGRITY / MATERIALITY              │
│ • requirement-ID coverage                               │
│ • compiler source-clause audit completeness             │
│ • verifier mismatches                                   │
│ • source-span grounding                                 │
│ • semantic_id linkage                                   │
│ • unresolved semantic objects                           │
│ • dependency-based materiality                          │
└─────────────────────────┬───────────────────────────────┘
                          │
                ┌─────────┴─────────┐
                │                   │
             CLEAN             MATERIAL ISSUE
                │                   │
                │                   ▼
                │       ┌────────────────────────────┐
                │       │ 9. ONE 27B SEMANTIC       │
                │       │    ARBITRATION CALL       │
                │       │ • all material issues     │
                │       │ • original source context │
                │       │ • no verdicts / no RCA    │
                │       │ • no repeated 27B retry   │
                │       └────────────┬───────────────┘
                │                    │
                └──────────┬─────────┘
                           ▼
┌─────────────────────────────────────────────────────────┐
│ 10. VERIFIED SEMANTIC REPRESENTATION                    │
│ Original source remains provenance.                     │
│ Only verified/resolved semantic objects are executable. │
└─────────────────────────┬───────────────────────────────┘
                          │
                          ▼
┌─────────────────────────────────────────────────────────┐
│ 11. PYTHON DETERMINISTIC COMPLIANCE ENGINE              │
│ • Boolean AST                                           │
│ • applicability                                         │
│ • state / transition / interval semantics               │
│ • persistence                                           │
│ • timing                                                │
│ • relationships                                         │
│ • evidence buckets                                      │
│                                                         │
│ FINAL REQUIREMENT TRUTH IS PYTHON-OWNED.                 │
└─────────────────────────┬───────────────────────────────┘
                          │
                          ▼
              AUTHORITATIVE COMPLIANCE STATE
                          │
                          ▼
┌─────────────────────────────────────────────────────────┐
│ 12. RCA ROUTER                                          │
│ Deep RCA only when mechanism-oriented evidence exists.  │
└─────────────────────────┬───────────────────────────────┘
                          │
                  ┌───────┴────────┐
                  │                │
                 NO               YES
                  │                │
                  │                ▼
                  │    ┌──────────────────────────────┐
                  │    │ 13. ONE 27B RCA SYNTHESIS    │
                  │    │ Receives compact verified    │
                  │    │ RCA Evidence Packet only.    │
                  │    └─────────────┬────────────────┘
                  │                  │
                  └────────┬─────────┘
                           ▼
┌─────────────────────────────────────────────────────────┐
│ 14. OPTIONAL 4B HYPOTHESIS EPISTEMIC REVIEW             │
│ Hypothesis wording/support only; no compliance changes. │
└─────────────────────────┬───────────────────────────────┘
                          │
                          ▼
┌─────────────────────────────────────────────────────────┐
│ 15. PYTHON FINAL CONSISTENCY GATE                       │
└─────────────────────────┬───────────────────────────────┘
                          │
                          ▼
┌─────────────────────────────────────────────────────────┐
│ 16. OPTIONAL 4B WORDING AUDIT                           │
│ Zero semantic authority.                                │
└─────────────────────────┬───────────────────────────────┘
                          │
                          ▼
                     FINAL REPORT
```

## 4. Requirement Intermediate Representation

A requirement is not reduced to generated Python code. v0.8 uses a declarative **Requirement IR** so it is inspectable, comparable, provenance-aware, and safe to execute.

A state-condition requirement such as:

```text
Wenn IgnitionState = ON und (GearPosition = P oder GearPosition = N)
and ServiceMode is not ACTIVE, StarterEnable shall be TRUE.
```

is represented conceptually as:

```text
CONDITION
└── AND
    ├── IgnitionState EQ ON
    ├── OR
    │   ├── GearPosition EQ P
    │   └── GearPosition EQ N
    └── ServiceMode NEQ ACTIVE

REQUIRED_BEHAVIOR
└── StarterEnable EQ TRUE
```

A timed event requirement such as:

```text
When TailgateRequest becomes OPEN,
TailgateStatus shall become OPEN within 800 ms.
```

is represented as:

```text
TRIGGER
└── TailgateRequest BECOMES OPEN

REQUIRED_BEHAVIOR
└── TailgateStatus BECOMES OPEN

TIMING
└── <= 800 ms AFTER TRIGGER
```

Each material semantic object carries a `semantic_id`, and the compiler returns a source-clause audit inventory mapping those IDs to verbatim requirement spans. Python verifies that material clauses identified by the compiler are represented in the IR. This specifically guards against the TC17 failure where `ServiceMode is not ACTIVE` disappeared from the normalized condition.

## 5. Evidence semantic annotation and contextual scope

Natural-language evidence is not automatically promoted to deterministic interval evidence.

Example:

```text
BatteryVoltage remained 12.2 throughout the complete evaluated interval.
```

The model may verify:

```text
subject      = BatteryVoltage
operator     = EQ
value        = 12.2
temporal     = PERSISTENT_STATE
scope phrase = "throughout the complete evaluated interval"
```

But the scope must remain `UNRESOLVED` or `PARTIAL` if the surrounding context does not establish what interval is meant. Python will not reinterpret the phrase and will not downgrade an unresolved persistent claim into a point sample.

Only a `PERSISTENT_STATE` fact with `scope.resolution=RESOLVED` **and a concrete non-empty `scope_id`** can become executable `INTERVAL_STATE` evidence.

This preserves the distinction between:

- full trace;
- full testcase;
- a named subinterval;
- a before/after-action interval;
- an ambiguous contextual reference.

## 6. Semantic arbitration policy

27B arbitration is **case-level**, not sentence-level.

If five materially ambiguous sentences exist, they are batched into one arbitration call. Non-material ambiguities remain unresolved and do not consume a primary-model call.

After one arbitration call:

- resolved semantics are merged by exact IDs;
- unresolved items remain unresolved;
- no second semantic 27B retry loop is allowed;
- impacted compliance remains conservative (`APPLICABILITY UNKNOWN` / `NOT EVALUABLE`) where necessary.

## 7. Deterministic compliance engine

Once semantics are verified, Python executes them. The LLM is not asked to vote on compliance.

For TC17:

```text
Condition:
  IgnitionState = ON
  GearPosition = N satisfies (P OR N)
  ServiceMode != ACTIVE

Required:
  StarterEnable = TRUE

Observed at correlated snapshot:
  StarterEnable = FALSE
```

Python therefore produces:

```text
APPLICABLE / VIOLATED
```

A model cannot override this result.

For TC12, Python executes the verified timing IR against structural trace transitions:

```text
TailgateRequest -> OPEN at 100.000 s
TailgateStatus  -> OPEN at 101.100 s
elapsed = 1100 ms
limit   = 800 ms
margin  = +300 ms late
=> VIOLATED
```

## 8. Frozen evidence semantics

v0.8 preserves the validated baseline rules:

1. `STATE_SAMPLE`, `TRANSITION`, and `INTERVAL_STATE` remain distinct.
2. A state sample proves only the observed instant/context.
3. Point samples combine only when correlated by snapshot/group or aligned timestamp/clock.
4. One opposite point cannot establish case-wide `NOT APPLICABLE`.
5. Resolved complete interval evidence can establish persistence/case-wide absence within its scope.
6. State samples do not prove transitions.
7. Positive persistence conformance requires interval evidence.
8. A correlated contradiction may prove violation without full persistence coverage.
9. Applicability evidence and evaluation evidence remain separate.
10. Historical tickets are non-normative.
11. Missing evidence remains conservative.
12. RCA hypotheses require positive current-case mechanism support.
13. A blocked compliance proposition is not itself an RCA mechanism.
14. Structural transition inference requires ordered same-signal value change.
15. Repeated same-value samples do not become interval evidence.
16. Response evidence is not retained as evaluation proof when applicability is definitively false.
17. Explicit parent/inherited scope remains visible.
18. Final compliance truth is Python-owned.
19. Python does not use multilingual/NLP phrase lists as the primary semantic solution.
20. `IF state-condition` remains state applicability; Python does not invent a transition trigger.
21. Global event-coverage metadata is not signal-specific applicability evidence.

## 9. RCA routing and RCA Evidence Packet

Deep RCA is triggered by mechanism-oriented evidence, for example:

- diagnostics/BZD/DTC evidence;
- historical precedent requiring current-case comparison;
- semantically identified diagnostic/historical/RCA context;
- future extensions may include structured intermediate/internal signal evidence and component degradation evidence.

A bare `expected X / observed Y` violation does not automatically trigger 27B RCA.

The RCA model receives a compact packet containing:

- authoritative requirement IDs/statuses/evidence IDs/timing facts;
- relevant verified Requirement IRs;
- verified semantic evidence;
- deterministic facts;
- diagnostics/history semantic findings;
- explicitly unresolved RCA context;
- provenance IDs;
- narrowly selected source excerpts only when narrative nuance materially contributes to RCA.

It does **not** normally receive:

- the full raw case;
- original natural-language requirements;
- competing semantic candidates;
- already-resolved raw observations.

This prevents the RCA model from reopening requirement interpretation.

## 10. Model-call budget

Target production call budget:

| Case | 4B | 27B |
|---|---:|---:|
| Routine structured compliance | normally 2–3 semantic calls: Requirement IR compilation + optional evidence annotation + IR verification | 0 |
| Structured semantic defect repaired cheaply | routine calls + at most one targeted requirement/evidence completion for the affected component | 0 |
| Material semantic ambiguity | routine calls (+ optional targeted completion) | 1 arbitration |
| Straightforward semantics + real RCA evidence | routine calls | 1 RCA |
| Hard semantics + real RCA evidence | routine calls (+ optional targeted completion) | 2 maximum normally |

Structured source/content sectioning may add focused 4B calls only when the incoming case organization is genuinely free-form. Requirement batching may add more 4B compilation calls for output sizing, but it never increases the 27B arbitration count.

Regularly exceeding two 27B calls per testcase is treated as an architecture regression.

## 11. v0.7.1 compatibility

The code retains a compatibility-only v0.7.1 execution path for older tests/adapters that instantiate `RCAPipeline` without a semantic-preparation client. The v0.8 GUI and CLI explicitly enable semantic preparation and therefore run the new architecture.

Legacy configuration keys for Phase-A chunking and v0.7 repair remain loadable so existing user configuration files do not break. They are hidden from the v0.8 production GUI because they no longer control the active topology.

## 12. Regression gates introduced in v0.8.0

The release includes exact test fixtures from overnight bundle v1.3 for TC12 and TC17.

Required regression outcomes include:

- decimal timestamps such as `99.900 s` and `100.000 s` are not stripped as numbered-list prefixes;
- natural-language `remained ... throughout ...` is not promoted by the production Python parser into `INTERVAL_STATE`;
- a compiler source-clause omitted from the AST is detected as material;
- TC12 REQ-1204 = `APPLICABLE / VIOLATED`, `1100 ms vs 800 ms`, `+300 ms`;
- TC12 REQ-1202/1206 = `NOT APPLICABLE`;
- TC12 REQ-1207 = `APPLICABLE / SATISFIED`;
- TC17 REQ-1701 = `APPLICABLE / VIOLATED`;
- TC17 REQ-1702/1703 = `NOT APPLICABLE`;
- clean TC17 structured routing performs separate Requirement IR compilation, evidence annotation, and IR verification with zero 27B calls;
- a TC17-style dropped semantic clause triggers exactly one batched 27B arbitration call;
- RCA-worthy context triggers one RCA call without reopening compliance;
- the RCA packet does not contain original requirement wording by default;
- TC17-style evidence annotations with `facts` nested under `resolution` are transport-normalized without language inference;
- a non-empty annotation-level `scope_id` is never silently assigned to a fact;
- `PERSISTENT_STATE` with `scope.resolution=RESOLVED` but empty `scope_id` is non-executable and eligible for targeted evidence completion;
- requirement/evidence semantic calls remain separated even for small cases.
