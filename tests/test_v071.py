from __future__ import annotations

import json

from rca_app.lmstudio_client import LMStudioClient
from rca_app.models import (
    Applicability,
    AtomicClaimExtractionSet,
    CanonicalCase,
    EvidenceClass,
    EvidenceItem,
    EvidenceNeed,
    NormativeType,
    ObservationType,
    PredicateOperator,
    RequirementAnalysis,
    RequirementElementType,
    RequirementLanguageNormalization,
    RequirementLanguageNormalizationSet,
    RequirementPredicate,
    RequirementPredicateGroup,
    SemanticAnalysis,
    SourceAvailability,
    SourceAvailabilityNormalization,
    Sufficiency,
)
from rca_app.semantic_preprocessing import FastSemanticPreprocessor
from rca_app.validator import DeterministicValidator


def test_v071_source_availability_accepts_compact_string_statement_envelope():
    parsed = SourceAvailabilityNormalization.model_validate({
        "requirements": {"availability": "PRESENT", "availability_statement": ""},
        "historical": {"availability": "ABSENT", "availability_statement": "None provided."},
        "diagnostics": {"availability": "ABSENT", "availability_statement": "Not available."},
        "trace": {"availability": "PRESENT", "availability_statement": ""},
    })
    assert parsed.requirements.availability == SourceAvailability.PRESENT
    assert parsed.historical.availability_statement.source_span == "None provided."
    assert parsed.diagnostics.availability_statement.source_span == "Not available."


def test_v071_atomic_claim_single_list_schema_accepts_bare_array_envelope():
    raw = '[{"source_category":"REPORTED_OBSERVATION","source_span":"A was late.","claim_text":"A was late.","claim_kind":"TIMING"}]'
    wrapped = LMStudioClient._parse_json_object_text(raw, response_model=AtomicClaimExtractionSet)
    parsed = AtomicClaimExtractionSet.model_validate(wrapped)
    assert len(parsed.claims) == 1
    assert parsed.claims[0].claim_text == "A was late."


def test_v071_requirement_language_contract_removes_behavior_and_trigger_from_applicability_groups():
    source_text = "When TailgateRequest becomes OPEN, TailgateStatus shall become OPEN within 800 ms."
    canonical = CanonicalCase(
        requirements=[{"requirement_id": "REQ-1204", "requirement_text": source_text}],
    )
    normalized = RequirementLanguageNormalizationSet(requirements=[RequirementLanguageNormalization(
        requirement_id="REQ-1204",
        applicability_any_of=[RequirementPredicateGroup(predicates=[
            RequirementPredicate(signal="TailgateRequest", operator=PredicateOperator.PRESENT, source_phrase="When TailgateRequest becomes OPEN"),
            RequirementPredicate(signal="TailgateStatus", operator=PredicateOperator.EQ, value="OPEN", source_phrase="shall become OPEN"),
        ])],
        trigger_signal="TailgateRequest",
        trigger_value="OPEN",
        required_behavior_signal="TailgateStatus",
        required_behavior_operator=PredicateOperator.EQ,
        required_behavior_value="OPEN",
        timing_limit_ms=800,
    )])
    attached = FastSemanticPreprocessor.attach_requirement_language(canonical, normalized)
    assert len(attached.requirement_language) == 1
    assert attached.requirement_language[0].applicability_any_of == []


def test_v071_structured_requirement_hints_restore_phase_a_trigger_and_machine_readable_timing():
    evidence = [
        EvidenceItem(id="T", evidence_class=EvidenceClass.DIRECT_OBSERVATION, text="100.000 s TailgateRequest = OPEN", source="Direct Observations / Trace", timestamped=True, timestamp_seconds=100.0, event_coverage_complete=True, clock_id="TRACE_BODY", signal_name="TailgateRequest", signal_value="OPEN", observation_type=ObservationType.TRANSITION, transition_from="CLOSED", transition_to="OPEN"),
        EvidenceItem(id="R", evidence_class=EvidenceClass.DIRECT_OBSERVATION, text="101.100 s TailgateStatus = OPEN", source="Direct Observations / Trace", timestamped=True, timestamp_seconds=101.1, event_coverage_complete=True, clock_id="TRACE_BODY", signal_name="TailgateStatus", signal_value="OPEN", observation_type=ObservationType.TRANSITION, transition_from="CLOSED", transition_to="OPEN"),
    ]
    req = RequirementAnalysis(
        requirement_id="REQ-1204",
        requirement_text="When TailgateRequest becomes OPEN, TailgateStatus shall become OPEN within 800 ms.",
        faithful_meaning="TailgateStatus must reach OPEN within 800 ms after the request becomes OPEN.",
        relevance="Direct timing requirement.",
        normative_type=NormativeType.MANDATORY,
        applicability=Applicability.APPLICABLE,
        applicability_evidence_ids=["T"],
        applicability_condition="TailgateRequest transitions to OPEN",
        trigger="",
        required_behavior="TailgateStatus shall become OPEN",
        timing_constraint="800 ms from trigger",
        evaluation_evidence_ids=["R"],
        evaluation_sufficiency=Sufficiency.SUFFICIENT_CONFORMANCE,
    )
    semantic = SemanticAnalysis(affected_functionality="tailgate", evidence_inventory=evidence, requirements=[req])
    canonical = CanonicalCase(
        evidence_inventory=evidence,
        requirements=[{"requirement_id": req.requirement_id, "requirement_text": req.requirement_text}],
        requirement_language=[RequirementLanguageNormalization(
            requirement_id="REQ-1204",
            trigger_signal="TailgateRequest",
            trigger_event="BECOMES",
            trigger_value="OPEN",
            required_behavior_signal="TailgateStatus",
            required_behavior_operator=PredicateOperator.EQ,
            required_behavior_value="OPEN",
            timing_limit_ms=800,
        )],
    )
    projected = FastSemanticPreprocessor.apply_requirement_language_hints(semantic, canonical)
    assert projected.requirements[0].trigger == "TailgateRequest becomes OPEN"
    assert projected.requirements[0].timing_constraint == "within 800 ms"
    validated = DeterministicValidator().normalize_and_validate(projected, canonical_case=canonical)
    result = validated.requirement_results[0]
    assert result.evaluation_status.value == "VIOLATED"
    assert result.timing_fact is not None
    assert round(result.timing_fact.elapsed_ms) == 1100
    assert round(result.timing_fact.limit_ms) == 800


