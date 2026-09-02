from rca_app.models import (
    Applicability,
    CanonicalCase,
    EvidenceClass,
    EvidenceItem,
    EvidenceNeed,
    EvaluationStatus,
    NormativeType,
    RequirementAnalysis,
    RequirementElementType,
    RequirementSource,
    SemanticAnalysis,
    Sufficiency,
)
from rca_app.validator import DeterministicValidator


def make_test001():
    return SemanticAnalysis(
        affected_functionality="Function X",
        evidence_inventory=[
            EvidenceItem(
                id="E1",
                evidence_class=EvidenceClass.REPORTED_OBSERVATION,
                text="FunctionStatus did not become ACTIVE.",
                source="Reported Test Result",
            ),
            EvidenceItem(
                id="E2",
                evidence_class=EvidenceClass.TEST_INSTRUCTION,
                text="Set FunctionRequest to ACTIVE.",
                source="Test Step 3",
            ),
        ],
        requirements=[
            RequirementAnalysis(
                requirement_id="REQ-001",
                requirement_text="If IgnitionState is ON and AvailabilityStatus is AVAILABLE, FunctionRequest may be accepted.",
                faithful_meaning="When those stated conditions hold, FunctionRequest may be accepted; no obligation to accept exists and the requirement is silent about other conditions.",
                relevance="It defines a permitted behavior involving FunctionRequest.",
                normative_type=NormativeType.PERMISSIVE,
                applicability=Applicability.UNKNOWN,
                applicability_evidence_ids=[],
                applicability_condition="IgnitionState is ON and AvailabilityStatus is AVAILABLE",
                required_behavior="FunctionRequest may be accepted",
                missing_applicability_evidence=[
                    EvidenceNeed(element=RequirementElementType.APPLICABILITY, description="IgnitionState runtime value"),
                    EvidenceNeed(element=RequirementElementType.APPLICABILITY, description="AvailabilityStatus runtime value"),
                ],
            ),
            RequirementAnalysis(
                requirement_id="REQ-002",
                requirement_text="When FunctionRequest becomes ACTIVE, FunctionStatus shall become ACTIVE within 500 ms.",
                faithful_meaning="When FunctionRequest becomes ACTIVE, FunctionStatus is required to become ACTIVE within 500 ms.",
                relevance="It defines the required FunctionStatus response and timing after its own trigger.",
                normative_type=NormativeType.MANDATORY,
                applicability=Applicability.UNKNOWN,
                applicability_evidence_ids=[],
                trigger="FunctionRequest becomes ACTIVE",
                required_behavior="FunctionStatus shall become ACTIVE",
                timing_constraint="within 500 ms",
                evaluation_evidence_ids=["E1"],
                evaluation_sufficiency=Sufficiency.INSUFFICIENT,
                missing_applicability_evidence=[
                    EvidenceNeed(element=RequirementElementType.TRIGGER, description="Observed FunctionRequest transition to ACTIVE")
                ],
                missing_evaluation_evidence=[
                    EvidenceNeed(element=RequirementElementType.TRIGGER, description="Timestamp of the FunctionRequest transition to ACTIVE"),
                    EvidenceNeed(element=RequirementElementType.RESPONSE, description="FunctionStatus values with timestamps over the 500 ms window"),
                    EvidenceNeed(element=RequirementElementType.TIMING, description="Complete coverage of the 500 ms window"),
                ],
            ),
            RequirementAnalysis(
                requirement_id="REQ-003",
                requirement_text="If AvailabilityStatus is NOT_AVAILABLE, FunctionStatus shall remain INACTIVE.",
                faithful_meaning="When AvailabilityStatus is NOT_AVAILABLE, FunctionStatus is required to remain INACTIVE.",
                relevance="It defines the required FunctionStatus persistence behavior under its own applicability condition.",
                normative_type=NormativeType.MANDATORY,
                applicability=Applicability.UNKNOWN,
                applicability_evidence_ids=[],
                applicability_condition="AvailabilityStatus is NOT_AVAILABLE",
                required_behavior="FunctionStatus shall remain INACTIVE",
                observation_interval_requirement="sufficient interval while the NOT_AVAILABLE condition applies",
                evaluation_sufficiency=Sufficiency.INSUFFICIENT,
                missing_applicability_evidence=[
                    EvidenceNeed(element=RequirementElementType.APPLICABILITY, description="AvailabilityStatus runtime value")
                ],
                missing_evaluation_evidence=[
                    EvidenceNeed(element=RequirementElementType.OBSERVATION_INTERVAL, description="FunctionStatus values over a sufficient observation interval")
                ],
            ),
        ],
    )


def make_canonical():
    data = make_test001()
    return CanonicalCase(
        ticket_id="TEST-001",
        title="Function does not activate.",
        description="The user activates Function X, but the function remains inactive.",
        evidence_inventory=data.evidence_inventory,
        requirements=[RequirementSource(requirement_id=r.requirement_id, requirement_text=r.requirement_text) for r in data.requirements],
    )


def test_test001_expected_statuses_and_minimum_evidence():
    validated = DeterministicValidator().normalize_and_validate(make_test001(), canonical_case=make_canonical())
    errors = [x for x in validated.issues if x.severity.value == "ERROR"]
    assert not errors, errors
    statuses = {x.analysis.requirement_id: x.evaluation_status.value for x in validated.requirement_results}
    assert statuses == {
        "REQ-001": "NO COMPLIANCE VERDICT",
        "REQ-002": "NOT EVALUABLE",
        "REQ-003": "NOT EVALUABLE",
    }
    minimum = "\n".join(validated.compliance_evidence)
    assert "IgnitionState" not in minimum
    assert "FunctionRequest" in minimum
    assert "FunctionStatus" in minimum
    assert "AvailabilityStatus" in minimum
    assert "500 ms" in minimum
    assert "sufficient observation interval" in minimum


def test_test_instruction_cannot_establish_applicability():
    data = make_test001()
    req = data.requirements[1]
    req.applicability = Applicability.APPLICABLE
    req.applicability_evidence_ids = ["E2"]
    validated = DeterministicValidator().normalize_and_validate(data)
    req2 = next(x.analysis for x in validated.requirement_results if x.analysis.requirement_id == "REQ-002")
    assert req2.applicability == Applicability.UNKNOWN
    assert not req2.applicability_evidence_ids


def test_permissive_only_if_is_critical_error():
    data = make_test001()
    data.requirements[0].faithful_meaning = "FunctionRequest may be accepted only if IgnitionState is ON."
    validated = DeterministicValidator().normalize_and_validate(data)
    codes = {x.code for x in validated.issues if x.severity.value == "ERROR"}
    assert "PERMISSIVE_CONVERSE_RISK" in codes


