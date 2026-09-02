# 1. Affected Functionality

Function X activation (FunctionStatus transition to ACTIVE upon FunctionRequest becoming ACTIVE)

# 2. Relevant Requirements

**REQ-001**
If IgnitionState is ON and AvailabilityStatus is AVAILABLE, FunctionRequest may be accepted.

Faithful meaning: Under the joint condition that IgnitionState is ON and AvailabilityStatus is AVAILABLE, the system is permitted (but not obligated) to accept a FunctionRequest.

Relevance: This permissive requirement defines the permission context under which a FunctionRequest may be accepted when the ignition and availability preconditions hold, framing the activation scenario in which the reported non-activation occurred.

**REQ-002**
When FunctionRequest becomes ACTIVE, FunctionStatus shall become ACTIVE within 500 ms.

Faithful meaning: Upon the transition event of FunctionRequest becoming ACTIVE, the system is obligated to transition FunctionStatus to ACTIVE, and that transition must occur within 500 ms of the trigger.

Relevance: This mandatory timed-response requirement directly names the response (FunctionStatus becoming ACTIVE) whose absence is reported in the current case; the 500 ms timing constraint remains unevaluable because no trigger timestamp or event-coverage metadata is supplied.

**REQ-003**
If AvailabilityStatus is NOT_AVAILABLE, FunctionStatus shall remain INACTIVE.

Faithful meaning: Under the condition that AvailabilityStatus is NOT_AVAILABLE, the system is obligated to keep FunctionStatus in the INACTIVE state for the duration of that condition.

Relevance: This requirement governs a different precondition (AvailabilityStatus NOT_AVAILABLE) and a different expected state (INACTIVE persistence); it is relevant as a boundary condition to confirm that the reported non-activation is not a compliant response to a NOT_AVAILABLE status rather than a violation of the activation requirement.

# 3. Expected System Behavior

- **REQ-001:** If IgnitionState is ON and AvailabilityStatus is AVAILABLE, FunctionRequest may be accepted.
- **REQ-002:** When FunctionRequest becomes ACTIVE, FunctionStatus shall become ACTIVE within 500 ms.
- **REQ-003:** If AvailabilityStatus is NOT_AVAILABLE, FunctionStatus shall remain INACTIVE.

# 4. Relevant Historical Tickets

No historical tickets were supplied for comparison.

# 5. Diagnostic Evidence

No diagnostic or BZD evidence was supplied.

# 6. Confirmed Findings

- Reported observation — FunctionStatus did not become ACTIVE. Source: Reported Test Result.

# 7. Requirement Evaluation

| Requirement ID | Normative Type | Applicability | Evaluation Status | Applicability Evidence | Evaluation Evidence | Missing Evidence |
|---|---|---|---|---|---|---|
| REQ-001 | PERMISSIVE | APPLICABILITY UNKNOWN | NO COMPLIANCE VERDICT | None observed. | None observed. | Applicability: Current-case observation confirming that IgnitionState was ON and AvailabilityStatus was AVAILABLE at the relevant point in time. Evaluation: None additionally required for a compliance verdict (permissive requirement) |
| REQ-002 | MANDATORY | APPLICABILITY UNKNOWN | NOT EVALUABLE | None observed. | FunctionStatus did not become ACTIVE. (Source: Reported Test Result) | Applicability: A TRANSITION observation (or equivalent current-case observation) confirming that FunctionRequest actually transitioned to ACTIVE during the evaluated scope, with a timestamp. Evaluation: Timestamped observation establishing the trigger occurrence: FunctionRequest becomes ACTIVE (transition event); Timestamped observation of the required response/state ("FunctionStatus shall become ACTIVE") with coverage spanning the full timing window (within 500 ms of the trigger); Alignable/common timebase between trigger and response observations if they originate from different clocks/sources |
| REQ-003 | MANDATORY | APPLICABILITY UNKNOWN | NOT EVALUABLE | None observed. | None observed. | Applicability: Current-case observation (direct observation, reported observation, or scope metadata) establishing whether AvailabilityStatus was NOT_AVAILABLE during the evaluated scope. Evaluation: Sustained observation of the required response/state ("FunctionStatus shall remain INACTIVE") throughout the applicable interval (AvailabilityStatus is NOT_AVAILABLE), sufficient to assess persistence; a single instant is insufficient |