def test_v071_structured_persistence_hint_restores_observation_interval_requirement():
    req = RequirementAnalysis(
        requirement_id="REQ-1208",
        requirement_text="If ChildLockState is ON, RearRightDoorStatus shall remain CLOSED.",
        faithful_meaning="While ChildLockState is ON, RearRightDoorStatus must remain CLOSED.",
        relevance="Conditional persistence requirement.",
        normative_type=NormativeType.MANDATORY,
        applicability=Applicability.UNKNOWN,
        applicability_evidence_ids=[],
        applicability_condition="ChildLockState is ON",
        required_behavior="RearRightDoorStatus shall remain CLOSED",
        observation_interval_requirement="",
        evaluation_sufficiency=Sufficiency.INSUFFICIENT,
    )
    semantic = SemanticAnalysis(affected_functionality="door", evidence_inventory=[], requirements=[req])
    canonical = CanonicalCase(
        requirements=[{"requirement_id": req.requirement_id, "requirement_text": req.requirement_text}],
        requirement_language=[RequirementLanguageNormalization(
            requirement_id="REQ-1208",
            applicability_any_of=[RequirementPredicateGroup(predicates=[RequirementPredicate(signal="ChildLockState", operator=PredicateOperator.EQ, value="ON", source_phrase="ChildLockState is ON")])],
            required_behavior_signal="RearRightDoorStatus",
            required_behavior_operator=PredicateOperator.EQ,
            required_behavior_value="CLOSED",
            persistence_required=True,
        )],
    )
    projected = FastSemanticPreprocessor.apply_requirement_language_hints(semantic, canonical)
    assert "continuously" in projected.requirements[0].observation_interval_requirement
    validated = DeterministicValidator().normalize_and_validate(projected, canonical_case=canonical)
    assert not any(x.code == "MISSING_PERSISTENCE_DECOMPOSITION" for x in validated.issues)


def test_v071_applicability_label_in_evaluation_bucket_is_structurally_removed_when_resolved():
    evidence = [EvidenceItem(
        id="I", evidence_class=EvidenceClass.DIRECT_OBSERVATION,
        text="IgnitionState remained ON throughout the complete evaluated interval.",
        source="Direct Observations / Trace", coverage_complete=True,
        signal_name="IgnitionState", signal_value="ON", observation_type=ObservationType.INTERVAL_STATE,
    )]
    req = RequirementAnalysis(
        requirement_id="REQ-1201",
        requirement_text="If IgnitionState is ON, CentralLockStatus shall be READY.",
        faithful_meaning="When IgnitionState is ON, CentralLockStatus must be READY.",
        relevance="Conditional state requirement.",
        normative_type=NormativeType.MANDATORY,
        applicability=Applicability.APPLICABLE,
        applicability_evidence_ids=["I"],
        applicability_condition="IgnitionState is ON",
        required_behavior="CentralLockStatus equals READY",
        evaluation_sufficiency=Sufficiency.INSUFFICIENT,
        missing_evaluation_evidence=[
            EvidenceNeed(element=RequirementElementType.APPLICABILITY, description="Applicability is already established by IgnitionState=ON."),
            EvidenceNeed(element=RequirementElementType.RESPONSE, description="Observe CentralLockStatus = READY."),
        ],
    )
    semantic = SemanticAnalysis(affected_functionality="lock", evidence_inventory=evidence, requirements=[req])
    validated = DeterministicValidator().normalize_and_validate(semantic)
    kept = validated.requirement_results[0].analysis.missing_evaluation_evidence
    assert all(x.element != RequirementElementType.APPLICABILITY for x in kept)
    assert any(x.code == "EVALUATION_BUCKET_APPLICABILITY_NORMALIZED" for x in validated.issues)
    assert not any(x.code == "APPLICABILITY_NEED_IN_EVALUATION_BUCKET" for x in validated.issues)