def test_v01_empty_decomposition_is_rejected():
    data = make_test001()
    req2 = data.requirements[1]
    req2.trigger = ""
    req2.required_behavior = ""
    req2.timing_constraint = ""
    req2.observation_interval_requirement = ""
    req2.evaluation_evidence_ids = []
    req3 = data.requirements[2]
    req3.applicability_condition = ""
    req3.required_behavior = ""
    req3.observation_interval_requirement = ""
    validated = DeterministicValidator().normalize_and_validate(data)
    codes = {x.code for x in validated.issues if x.severity.value == "ERROR"}
    assert "MISSING_TRIGGER_DECOMPOSITION" in codes
    assert "MISSING_REQUIRED_BEHAVIOR" in codes
    assert "MISSING_TIMING_DECOMPOSITION" in codes
    assert "MISSING_APPLICABILITY_CONDITION" in codes
    assert "MISSING_PERSISTENCE_DECOMPOSITION" in codes


def test_relevant_reported_observation_is_auto_mapped_without_repair():
    data = make_test001()
    data.requirements[1].evaluation_evidence_ids = []
    validated = DeterministicValidator().normalize_and_validate(data)
    req2 = next(x.analysis for x in validated.requirement_results if x.analysis.requirement_id == "REQ-002")
    errors = [x for x in validated.issues if x.severity.value == "ERROR"]
    assert not any(x.code == "RELEVANT_OBSERVATION_NOT_MAPPED" for x in errors), errors
    assert "E1" in req2.evaluation_evidence_ids
    assert any(x.code == "RELEVANT_OBSERVATION_AUTO_MAPPED" for x in validated.issues)


def test_condition_cannot_be_duplicated_as_nonexistent_evaluation_trigger():
    data = make_test001()
    data.requirements[2].missing_evaluation_evidence.insert(
        0, EvidenceNeed(element=RequirementElementType.TRIGGER, description="AvailabilityStatus was NOT_AVAILABLE")
    )
    validated = DeterministicValidator().normalize_and_validate(data)
    codes = {x.code for x in validated.issues if x.severity.value == "ERROR"}
    assert "NONEXISTENT_TRIGGER_IN_EVALUATION_BUCKET" in codes


def test_condition_applicability_need_mislabeled_trigger_is_corrected():
    data = make_test001()
    req = data.requirements[2]
    req.missing_applicability_evidence = [
        EvidenceNeed(element=RequirementElementType.TRIGGER, description="AvailabilityStatus was NOT_AVAILABLE")
    ]
    validated = DeterministicValidator().normalize_and_validate(data)
    req2 = next(x.analysis for x in validated.requirement_results if x.analysis.requirement_id == "REQ-003")
    errors = [x for x in validated.issues if x.severity.value == "ERROR"]
    assert not any(x.code == "MISSING_CONDITION_APPLICABILITY_NEED" for x in errors), errors
    assert req2.missing_applicability_evidence[0].element == RequirementElementType.APPLICABILITY
    assert any(x.code == "CONDITION_NEED_TYPE_CORRECTED" for x in validated.issues)


def test_missing_condition_applicability_need_is_derived():
    data = make_test001()
    req = data.requirements[2]
    req.missing_applicability_evidence = []
    validated = DeterministicValidator().normalize_and_validate(data)
    req2 = next(x.analysis for x in validated.requirement_results if x.analysis.requirement_id == "REQ-003")
    errors = [x for x in validated.issues if x.severity.value == "ERROR"]
    assert not any(x.code == "MISSING_CONDITION_APPLICABILITY_NEED" for x in errors), errors
    assert any(n.element == RequirementElementType.APPLICABILITY for n in req2.missing_applicability_evidence)
    assert any("AvailabilityStatus" in n.description for n in req2.missing_applicability_evidence)
    assert any(x.code == "CONDITION_APPLICABILITY_NEED_DERIVED" for x in validated.issues)


def test_missing_trigger_applicability_need_is_derived():
    data = make_test001()
    req = data.requirements[1]
    req.missing_applicability_evidence = []
    validated = DeterministicValidator().normalize_and_validate(data)
    req2 = next(x.analysis for x in validated.requirement_results if x.analysis.requirement_id == "REQ-002")
    errors = [x for x in validated.issues if x.severity.value == "ERROR"]
    assert not any(x.code == "MISSING_TRIGGER_APPLICABILITY_NEED" for x in errors), errors
    assert any(n.element == RequirementElementType.TRIGGER for n in req2.missing_applicability_evidence)
    assert any("FunctionRequest" in n.description for n in req2.missing_applicability_evidence)
    assert any(x.code == "TRIGGER_APPLICABILITY_NEED_DERIVED" for x in validated.issues)


def test_v03_normalizes_permissive_applicability_labels_and_removes_spurious_case_validity():
    from rca_app.models import CaseValidityNeed
    data = make_test001()
    data.requirements[0].relevance = "PERIPHERAL"
    data.requirements[0].missing_applicability_evidence = [
        EvidenceNeed(element=RequirementElementType.RESPONSE, description="IgnitionState runtime value"),
        EvidenceNeed(element=RequirementElementType.RESPONSE, description="AvailabilityStatus runtime value"),
    ]
    data.case_validity_needs = [
        CaseValidityNeed(ticket_assertion="The user activates Function X", evidence_needed="Independent trace confirmation")
    ]
    validated = DeterministicValidator().normalize_and_validate(data, canonical_case=make_canonical())
    req1 = next(x.analysis for x in validated.requirement_results if x.analysis.requirement_id == "REQ-001")
    assert all(n.element == RequirementElementType.APPLICABILITY for n in req1.missing_applicability_evidence)
    assert req1.relevance != "PERIPHERAL"
    assert validated.case_validity_evidence == []
    assert validated.semantic.case_validity_needs == []
    assert any(x.code == "CASE_VALIDITY_NEEDS_REMOVED" for x in validated.issues)


def test_v03_minimum_evidence_deduplicates_trigger_timestamp():
    validated = DeterministicValidator().normalize_and_validate(make_test001(), canonical_case=make_canonical())
    req2_items = [x for x in validated.compliance_evidence if x.startswith("REQ-002")]
    assert len([x for x in req2_items if "Applicability:" in x]) == 1
    assert len([x for x in req2_items if "Evaluation" in x]) == 1
    assert "timestamp" in req2_items[0].lower()
    assert "500 ms" in req2_items[1]


def test_v031_timed_transition_interval_is_not_misclassified_as_persistence():
    data = make_test001()
    req2 = data.requirements[1]
    req2.observation_interval_requirement = "Observation must cover the full 500 ms window following the trigger to confirm or exclude the transition."
    # No OBSERVATION_INTERVAL bucket is required for a timed transition when
    # response/timing evidence already covers the 500 ms window.
    req2.missing_evaluation_evidence = [
        EvidenceNeed(element=RequirementElementType.TRIGGER, description="Timestamp of the FunctionRequest transition to ACTIVE"),
        EvidenceNeed(element=RequirementElementType.RESPONSE, description="Timestamped FunctionStatus observation covering the full 500 ms window"),
        EvidenceNeed(element=RequirementElementType.TIMING, description="Alignable timebase / 500 ms timing coverage"),
    ]
    validated = DeterministicValidator().normalize_and_validate(data, canonical_case=make_canonical())
    errors = [x for x in validated.issues if x.severity.value == "ERROR"]
    codes = {x.code for x in errors}
    assert "MISSING_PERSISTENCE_EVALUATION_NEED" not in codes
    assert "MINIMUM_EVIDENCE_PERSISTENCE_CLOSURE_FAILED" not in codes
    req2_items = [x for x in validated.compliance_evidence if x.startswith("REQ-002")]
    assert any("timing constraint" in x.lower() for x in req2_items)
    assert not any("persistence" in x.lower() for x in req2_items)