# 8. Evidence-Backed Hypotheses

No evidence-backed failure hypothesis can currently be established.
# 9. Missing Information

**REQ-001**
- **Applicability Evidence:** Current-case observation confirming that IgnitionState was ON and AvailabilityStatus was AVAILABLE at the relevant point in time
- **Evaluation Evidence:** None additionally required for a compliance verdict (permissive requirement).

**REQ-002**
- **Applicability Evidence:** A TRANSITION observation (or equivalent current-case observation) confirming that FunctionRequest actually transitioned to ACTIVE during the evaluated scope, with a timestamp
- **Evaluation Evidence:** Timestamped observation establishing the trigger occurrence: FunctionRequest becomes ACTIVE (transition event); Timestamped observation of the required response/state ("FunctionStatus shall become ACTIVE") with coverage spanning the full timing window (within 500 ms of the trigger); Alignable/common timebase between trigger and response observations if they originate from different clocks/sources

**REQ-003**
- **Applicability Evidence:** Current-case observation (direct observation, reported observation, or scope metadata) establishing whether AvailabilityStatus was NOT_AVAILABLE during the evaluated scope
- **Evaluation Evidence:** Sustained observation of the required response/state ("FunctionStatus shall remain INACTIVE") throughout the applicable interval (AvailabilityStatus is NOT_AVAILABLE), sufficient to assess persistence; a single instant is insufficient

# 10. Minimum Next Evidence Required

**Compliance Evidence**

- REQ-002 — Applicability: Observe whether FunctionRequest becomes ACTIVE, with timestamp.
- REQ-002 — Evaluation (if applicable): Observe the response/state defined by the requirement ("FunctionStatus shall become ACTIVE") with timestamps and coverage sufficient to evaluate the timing constraint (within 500 ms of the trigger).
- REQ-002 — Timing (if applicable): If trigger and response come from different clocks/sources, provide an alignable timebase.
- REQ-003 — Applicability: Observe the runtime condition (AvailabilityStatus is NOT_AVAILABLE).
- REQ-003 — Persistence (if applicable): Observe the response/state defined by the requirement ("FunctionStatus shall remain INACTIVE") throughout the applicable interval (AvailabilityStatus is NOT_AVAILABLE), with a sufficient observation interval to assess persistence.

# 11. Overall Assessment

**Established:**
- FunctionStatus did not become ACTIVE.
**Requirement status:** REQ-001: NO COMPLIANCE VERDICT (APPLICABILITY UNKNOWN); REQ-002: NOT EVALUABLE (APPLICABILITY UNKNOWN); REQ-003: NOT EVALUABLE (APPLICABILITY UNKNOWN).
**Supported hypotheses:** None.
**Minimum evidence needed next:** REQ-002 — Applicability: Observe whether FunctionRequest becomes ACTIVE, with timestamp; REQ-002 — Evaluation (if applicable): Observe the response/state defined by the requirement ("FunctionStatus shall become ACTIVE") with timestamps and coverage sufficient to evaluate the timing constraint (within 500 ms of the trigger); REQ-002 — Timing (if applicable): If trigger and response come from different clocks/sources, provide an alignable timebase; REQ-003 — Applicability: Observe the runtime condition (AvailabilityStatus is NOT_AVAILABLE); REQ-003 — Persistence (if applicable): Observe the response/state defined by the requirement ("FunctionStatus shall remain INACTIVE") throughout the applicable interval (AvailabilityStatus is NOT_AVAILABLE), with a sufficient observation interval to assess persistence.