def test_v071_structured_behavior_signal_prevents_false_evaluation_target_mismatch_when_response_is_absent():
    evidence = [EvidenceItem(
        id="I", evidence_class=EvidenceClass.DIRECT_OBSERVATION,
        text="IgnitionState remained ON throughout the complete evaluated interval.",
        source="Direct Observations / Trace", coverage_complete=True,
        signal_name="IgnitionState", signal_value="ON", observation_type=ObservationType.INTERVAL_STATE,
    )]
    req = RequirementAnalysis(
        requirement_id="REQ-1201",
        requirement_text="If IgnitionState is ON, CentralLockStatus shall be READY.",
        faithful_meaning="When IgnitionState is ON, CentralLockStatus must be READY.",
        relevance="Conditional state requirement.",
        normative_type=NormativeType.MANDATORY,
        applicability=Applicability.APPLICABLE,
        applicability_evidence_ids=["I"],
        applicability_condition="IgnitionState is ON",
        required_behavior="CentralLockStatus equals READY",
        evaluation_sufficiency=Sufficiency.INSUFFICIENT,
        missing_evaluation_evidence=[EvidenceNeed(
            element=RequirementElementType.RESPONSE,
            description="No observation of CentralLockStatus exists during the interval where IgnitionState is ON; observe CentralLockStatus = READY.",
        )],
    )
    semantic = SemanticAnalysis(affected_functionality="lock", evidence_inventory=evidence, requirements=[req])
    canonical = CanonicalCase(
        evidence_inventory=evidence,
        requirements=[{"requirement_id": req.requirement_id, "requirement_text": req.requirement_text}],
        requirement_language=[RequirementLanguageNormalization(
            requirement_id=req.requirement_id,
            applicability_any_of=[RequirementPredicateGroup(predicates=[RequirementPredicate(
                signal="IgnitionState", operator=PredicateOperator.EQ, value="ON", source_phrase="IgnitionState is ON"
            )])],
            required_behavior_signal="CentralLockStatus",
            required_behavior_operator=PredicateOperator.EQ,
            required_behavior_value="READY",
        )],
    )
    validated = DeterministicValidator().normalize_and_validate(semantic, canonical_case=canonical)
    assert not any(x.code == "EVALUATION_NEED_TARGET_MISMATCH" for x in validated.issues)


def test_v071_trigger_timestamp_need_is_deferred_until_trigger_decomposition_exists():
    req = RequirementAnalysis(
        requirement_id="REQ-1203",
        requirement_text="When DriverDoorRequest becomes OPEN, DriverDoorStatus shall become OPEN within 300 ms.",
        faithful_meaning="DriverDoorStatus must become OPEN within 300 ms after DriverDoorRequest becomes OPEN.",
        relevance="Timed response requirement.",
        normative_type=NormativeType.MANDATORY,
        applicability=Applicability.UNKNOWN,
        applicability_evidence_ids=[],
        applicability_condition="DriverDoorRequest transitions to OPEN",
        trigger="",
        required_behavior="DriverDoorStatus shall become OPEN",
        timing_constraint="within 300 ms",
        evaluation_sufficiency=Sufficiency.INSUFFICIENT,
        missing_applicability_evidence=[EvidenceNeed(
            element=RequirementElementType.APPLICABILITY,
            description="Observe whether DriverDoorRequest transitions to OPEN.",
        )],
        missing_evaluation_evidence=[
            EvidenceNeed(element=RequirementElementType.RESPONSE, description="Observe DriverDoorStatus = OPEN."),
            EvidenceNeed(element=RequirementElementType.TIMING, description="Provide timing sufficient to compare the response with the 300 ms limit."),
        ],
    )
    semantic = SemanticAnalysis(affected_functionality="door", evidence_inventory=[], requirements=[req])
    validated = DeterministicValidator().normalize_and_validate(semantic)
    codes = {x.code for x in validated.issues}
    assert "MISSING_TRIGGER_DECOMPOSITION" in codes
    assert "MISSING_TRIGGER_TIMESTAMP_NEED" not in codes


def test_v071_release_artifacts_exist_and_history_transition_is_documented():
    from pathlib import Path
    root = Path(__file__).resolve().parent.parent
    history = (root / "VERSION_HISTORY.md").read_text(encoding="utf-8")
    release = root / "docs" / "V0.7.1_RELEASE_NOTES.md"
    assert release.exists()
    assert "## v0.7.0 → v0.7.1" in history
    assert "Current release:** v1.8.5" in history