def test_v031_true_persistence_need_is_derived_without_llm_repair():
    data = make_test001()
    req3 = data.requirements[2]
    req3.missing_evaluation_evidence = [
        EvidenceNeed(element=RequirementElementType.RESPONSE, description="Observe FunctionStatus over the applicable interval")
    ]
    validated = DeterministicValidator().normalize_and_validate(data, canonical_case=make_canonical())
    req3v = next(x.analysis for x in validated.requirement_results if x.analysis.requirement_id == "REQ-003")
    errors = [x for x in validated.issues if x.severity.value == "ERROR"]
    assert not any(x.code == "MISSING_PERSISTENCE_EVALUATION_NEED" for x in errors), errors
    assert any(n.element == RequirementElementType.OBSERVATION_INTERVAL for n in req3v.missing_evaluation_evidence)
    assert any(x.code == "PERSISTENCE_EVALUATION_NEED_DERIVED" for x in validated.issues)
    assert any("Persistence" in x for x in validated.compliance_evidence if x.startswith("REQ-003"))


def test_v032_timing_need_is_normalized_without_llm_repair():
    data = make_test001()
    req2 = data.requirements[1]
    req2.evaluation_evidence_ids = []
    req2.missing_evaluation_evidence = [
        EvidenceNeed(element=RequirementElementType.TRIGGER, description="Timestamp of the FunctionRequest-to-ACTIVE transition to anchor the 500 ms window."),
        EvidenceNeed(element=RequirementElementType.RESPONSE, description="Timestamped observation of FunctionStatus state covering the full 500 ms window after the trigger."),
        EvidenceNeed(element=RequirementElementType.RESPONSE, description="Adequate temporal coverage of the entire 500 ms timing window."),
        EvidenceNeed(element=RequirementElementType.RESPONSE, description="Alignable timebase between the trigger source and the FunctionStatus observation source."),
    ]
    validated = DeterministicValidator().normalize_and_validate(data, canonical_case=make_canonical())
    req2v = next(x.analysis for x in validated.requirement_results if x.analysis.requirement_id == "REQ-002")
    errors = [x for x in validated.issues if x.severity.value == "ERROR"]
    assert not any(x.code == "MISSING_TIMING_EVALUATION_NEED" for x in errors), errors
    assert any(n.element == RequirementElementType.TIMING for n in req2v.missing_evaluation_evidence)
    assert len([n for n in req2v.missing_evaluation_evidence if n.element == RequirementElementType.RESPONSE]) == 1
    assert len([n for n in req2v.missing_evaluation_evidence if n.element == RequirementElementType.TRIGGER]) == 1
    assert any("timebase" in n.description.lower() for n in req2v.missing_evaluation_evidence if n.element == RequirementElementType.TIMING)
    assert any(x.code == "TIMING_EVALUATION_NEEDS_NORMALIZED" for x in validated.issues)


def test_v032_timing_relevance_cannot_claim_unproven_timing_failure():
    data = make_test001()
    req2 = data.requirements[1]
    req2.relevance = "This mandatory requirement directly specifies the response transition and its 500 ms timing bound that the reported observation states was not achieved."
    validated = DeterministicValidator().normalize_and_validate(data, canonical_case=make_canonical())
    req2v = next(x.analysis for x in validated.requirement_results if x.analysis.requirement_id == "REQ-002")
    assert "timing constraint cannot be evaluated" in req2v.relevance.lower()
    assert "timing bound that the reported observation states was not achieved" not in req2v.relevance.lower()
    assert any(x.code == "TIMING_RELEVANCE_CLAIM_NORMALIZED" for x in validated.issues)


def test_v033_permissive_soft_converse_relevance_is_normalized():
    data = make_test001()
    req = data.requirements[0]
    req.relevance = (
        "This permissive requirement defines whether the activation path was permitted under the test's "
        "conditions, providing context for whether the system was allowed to process the request at all."
    )
    validated = DeterministicValidator().normalize_and_validate(data, canonical_case=make_canonical())
    req1 = next(x.analysis for x in validated.requirement_results if x.analysis.requirement_id == "REQ-001")
    errors = [x for x in validated.issues if x.severity.value == "ERROR"]
    assert not any(x.code == "PERMISSIVE_CONVERSE_RISK" for x in errors), errors
    assert "makes no statement about whether the same behavior is permitted under other conditions" in req1.relevance
    assert "allowed to process" not in req1.relevance.lower()
    assert any(x.code == "RELEVANCE_PROSE_NORMALIZED" for x in validated.issues)


def test_v033_causal_alternative_relevance_is_normalized():
    data = make_test001()
    req = data.requirements[2]
    req.relevance = (
        "This requirement is relevant to determine whether the inactive state could be a correct response "
        "to a different condition rather than a failure of the activation path."
    )
    validated = DeterministicValidator().normalize_and_validate(data, canonical_case=make_canonical())
    req3 = next(x.analysis for x in validated.requirement_results if x.analysis.requirement_id == "REQ-003")
    errors = [x for x in validated.issues if x.severity.value == "ERROR"]
    assert not any(x.code == "CAUSAL_RELEVANCE_LANGUAGE" for x in errors), errors
    assert "could be a correct response" not in req3.relevance.lower()
    assert "rather than a failure" not in req3.relevance.lower()
    assert "AvailabilityStatus is NOT_AVAILABLE" in req3.relevance
    assert any(x.code == "RELEVANCE_PROSE_NORMALIZED" for x in validated.issues)


def test_v033_persistence_evidence_is_compacted_to_single_interval_need():
    data = make_test001()
    req = data.requirements[2]
    req.missing_evaluation_evidence = [
        EvidenceNeed(
            element=RequirementElementType.RESPONSE,
            description="Sustained observation of FunctionStatus over the applicable interval to confirm it remained INACTIVE.",
        ),
        EvidenceNeed(
            element=RequirementElementType.OBSERVATION_INTERVAL,
            description="Observation coverage over the full NOT_AVAILABLE interval.",
        ),
    ]
    validated = DeterministicValidator().normalize_and_validate(data, canonical_case=make_canonical())
    req3 = next(x.analysis for x in validated.requirement_results if x.analysis.requirement_id == "REQ-003")
    needs = req3.missing_evaluation_evidence
    assert len(needs) == 1
    assert needs[0].element == RequirementElementType.OBSERVATION_INTERVAL
    assert "FunctionStatus shall remain INACTIVE" in needs[0].description
    assert "AvailabilityStatus is NOT_AVAILABLE" in needs[0].description
    assert any(x.code == "PERSISTENCE_EVALUATION_NEEDS_NORMALIZED" for x in validated.issues)


