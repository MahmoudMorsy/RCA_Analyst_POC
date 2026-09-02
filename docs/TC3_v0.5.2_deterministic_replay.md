# 1. Affected Functionality

Function activation response timing (FunctionStatus transition to ACTIVE after FunctionRequest becomes ACTIVE)

# 2. Relevant Requirements

**REQ-201**
When FunctionRequest becomes ACTIVE, FunctionStatus shall become ACTIVE within 500 ms.

Faithful meaning: Upon the transition event of FunctionRequest to ACTIVE, the system is obligated to cause FunctionStatus to transition to ACTIVE no later than 500 ms after that trigger event.

Relevance: The ticket reports that FunctionStatus activation is delayed relative to the specified 500 ms response time, and the direct trace shows the FunctionRequest-to-ACTIVE trigger and the subsequent FunctionStatus-to-ACTIVE transition, making this the primary timed obligation under evaluation.

**REQ-202**
If AvailabilityStatus is NOT_AVAILABLE, FunctionStatus shall remain INACTIVE.

Faithful meaning: During any interval in which AvailabilityStatus holds the value NOT_AVAILABLE, FunctionStatus is obligated to persist in the INACTIVE state throughout that interval.

Relevance: This requirement governs a different precondition (AvailabilityStatus = NOT_AVAILABLE) than the one present in the case; it is evaluated to confirm it does not apply and therefore does not constrain the observed activation behavior.

# 3. Expected System Behavior

- **REQ-201:** When FunctionRequest becomes ACTIVE, FunctionStatus shall become ACTIVE within 500 ms.
- **REQ-202:** If AvailabilityStatus is NOT_AVAILABLE, FunctionStatus shall remain INACTIVE.

# 4. Relevant Historical Tickets

No historical tickets were supplied for comparison.

# 5. Diagnostic Evidence

No diagnostic or BZD evidence was supplied.

# 6. Confirmed Findings

- Reported observation — FunctionStatus became ACTIVE later than expected. Source: Reported Test Result.
- Direct observation — 10.000 s IgnitionState = ON Source: Direct Observations / Trace, 10.000 s.
- Direct observation — AvailabilityStatus remained AVAILABLE throughout the complete evaluated interval. Source: Direct Observations / Trace.
- Direct observation — 10.100 s FunctionRequest transitioned to ACTIVE Source: Direct Observations / Trace, 10.100 s.
- Direct observation — 10.100 s FunctionStatus = INACTIVE Source: Direct Observations / Trace, 10.100 s.
- Direct observation — 10.300 s FunctionStatus = INACTIVE Source: Direct Observations / Trace, 10.300 s.
- Direct observation — 10.500 s FunctionStatus = INACTIVE Source: Direct Observations / Trace, 10.500 s.
- Direct observation — 10.650 s FunctionStatus transitioned to ACTIVE Source: Direct Observations / Trace, 10.650 s.

# 7. Requirement Evaluation

| Requirement ID | Normative Type | Applicability | Evaluation Status | Applicability Evidence | Evaluation Evidence | Missing Evidence |
|---|---|---|---|---|---|---|
| REQ-201 | MANDATORY | APPLICABLE | VIOLATED | 10.100 s FunctionRequest transitioned to ACTIVE (Source: Direct Observations / Trace [10.100 s]) | 10.100 s FunctionStatus = INACTIVE (Source: Direct Observations / Trace [10.100 s]); 10.300 s FunctionStatus = INACTIVE (Source: Direct Observations / Trace [10.300 s]); 10.500 s FunctionStatus = INACTIVE (Source: Direct Observations / Trace [10.500 s]); 10.650 s FunctionStatus transitioned to ACTIVE (Source: Direct Observations / Trace [10.650 s]); FunctionStatus became ACTIVE later than expected. (Source: Reported Test Result); Deterministic timing: 550 ms observed vs 500 ms allowed (exceeds limit; 50 ms beyond the limit), clock TRACE_A | Applicability: None additionally required. Evaluation: None additionally required |
| REQ-202 | MANDATORY | NOT APPLICABLE | NO COMPLIANCE VERDICT | AvailabilityStatus remained AVAILABLE throughout the complete evaluated interval. (Source: Direct Observations / Trace) | None observed. | Applicability: None additionally required; resolved as NOT APPLICABLE. Evaluation: Not required for this case. |

# 8. Evidence-Backed Hypotheses

No evidence-backed failure hypothesis can currently be established.
# 9. Missing Information

**REQ-201**
- **Applicability Evidence:** None additionally required.
- **Evaluation Evidence:** None additionally required.

**REQ-202**
- **Applicability Evidence:** None additionally required; applicability is resolved as NOT APPLICABLE by supplied current-case evidence.
- **Evaluation Evidence:** Not required because the requirement is not applicable in the current case.

# 10. Minimum Next Evidence Required

**Compliance Evidence**

No additional compliance evidence is currently selected as a minimum next step.

# 11. Overall Assessment

**Established:**
- FunctionStatus became ACTIVE later than expected.
- 10.000 s IgnitionState = ON
- AvailabilityStatus remained AVAILABLE throughout the complete evaluated interval.
- 10.100 s FunctionRequest transitioned to ACTIVE
- 10.100 s FunctionStatus = INACTIVE
- 10.300 s FunctionStatus = INACTIVE
- 10.500 s FunctionStatus = INACTIVE
- 10.650 s FunctionStatus transitioned to ACTIVE
**Requirement status:** REQ-201: VIOLATED (APPLICABLE); REQ-202: NO COMPLIANCE VERDICT (NOT APPLICABLE).
**Deterministic timing:** REQ-201: 550 ms observed vs 500 ms allowed (exceeds limit; 50 ms beyond the limit), clock TRACE_A.
**Supported hypotheses:** None.
**Minimum evidence needed next:** No additional compliance evidence is currently selected.