def test_v034_permissive_sufficiency_is_not_required():
    data = make_test001()
    req1 = data.requirements[0]
    req1.evaluation_sufficiency = Sufficiency.SUFFICIENT_CONFORMANCE
    validated = DeterministicValidator().normalize_and_validate(data, canonical_case=make_canonical())
    req1v = next(x.analysis for x in validated.requirement_results if x.analysis.requirement_id == "REQ-001")
    errors = [x for x in validated.issues if x.severity.value == "ERROR"]
    assert not errors, errors
    assert req1v.evaluation_sufficiency == Sufficiency.NOT_REQUIRED
    rr = next(x for x in validated.requirement_results if x.analysis.requirement_id == "REQ-001")
    assert rr.evaluation_status.value == "NO COMPLIANCE VERDICT"
    assert any(x.code == "PERMISSIVE_SUFFICIENCY_NORMALIZED" for x in validated.issues)


def test_v034_timing_relevance_did_not_occur_is_normalized():
    data = make_test001()
    req2 = data.requirements[1]
    req2.relevance = (
        "This requirement directly specifies the mandatory response (FunctionStatus becoming ACTIVE within 500 ms) "
        "that the reported observation states did not occur, making it the primary normative obligation implicated by the failure."
    )
    validated = DeterministicValidator().normalize_and_validate(data, canonical_case=make_canonical())
    req2v = next(x.analysis for x in validated.requirement_results if x.analysis.requirement_id == "REQ-002")
    errors = [x for x in validated.issues if x.severity.value == "ERROR"]
    assert not errors, errors
    assert "timing constraint cannot be evaluated" in req2v.relevance.lower()
    assert "within 500 ms) that the reported observation states did not occur" not in req2v.relevance.lower()
    assert any(x.code == "TIMING_RELEVANCE_CLAIM_NORMALIZED" for x in validated.issues)


def test_v035_permissive_response_observation_is_not_auto_mapped():
    data = make_test001()
    req1 = data.requirements[0]
    req1.evaluation_evidence_ids = []
    req1.evaluation_sufficiency = Sufficiency.NOT_REQUIRED
    validated = DeterministicValidator().normalize_and_validate(data, canonical_case=make_canonical())
    req1v = next(x.analysis for x in validated.requirement_results if x.analysis.requirement_id == "REQ-001")
    assert req1v.evaluation_evidence_ids == []
    assert req1v.evaluation_sufficiency == Sufficiency.NOT_REQUIRED
    assert not any(
        x.code == "RELEVANT_OBSERVATION_AUTO_MAPPED" and "requirements[0]" in x.path
        for x in validated.issues
    )


def test_v035_permissive_supplied_evaluation_evidence_is_removed():
    data = make_test001()
    req1 = data.requirements[0]
    req1.evaluation_evidence_ids = ["E1"]
    req1.evaluation_sufficiency = Sufficiency.NOT_REQUIRED
    validated = DeterministicValidator().normalize_and_validate(data, canonical_case=make_canonical())
    req1v = next(x.analysis for x in validated.requirement_results if x.analysis.requirement_id == "REQ-001")
    rr1 = next(x for x in validated.requirement_results if x.analysis.requirement_id == "REQ-001")
    assert req1v.evaluation_evidence_ids == []
    assert rr1.evidence_ids == []
    assert rr1.evaluation_status.value == "NO COMPLIANCE VERDICT"
    assert any(x.code == "PERMISSIVE_EVALUATION_EVIDENCE_REMOVED" for x in validated.issues)


def test_v035_causal_attribution_relevance_is_normalized():
    data = make_test001()
    req3 = data.requirements[2]
    req3.relevance = (
        "This requirement governs FunctionStatus persistence when AvailabilityStatus is NOT_AVAILABLE, "
        "a different applicability condition from the one the test was designed to establish; it is relevant "
        "as a boundary condition that must be excluded or confirmed before attributing the observed inactivity "
        "to a violation of the activation path."
    )
    validated = DeterministicValidator().normalize_and_validate(data, canonical_case=make_canonical())
    req3v = next(x.analysis for x in validated.requirement_results if x.analysis.requirement_id == "REQ-003")
    assert "before attributing" not in req3v.relevance.lower()
    assert "violation of the activation path" not in req3v.relevance.lower()
    assert req3v.relevance == (
        "This requirement defines the required behavior when AvailabilityStatus is NOT_AVAILABLE; "
        "its applicability depends on whether that condition is established in the current case."
    )
    assert any(x.code == "RELEVANCE_PROSE_NORMALIZED" for x in validated.issues)


def test_v035_safe_timing_unevaluable_relevance_is_preserved():
    data = make_test001()
    req2 = data.requirements[1]
    safe = (
        "This requirement obligates FunctionStatus to become ACTIVE within 500 ms of FunctionRequest becoming ACTIVE; "
        "the reported observation that FunctionStatus did not become ACTIVE is relevant to the required transition, "
        "while the 500 ms timing constraint remains unevaluable due to absent timestamps and trigger confirmation."
    )
    req2.relevance = safe
    validated = DeterministicValidator().normalize_and_validate(data, canonical_case=make_canonical())
    req2v = next(x.analysis for x in validated.requirement_results if x.analysis.requirement_id == "REQ-002")
    assert req2v.relevance == safe
    assert not any(
        x.code in {"RELEVANCE_PROSE_NORMALIZED", "TIMING_RELEVANCE_CLAIM_NORMALIZED"}
        and "requirements[1]" in x.path
        for x in validated.issues
    )



def test_v036_generic_conditional_converse_relevance_is_normalized():
    data = make_test001()
    req3 = data.requirements[2]
    req3.relevance = (
        "This requirement constrains FunctionStatus to INACTIVE only when AvailabilityStatus is NOT_AVAILABLE, "
        "a condition not established by current-case evidence."
    )
    validated = DeterministicValidator().normalize_and_validate(data, canonical_case=make_canonical())
    req3v = next(x.analysis for x in validated.requirement_results if x.analysis.requirement_id == "REQ-003")
    errors = [x for x in validated.issues if x.severity.value == "ERROR"]
    assert not errors, errors
    assert "only when" not in req3v.relevance.lower()
    assert req3v.relevance == (
        "This requirement defines the required behavior when AvailabilityStatus is NOT_AVAILABLE; "
        "its applicability depends on whether that condition is established in the current case."
    )
    assert any(x.code == "RELEVANCE_PROSE_NORMALIZED" for x in validated.issues)


def test_v036_explanatory_relevance_is_normalized_outside_hypothesis_section():
    data = make_test001()
    req1 = data.requirements[0]
    req1.relevance = (
        "This permissive requirement creates no obligation, so it does not independently explain the reported non-activation."
    )
    validated = DeterministicValidator().normalize_and_validate(data, canonical_case=make_canonical())
    req1v = next(x.analysis for x in validated.requirement_results if x.analysis.requirement_id == "REQ-001")
    errors = [x for x in validated.issues if x.severity.value == "ERROR"]
    assert not errors, errors
    assert "explain" not in req1v.relevance.lower()
    assert "makes no statement about whether the same behavior is permitted under other conditions" in req1v.relevance
    assert any(x.code == "RELEVANCE_PROSE_NORMALIZED" for x in validated.issues)


def test_v036_faithful_meaning_converse_is_rejected_for_one_way_conditional():
    data = make_test001()
    req3 = data.requirements[2]
    req3.faithful_meaning = "FunctionStatus remains INACTIVE only when AvailabilityStatus is NOT_AVAILABLE."
    validated = DeterministicValidator().normalize_and_validate(data, canonical_case=make_canonical())
    errors = [x for x in validated.issues if x.severity.value == "ERROR"]
    assert any(x.code == "CONDITIONAL_CONVERSE_RISK" for x in errors)


def test_v036_explicit_only_when_source_is_not_treated_as_converse_invention():
    case = make_canonical()
    case.requirements[2].requirement_text = "FunctionStatus shall remain INACTIVE only when AvailabilityStatus is NOT_AVAILABLE."
    data = make_test001()
    req3 = data.requirements[2]
    req3.requirement_text = case.requirements[2].requirement_text
    req3.applicability_condition = "AvailabilityStatus is NOT_AVAILABLE"
    req3.faithful_meaning = "FunctionStatus shall remain INACTIVE only when AvailabilityStatus is NOT_AVAILABLE."
    req3.relevance = "FunctionStatus is constrained to INACTIVE only when AvailabilityStatus is NOT_AVAILABLE."
    validated = DeterministicValidator().normalize_and_validate(data, canonical_case=case)
    assert not any(x.code == "CONDITIONAL_CONVERSE_RISK" for x in validated.issues)


def test_v040_applicability_evidence_ids_are_required_in_schema():
    schema = RequirementAnalysis.model_json_schema()
    assert "applicability_evidence_ids" in schema.get("required", [])


def test_v040_test002_explicit_applicability_binding_preserves_verdicts():
    from pathlib import Path
    from rca_app.case_parser import DeterministicCaseParser

    case_text = (Path(__file__).resolve().parent.parent / "examples" / "TEST-002.txt").read_text(encoding="utf-8")
    canonical = DeterministicCaseParser().parse(case_text)
    direct_by_signal = {
        e.signal_name: e.id
        for e in canonical.evidence_inventory
        if e.evidence_class == EvidenceClass.DIRECT_OBSERVATION and e.signal_name
    }
    reported_id = next(e.id for e in canonical.evidence_inventory if e.evidence_class == EvidenceClass.REPORTED_OBSERVATION)

    data = SemanticAnalysis(
        affected_functionality="Function X activation state",
        evidence_inventory=canonical.evidence_inventory,
        requirements=[
            RequirementAnalysis(
                requirement_id="REQ-101",
                requirement_text="If IgnitionState is ON and AvailabilityStatus is AVAILABLE, FunctionStatus shall be ACTIVE.",
                faithful_meaning="When both conditions hold, FunctionStatus is required to be ACTIVE.",
                relevance="This requirement defines the required FunctionStatus state when IgnitionState is ON and AvailabilityStatus is AVAILABLE.",
                normative_type=NormativeType.MANDATORY,
                applicability=Applicability.APPLICABLE,
                applicability_evidence_ids=[direct_by_signal["IgnitionState"], direct_by_signal["AvailabilityStatus"]],
                applicability_condition="IgnitionState is ON AND AvailabilityStatus is AVAILABLE",
                required_behavior="FunctionStatus shall be ACTIVE",
                evaluation_evidence_ids=[reported_id, direct_by_signal["FunctionStatus"]],
                evaluation_sufficiency=Sufficiency.SUFFICIENT_NONCONFORMANCE,
            ),
            RequirementAnalysis(
                requirement_id="REQ-102",
                requirement_text="If AvailabilityStatus is AVAILABLE, WarningIndicator shall be OFF.",
                faithful_meaning="When AvailabilityStatus is AVAILABLE, WarningIndicator is required to be OFF.",
                relevance="This requirement defines the required WarningIndicator state when AvailabilityStatus is AVAILABLE.",
                normative_type=NormativeType.MANDATORY,
                applicability=Applicability.APPLICABLE,
                applicability_evidence_ids=[direct_by_signal["AvailabilityStatus"]],
                applicability_condition="AvailabilityStatus is AVAILABLE",
                required_behavior="WarningIndicator shall be OFF",
                evaluation_evidence_ids=[direct_by_signal["WarningIndicator"]],
                evaluation_sufficiency=Sufficiency.SUFFICIENT_CONFORMANCE,
            ),
            RequirementAnalysis(
                requirement_id="REQ-103",
                requirement_text="If AvailabilityStatus is NOT_AVAILABLE, FunctionStatus shall remain INACTIVE.",
                faithful_meaning="When AvailabilityStatus is NOT_AVAILABLE, FunctionStatus is required to remain INACTIVE.",
                relevance="This requirement defines the required behavior when AvailabilityStatus is NOT_AVAILABLE.",
                normative_type=NormativeType.MANDATORY,
                applicability=Applicability.NOT_APPLICABLE,
                applicability_evidence_ids=[direct_by_signal["AvailabilityStatus"]],
                applicability_condition="AvailabilityStatus is NOT_AVAILABLE",
                required_behavior="FunctionStatus shall remain INACTIVE",
                observation_interval_requirement="Persistence while AvailabilityStatus is NOT_AVAILABLE",
                evaluation_evidence_ids=[],
                evaluation_sufficiency=Sufficiency.INSUFFICIENT,
            ),
        ],
    )

    validated = DeterministicValidator().normalize_and_validate(data, canonical_case=canonical)
    errors = [x for x in validated.issues if x.severity.value == "ERROR"]
    assert not errors, errors
    statuses = {x.analysis.requirement_id: x.evaluation_status.value for x in validated.requirement_results}
    assert statuses == {
        "REQ-101": "VIOLATED",
        "REQ-102": "NOT EVALUABLE",
        "REQ-103": "NO COMPLIANCE VERDICT",
    }
    reqs = {x.analysis.requirement_id: x.analysis for x in validated.requirement_results}
    assert reqs["REQ-101"].applicability_evidence_ids == [direct_by_signal["IgnitionState"], direct_by_signal["AvailabilityStatus"]]
    assert reqs["REQ-102"].applicability_evidence_ids == [direct_by_signal["AvailabilityStatus"]]
    assert reqs["REQ-103"].applicability_evidence_ids == [direct_by_signal["AvailabilityStatus"]]
    assert reqs["REQ-103"].evaluation_sufficiency == Sufficiency.NOT_REQUIRED
    assert reqs["REQ-103"].evaluation_evidence_ids == []
    assert reqs["REQ-103"].missing_evaluation_evidence == []
    assert reqs["REQ-102"].evaluation_sufficiency == Sufficiency.INSUFFICIENT
    assert any(n.element == RequirementElementType.OBSERVATION_INTERVAL for n in reqs["REQ-102"].missing_evaluation_evidence)
    assert any("WarningIndicator" in item and "interval" in item.lower() for item in validated.compliance_evidence)


def _make_v043_test003_semantic(case_text=None, response_time=10.650):
    from pathlib import Path
    from rca_app.case_parser import DeterministicCaseParser
    from rca_app.models import EvidenceNeed, ObservationType, RequirementElementType

    if case_text is None:
        case_text = (Path(__file__).resolve().parent.parent / "examples" / "TEST-003.txt").read_text(encoding="utf-8")
    if response_time != 10.650:
        case_text = case_text.replace("10.650 s FunctionStatus = ACTIVE", f"{response_time:.3f} s FunctionStatus = ACTIVE")
    canonical = DeterministicCaseParser().parse(case_text)
    trigger = next(e for e in canonical.evidence_inventory if e.signal_name == "FunctionRequest" and e.observation_type == ObservationType.TRANSITION)
    response = next(e for e in canonical.evidence_inventory if e.signal_name == "FunctionStatus" and e.transition_to == "ACTIVE")
    availability = next(e for e in canonical.evidence_inventory if e.signal_name == "AvailabilityStatus")
    reported = next(e for e in canonical.evidence_inventory if e.evidence_class == EvidenceClass.REPORTED_OBSERVATION)
    status_samples = [e.id for e in canonical.evidence_inventory if e.signal_name == "FunctionStatus" and not e.transition_to]

    semantic = SemanticAnalysis(
        affected_functionality="Function activation response timing",
        evidence_inventory=canonical.evidence_inventory,
        requirements=[
            RequirementAnalysis(
                requirement_id="REQ-201",
                requirement_text="When FunctionRequest becomes ACTIVE, FunctionStatus shall become ACTIVE within 500 ms.",
                faithful_meaning="When FunctionRequest transitions to ACTIVE, FunctionStatus must transition to ACTIVE within 500 ms.",
                relevance="This requirement defines the timed FunctionStatus response to the FunctionRequest transition.",
                normative_type=NormativeType.MANDATORY,
                applicability=Applicability.APPLICABLE,
                applicability_evidence_ids=[trigger.id],
                trigger="FunctionRequest becomes ACTIVE",
                required_behavior="FunctionStatus shall become ACTIVE",
                timing_constraint="within 500 ms",
                evaluation_evidence_ids=status_samples + [response.id, reported.id],
                evaluation_sufficiency=Sufficiency.INSUFFICIENT,
                missing_evaluation_evidence=[
                    EvidenceNeed(element=RequirementElementType.RESPONSE, description="A tighter timing observation would be useful.")
                ],
            ),
            RequirementAnalysis(
                requirement_id="REQ-202",
                requirement_text="If AvailabilityStatus is NOT_AVAILABLE, FunctionStatus shall remain INACTIVE.",
                faithful_meaning="When AvailabilityStatus is NOT_AVAILABLE, FunctionStatus must remain INACTIVE.",
                relevance="This requirement defines the required behavior when AvailabilityStatus is NOT_AVAILABLE.",
                normative_type=NormativeType.MANDATORY,
                applicability=Applicability.NOT_APPLICABLE,
                applicability_evidence_ids=[availability.id],
                applicability_condition="AvailabilityStatus is NOT_AVAILABLE",
                required_behavior="FunctionStatus shall remain INACTIVE",
                observation_interval_requirement="Persistence while AvailabilityStatus is NOT_AVAILABLE",
                evaluation_sufficiency=Sufficiency.NOT_REQUIRED,
            ),
        ],
    )
    return canonical, semantic


def test_v043_explicit_transition_timing_fact_derives_550ms_violation_and_clears_missing_needs():
    from rca_app.models import TimingOutcome

    canonical, semantic = _make_v043_test003_semantic()
    validated = DeterministicValidator().normalize_and_validate(semantic, canonical_case=canonical)
    errors = [x for x in validated.issues if x.severity.value == "ERROR"]
    assert not errors, errors

    rr = next(x for x in validated.requirement_results if x.analysis.requirement_id == "REQ-201")
    assert rr.evaluation_status == EvaluationStatus.VIOLATED
    assert rr.timing_fact is not None
    assert rr.timing_fact.outcome == TimingOutcome.EXCEEDS_LIMIT
    assert rr.timing_fact.elapsed_ms == 550.0
    assert rr.timing_fact.limit_ms == 500.0
    assert rr.timing_fact.margin_ms == 50.0
    assert rr.analysis.evaluation_sufficiency == Sufficiency.SUFFICIENT_NONCONFORMANCE
    assert rr.analysis.missing_evaluation_evidence == []
    assert validated.compliance_evidence == []
    assert any(x.code == "TIMING_SUFFICIENCY_DERIVED" for x in validated.issues)
    assert any(x.code == "RESOLVED_TIMING_NEEDS_REMOVED" for x in validated.issues)


def test_v043_explicit_transition_inside_limit_derives_satisfied():
    from rca_app.models import TimingOutcome

    canonical, semantic = _make_v043_test003_semantic(response_time=10.550)
    validated = DeterministicValidator().normalize_and_validate(semantic, canonical_case=canonical)
    rr = next(x for x in validated.requirement_results if x.analysis.requirement_id == "REQ-201")
    assert rr.evaluation_status == EvaluationStatus.SATISFIED
    assert rr.timing_fact is not None
    assert rr.timing_fact.outcome == TimingOutcome.WITHIN_LIMIT
    assert rr.timing_fact.elapsed_ms == 450.0
    assert rr.analysis.missing_evaluation_evidence == []


def test_v043_state_samples_cannot_prove_becomes_trigger_or_bridge_timing_gap():
    from pathlib import Path
    from rca_app.case_parser import DeterministicCaseParser

    text = """CURRENT TICKET
Ticket ID: SAMPLE-TIMING
Title: Sample-only timing
Description: Trigger and response values are sampled without observed transitions.
TEST INFORMATION
Test Steps:
1. Set FunctionRequest ACTIVE.
Reported Test Result:
FunctionStatus appeared ACTIVE.
SYSTEM REQUIREMENTS
REQ-201
When FunctionRequest becomes ACTIVE, FunctionStatus shall become ACTIVE within 500 ms.
REQ-202
If AvailabilityStatus is NOT_AVAILABLE, FunctionStatus shall remain INACTIVE.
CURRENT TRACE / DIRECT OBSERVATIONS
Clock ID: TRACE_A
Event Coverage Complete: true
50.000 s FunctionRequest = ACTIVE
50.100 s FunctionStatus = ACTIVE
TASK
Analyze.
"""
    canonical = DeterministicCaseParser().parse(text)
    trigger_sample = next(e for e in canonical.evidence_inventory if e.signal_name == "FunctionRequest")
    response_sample = next(e for e in canonical.evidence_inventory if e.signal_name == "FunctionStatus")
    reported = next(e for e in canonical.evidence_inventory if e.evidence_class == EvidenceClass.REPORTED_OBSERVATION)

    semantic = SemanticAnalysis(
        affected_functionality="Function activation response timing",
        evidence_inventory=canonical.evidence_inventory,
        requirements=[
            RequirementAnalysis(
                requirement_id="REQ-201",
                requirement_text="When FunctionRequest becomes ACTIVE, FunctionStatus shall become ACTIVE within 500 ms.",
                faithful_meaning="When FunctionRequest becomes ACTIVE, FunctionStatus must become ACTIVE within 500 ms.",
                relevance="This requirement defines the timed response.",
                normative_type=NormativeType.MANDATORY,
                applicability=Applicability.APPLICABLE,
                applicability_evidence_ids=[trigger_sample.id],
                trigger="FunctionRequest becomes ACTIVE",
                required_behavior="FunctionStatus shall become ACTIVE",
                timing_constraint="within 500 ms",
                evaluation_evidence_ids=[response_sample.id, reported.id],
                evaluation_sufficiency=Sufficiency.SUFFICIENT_NONCONFORMANCE,
            ),
            RequirementAnalysis(
                requirement_id="REQ-202",
                requirement_text="If AvailabilityStatus is NOT_AVAILABLE, FunctionStatus shall remain INACTIVE.",
                faithful_meaning="When AvailabilityStatus is NOT_AVAILABLE, FunctionStatus must remain INACTIVE.",
                relevance="This requirement defines the behavior under NOT_AVAILABLE.",
                normative_type=NormativeType.MANDATORY,
                applicability=Applicability.UNKNOWN,
                applicability_evidence_ids=[],
                applicability_condition="AvailabilityStatus is NOT_AVAILABLE",
                required_behavior="FunctionStatus shall remain INACTIVE",
                observation_interval_requirement="Persistence while NOT_AVAILABLE",
                evaluation_sufficiency=Sufficiency.INSUFFICIENT,
            ),
        ],
    )

    validated = DeterministicValidator().normalize_and_validate(semantic, canonical_case=canonical)
    rr = next(x for x in validated.requirement_results if x.analysis.requirement_id == "REQ-201")
    assert rr.analysis.applicability == Applicability.UNKNOWN
    assert rr.evaluation_status == EvaluationStatus.NOT_EVALUABLE
    assert rr.timing_fact is None
    assert rr.analysis.evaluation_sufficiency == Sufficiency.INSUFFICIENT
    assert rr.analysis.missing_evaluation_evidence
    assert any(x.code == "TRIGGER_TRANSITION_NOT_ESTABLISHED" for x in validated.issues)
    assert any(x.code == "TIMING_SUFFICIENCY_DOWNGRADED" for x in validated.issues)


def test_v043_condition_only_not_applicable_cannot_be_proved_by_single_state_sample():
    from rca_app.models import ObservationType

    sample = EvidenceItem(
        id="E-AVAIL",
        evidence_class=EvidenceClass.DIRECT_OBSERVATION,
        text="10.020 s AvailabilityStatus = AVAILABLE",
        source="Direct Observations / Trace",
        timestamped=True,
        timestamp_seconds=10.02,
        coverage_complete=True,  # legacy/generic coverage must not help
        event_coverage_complete=True,  # event completeness also must not turn a point sample into an interval
        clock_id="TRACE_A",
        signal_name="AvailabilityStatus",
        signal_value="AVAILABLE",
        observation_type=ObservationType.STATE_SAMPLE,
    )
    canonical = CanonicalCase(
        evidence_inventory=[sample],
        requirements=[RequirementSource(
            requirement_id="REQ-202",
            requirement_text="If AvailabilityStatus is NOT_AVAILABLE, FunctionStatus shall remain INACTIVE.",
        )],
    )
    semantic = SemanticAnalysis(
        affected_functionality="FunctionStatus",
        evidence_inventory=[sample],
        requirements=[RequirementAnalysis(
            requirement_id="REQ-202",
            requirement_text="If AvailabilityStatus is NOT_AVAILABLE, FunctionStatus shall remain INACTIVE.",
            faithful_meaning="When AvailabilityStatus is NOT_AVAILABLE, FunctionStatus must remain INACTIVE.",
            relevance="This requirement defines the required behavior under NOT_AVAILABLE.",
            normative_type=NormativeType.MANDATORY,
            applicability=Applicability.NOT_APPLICABLE,
            applicability_evidence_ids=[sample.id],
            applicability_condition="AvailabilityStatus is NOT_AVAILABLE",
            required_behavior="FunctionStatus shall remain INACTIVE",
            observation_interval_requirement="Persistence while AvailabilityStatus is NOT_AVAILABLE",
            evaluation_sufficiency=Sufficiency.NOT_REQUIRED,
        )],
    )

    validated = DeterministicValidator().normalize_and_validate(semantic, canonical_case=canonical)
    rr = validated.requirement_results[0]
    assert rr.analysis.applicability == Applicability.UNKNOWN
    assert rr.analysis.evaluation_sufficiency == Sufficiency.INSUFFICIENT
    assert rr.evaluation_status == EvaluationStatus.NOT_EVALUABLE
    assert rr.analysis.missing_applicability_evidence
    assert rr.analysis.missing_evaluation_evidence
    assert any(x.code == "NOT_APPLICABLE_SCOPE_NOT_ESTABLISHED" for x in validated.issues)


def test_v043_condition_only_not_applicable_is_preserved_by_interval_state():
    from rca_app.models import ObservationType

    interval = EvidenceItem(
        id="E-AVAIL",
        evidence_class=EvidenceClass.DIRECT_OBSERVATION,
        text="AvailabilityStatus remained AVAILABLE throughout the complete evaluated interval.",
        source="Direct Observations / Trace",
        coverage_complete=True,
        signal_name="AvailabilityStatus",
        signal_value="AVAILABLE",
        observation_type=ObservationType.INTERVAL_STATE,
    )
    canonical = CanonicalCase(
        evidence_inventory=[interval],
        requirements=[RequirementSource(
            requirement_id="REQ-202",
            requirement_text="If AvailabilityStatus is NOT_AVAILABLE, FunctionStatus shall remain INACTIVE.",
        )],
    )
    semantic = SemanticAnalysis(
        affected_functionality="FunctionStatus",
        evidence_inventory=[interval],
        requirements=[RequirementAnalysis(
            requirement_id="REQ-202",
            requirement_text="If AvailabilityStatus is NOT_AVAILABLE, FunctionStatus shall remain INACTIVE.",
            faithful_meaning="When AvailabilityStatus is NOT_AVAILABLE, FunctionStatus must remain INACTIVE.",
            relevance="This requirement defines the required behavior under NOT_AVAILABLE.",
            normative_type=NormativeType.MANDATORY,
            applicability=Applicability.NOT_APPLICABLE,
            applicability_evidence_ids=[interval.id],
            applicability_condition="AvailabilityStatus is NOT_AVAILABLE",
            required_behavior="FunctionStatus shall remain INACTIVE",
            observation_interval_requirement="Persistence while AvailabilityStatus is NOT_AVAILABLE",
            evaluation_sufficiency=Sufficiency.NOT_REQUIRED,
        )],
    )

    validated = DeterministicValidator().normalize_and_validate(semantic, canonical_case=canonical)
    rr = validated.requirement_results[0]
    assert rr.analysis.applicability == Applicability.NOT_APPLICABLE
    assert rr.evaluation_status == EvaluationStatus.NO_COMPLIANCE_VERDICT
    assert not any(x.code == "NOT_APPLICABLE_SCOPE_NOT_ESTABLISHED" for x in validated.issues)


def test_v043_late_timing_violation_requires_explicit_event_coverage_not_legacy_generic_coverage():
    from pathlib import Path

    text = (Path(__file__).resolve().parent.parent / "examples" / "TEST-003.txt").read_text(encoding="utf-8")
    text = text.replace("Event Coverage Complete: true", "Coverage Complete: true")
    canonical, semantic = _make_v043_test003_semantic(case_text=text)
    validated = DeterministicValidator().normalize_and_validate(semantic, canonical_case=canonical)

    rr = next(x for x in validated.requirement_results if x.analysis.requirement_id == "REQ-201")
    assert rr.timing_fact is None
    assert rr.analysis.evaluation_sufficiency == Sufficiency.INSUFFICIENT
    assert rr.evaluation_status == EvaluationStatus.NOT_EVALUABLE
    assert any(x.code == "TIMING_LATE_TRANSITION_COVERAGE_INCOMPLETE" for x in validated.issues)


def test_v043_persistence_verdict_requires_interval_state_not_sample_plus_coverage():
    from rca_app.models import ObservationType

    app_interval = EvidenceItem(
        id="E-APP",
        evidence_class=EvidenceClass.DIRECT_OBSERVATION,
        text="AvailabilityStatus remained NOT_AVAILABLE throughout the complete evaluated interval.",
        source="Direct Observations / Trace",
        coverage_complete=True,
        signal_name="AvailabilityStatus",
        signal_value="NOT_AVAILABLE",
        observation_type=ObservationType.INTERVAL_STATE,
    )
    response_sample = EvidenceItem(
        id="E-STATUS",
        evidence_class=EvidenceClass.DIRECT_OBSERVATION,
        text="10.300 s FunctionStatus = INACTIVE",
        source="Direct Observations / Trace",
        timestamped=True,
        timestamp_seconds=10.3,
        coverage_complete=True,
        event_coverage_complete=True,
        signal_name="FunctionStatus",
        signal_value="INACTIVE",
        observation_type=ObservationType.STATE_SAMPLE,
    )
    canonical = CanonicalCase(
        evidence_inventory=[app_interval, response_sample],
        requirements=[RequirementSource(
            requirement_id="REQ-PERSIST",
            requirement_text="If AvailabilityStatus is NOT_AVAILABLE, FunctionStatus shall remain INACTIVE.",
        )],
    )
    semantic = SemanticAnalysis(
        affected_functionality="FunctionStatus persistence",
        evidence_inventory=[app_interval, response_sample],
        requirements=[RequirementAnalysis(
            requirement_id="REQ-PERSIST",
            requirement_text="If AvailabilityStatus is NOT_AVAILABLE, FunctionStatus shall remain INACTIVE.",
            faithful_meaning="When AvailabilityStatus is NOT_AVAILABLE, FunctionStatus must remain INACTIVE.",
            relevance="This requirement defines FunctionStatus persistence under NOT_AVAILABLE.",
            normative_type=NormativeType.MANDATORY,
            applicability=Applicability.APPLICABLE,
            applicability_evidence_ids=[app_interval.id],
            applicability_condition="AvailabilityStatus is NOT_AVAILABLE",
            required_behavior="FunctionStatus shall remain INACTIVE",
            observation_interval_requirement="Persistence across the NOT_AVAILABLE interval",
            evaluation_evidence_ids=[response_sample.id],
            evaluation_sufficiency=Sufficiency.SUFFICIENT_CONFORMANCE,
        )],
    )

    validated = DeterministicValidator().normalize_and_validate(semantic, canonical_case=canonical)
    rr = validated.requirement_results[0]
    assert rr.analysis.evaluation_sufficiency == Sufficiency.INSUFFICIENT
    assert rr.evaluation_status == EvaluationStatus.NOT_EVALUABLE
    assert any(n.element == RequirementElementType.OBSERVATION_INTERVAL for n in rr.analysis.missing_evaluation_evidence)
    assert any(x.code == "PERSISTENCE_SUFFICIENCY_DOWNGRADED" for x in validated.issues)


def test_v043_persistence_interval_state_can_support_satisfied_verdict():
    from rca_app.models import ObservationType

    app_interval = EvidenceItem(
        id="E-APP",
        evidence_class=EvidenceClass.DIRECT_OBSERVATION,
        text="AvailabilityStatus remained NOT_AVAILABLE throughout the complete evaluated interval.",
        source="Direct Observations / Trace",
        coverage_complete=True,
        signal_name="AvailabilityStatus",
        signal_value="NOT_AVAILABLE",
        observation_type=ObservationType.INTERVAL_STATE,
    )
    response_interval = EvidenceItem(
        id="E-STATUS",
        evidence_class=EvidenceClass.DIRECT_OBSERVATION,
        text="FunctionStatus remained INACTIVE throughout the complete evaluated interval.",
        source="Direct Observations / Trace",
        coverage_complete=True,
        signal_name="FunctionStatus",
        signal_value="INACTIVE",
        observation_type=ObservationType.INTERVAL_STATE,
    )
    canonical = CanonicalCase(
        evidence_inventory=[app_interval, response_interval],
        requirements=[RequirementSource(
            requirement_id="REQ-PERSIST",
            requirement_text="If AvailabilityStatus is NOT_AVAILABLE, FunctionStatus shall remain INACTIVE.",
        )],
    )
    semantic = SemanticAnalysis(
        affected_functionality="FunctionStatus persistence",
        evidence_inventory=[app_interval, response_interval],
        requirements=[RequirementAnalysis(
            requirement_id="REQ-PERSIST",
            requirement_text="If AvailabilityStatus is NOT_AVAILABLE, FunctionStatus shall remain INACTIVE.",
            faithful_meaning="When AvailabilityStatus is NOT_AVAILABLE, FunctionStatus must remain INACTIVE.",
            relevance="This requirement defines FunctionStatus persistence under NOT_AVAILABLE.",
            normative_type=NormativeType.MANDATORY,
            applicability=Applicability.APPLICABLE,
            applicability_evidence_ids=[app_interval.id],
            applicability_condition="AvailabilityStatus is NOT_AVAILABLE",
            required_behavior="FunctionStatus shall remain INACTIVE",
            observation_interval_requirement="Persistence across the NOT_AVAILABLE interval",
            evaluation_evidence_ids=[response_interval.id],
            evaluation_sufficiency=Sufficiency.SUFFICIENT_CONFORMANCE,
        )],
    )

    validated = DeterministicValidator().normalize_and_validate(semantic, canonical_case=canonical)
    rr = validated.requirement_results[0]
    assert rr.analysis.evaluation_sufficiency == Sufficiency.SUFFICIENT_CONFORMANCE
    assert rr.evaluation_status == EvaluationStatus.SATISFIED
