from __future__ import annotations

import json
from pathlib import Path

from rca_app.config import AppConfig
from rca_app.hypothesis_review import HypothesisEpistemicGate
from rca_app.intake import IntakeRouteDecision
from rca_app.lmstudio_client import StructuredResponse
from rca_app.models import (
    ApiStats,
    Applicability,
    AtomicClaimExtraction,
    AtomicClaimExtractionSet,
    AtomicClaimKind,
    AtomicTimingAssessment,
    CanonicalAtomicClaim,
    CanonicalCase,
    EpistemicStrength,
    EvidenceClass,
    EvidenceItem,
    EvaluationStatus,
    HypothesisAnalysis,
    HypothesisEpistemicReview,
    HypothesisReviewAction,
    HypothesisReviewResponse,
    HypothesisSemanticType,
    HypothesisSupportBasis,
    IntakeContentClassification,
    IntakeField,
    IntakeRequirement,
    NormativeType,
    ObservationType,
    PredicateOperator,
    RCASynthesisReasoning,
    RequirementAnalysis,
    RequirementLanguageNormalization,
    RequirementLanguageNormalizationSet,
    RequirementPredicate,
    RequirementPredicateGroup,
    RequirementReasoningPhase,
    RequirementSource,
    ReviewEvidenceSufficiency,
    SemanticAnalysis,
    SourceAvailability,
    SourceAvailabilityDecision,
    SourceAvailabilityNormalization,
    Sufficiency,
)
from rca_app.pipeline import RCAPipeline
from rca_app.semantic_preprocessing import FastSemanticPreprocessor
from rca_app.validator import DeterministicValidator
from tests.test_validator import make_test001


def _resp(obj, model="fake"):
    return StructuredResponse(
        parsed=obj,
        raw_json=json.dumps(obj.model_dump(mode="json")),
        stats=ApiStats(elapsed_seconds=0.01, model=model),
        transport="openai-chat",
    )


class RecordingPrimary:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []
        self.model = "primary-27b"

    def structured_chat(self, **kwargs):
        self.calls.append(kwargs)
        return _resp(self.responses.pop(0), self.model)


class EmptyFast:
    model = "fast-4b"

    def structured_repair(self, **kwargs):
        raise AssertionError("This client should not be called in this test")


def test_v080_config_defaults_enable_adaptive_semantic_compiler_architecture():
    cfg = AppConfig()
    assert cfg.semantic_preparation_enabled is True
    assert cfg.semantic_preparation_max_tokens == 6000
    assert cfg.semantic_arbitration_enabled is True
    assert cfg.rca_synthesis_enabled is True
    # Legacy Phase-A controls remain loadable for v0.7 compatibility only.
    assert cfg.primary_large_case_max_tokens == 16000
    assert cfg.primary_large_case_requirement_threshold == 8
    assert cfg.primary_phase_a_chunk_size == 6
    assert cfg.fast_source_availability_max_tokens == 900
    assert cfg.fast_content_classification_max_tokens == 2800
    assert cfg.fast_atomic_claim_enabled is False
    assert cfg.fast_requirement_language_enabled is False
    assert cfg.fast_hypothesis_review_enabled is True
    assert cfg.fast_final_review_enabled is False


def test_v070_absence_meaning_is_llm_owned_python_only_enforces_structure():
    raw = "CURRENT BZD / DIAGNOSTICS\nNot available.\nSYSTEM REQUIREMENTS\nREQ-1\nIf X is ON, Y shall be ON."
    availability = SourceAvailabilityNormalization(
        requirements=SourceAvailabilityDecision(availability=SourceAvailability.PRESENT),
        diagnostics=SourceAvailabilityDecision(
            availability=SourceAvailability.ABSENT,
            availability_statement=IntakeField(value="Not available.", source_span="Not available."),
        ),
    )
    # Simulate a noisy content classifier that still put the absence sentence in a block.
    content = IntakeContentClassification(
        requirements=[IntakeRequirement(
            requirement_id="REQ-1",
            requirement_text="If X is ON, Y shall be ON.",
            source_span="REQ-1\nIf X is ON, Y shall be ON.",
        )],
        diagnostic_blocks=[IntakeField(value="Not available.", source_span="Not available.")],
    )
    normalized = FastSemanticPreprocessor.combine_intake(raw, availability, content)
    assert normalized.diagnostics.availability == SourceAvailability.ABSENT
    assert normalized.diagnostics.blocks == []
    assert normalized.diagnostics.availability_statement.source_span == "Not available."


def _tc4_semantic_and_canonical():
    evidence = [
        EvidenceItem(id="A", evidence_class=EvidenceClass.DIRECT_OBSERVATION, text="AvailabilityStatus = AVAILABLE", source="Direct Observations / Trace", signal_name="AvailabilityStatus", signal_value="AVAILABLE", observation_type=ObservationType.STATE_SAMPLE, observation_group="SNAP_B"),
        EvidenceItem(id="R", evidence_class=EvidenceClass.DIRECT_OBSERVATION, text="FunctionStatus = INACTIVE", source="Direct Observations / Trace", signal_name="FunctionStatus", signal_value="INACTIVE", observation_type=ObservationType.STATE_SAMPLE, observation_group="SNAP_B"),
    ]
    req = RequirementAnalysis(
        requirement_id="REQ-302",
        requirement_text="If AvailabilityStatus is NOT_AVAILABLE, FunctionStatus shall remain INACTIVE.",
        faithful_meaning="When AvailabilityStatus is NOT_AVAILABLE, FunctionStatus must remain INACTIVE.",
        relevance="It defines FunctionStatus behavior under the NOT_AVAILABLE condition.",
        normative_type=NormativeType.MANDATORY,
        applicability=Applicability.UNKNOWN,
        applicability_evidence_ids=[],
        applicability_condition="AvailabilityStatus is NOT_AVAILABLE",
        required_behavior="FunctionStatus shall remain INACTIVE",
        observation_interval_requirement="while the condition applies",
        evaluation_evidence_ids=["R"],
        evaluation_sufficiency=Sufficiency.INSUFFICIENT,
    )
    semantic = SemanticAnalysis(affected_functionality="Function X", evidence_inventory=evidence, requirements=[req])
    canonical = CanonicalCase(
        requirements=[RequirementSource(requirement_id=req.requirement_id, requirement_text=req.requirement_text)],
        evidence_inventory=evidence,
        requirement_language=[RequirementLanguageNormalization(
            requirement_id="REQ-302",
            normative_type_hint=NormativeType.MANDATORY,
            applicability_any_of=[RequirementPredicateGroup(predicates=[RequirementPredicate(
                signal="AvailabilityStatus", operator=PredicateOperator.EQ, value="NOT_AVAILABLE", source_phrase="AvailabilityStatus is NOT_AVAILABLE"
            )])],
            required_behavior_signal="FunctionStatus",
            required_behavior_operator=PredicateOperator.EQ,
            required_behavior_value="INACTIVE",
            persistence_required=True,
        )],
    )
    return semantic, canonical


def test_v070_tc4_contextual_evaluation_evidence_uses_llm_normalized_predicate():
    semantic, canonical = _tc4_semantic_and_canonical()
    validated = DeterministicValidator().normalize_and_validate(semantic, canonical_case=canonical)
    req = validated.requirement_results[0].analysis
    assert "R" not in req.evaluation_evidence_ids
    assert any(x.code == "EVALUATION_CONTEXT_APPLICABILITY_FALSE_REMOVED" for x in validated.issues)


def _tc8_semantic_and_canonical_with_atomic_claims():
    evidence = [
        EvidenceItem(id="REP", evidence_class=EvidenceClass.REPORTED_OBSERVATION, text="The PREPARED transition was timely, but the ACTIVE transition was late.", source="Reported Test Result"),
        EvidenceItem(id="Q0", evidence_class=EvidenceClass.DIRECT_OBSERVATION, text="39.900 s FunctionRequest = INACTIVE", source="Direct Observations / Trace", timestamped=True, timestamp_seconds=39.9, event_coverage_complete=True, clock_id="TRACE_C", signal_name="FunctionRequest", signal_value="INACTIVE", observation_type=ObservationType.STATE_SAMPLE),
        EvidenceItem(id="S0", evidence_class=EvidenceClass.DIRECT_OBSERVATION, text="39.900 s FunctionStatus = INACTIVE", source="Direct Observations / Trace", timestamped=True, timestamp_seconds=39.9, event_coverage_complete=True, clock_id="TRACE_C", signal_name="FunctionStatus", signal_value="INACTIVE", observation_type=ObservationType.STATE_SAMPLE),
        EvidenceItem(id="Q1", evidence_class=EvidenceClass.DIRECT_OBSERVATION, text="40.000 s FunctionRequest = ACTIVE", source="Direct Observations / Trace", timestamped=True, timestamp_seconds=40.0, event_coverage_complete=True, clock_id="TRACE_C", signal_name="FunctionRequest", signal_value="ACTIVE", observation_type=ObservationType.TRANSITION, transition_from="INACTIVE", transition_to="ACTIVE"),
        EvidenceItem(id="P", evidence_class=EvidenceClass.DIRECT_OBSERVATION, text="40.150 s FunctionStatus = PREPARED", source="Direct Observations / Trace", timestamped=True, timestamp_seconds=40.15, event_coverage_complete=True, clock_id="TRACE_C", signal_name="FunctionStatus", signal_value="PREPARED", observation_type=ObservationType.TRANSITION, transition_from="INACTIVE", transition_to="PREPARED"),
        EvidenceItem(id="A", evidence_class=EvidenceClass.DIRECT_OBSERVATION, text="40.520 s FunctionStatus = ACTIVE", source="Direct Observations / Trace", timestamped=True, timestamp_seconds=40.52, event_coverage_complete=True, clock_id="TRACE_C", signal_name="FunctionStatus", signal_value="ACTIVE", observation_type=ObservationType.TRANSITION, transition_from="PREPARED", transition_to="ACTIVE"),
    ]
    req1 = RequirementAnalysis(
        requirement_id="REQ-701", requirement_text="When FunctionRequest becomes ACTIVE, FunctionStatus shall become PREPARED within 200 ms.",
        faithful_meaning="FunctionStatus must become PREPARED within 200 ms after the request transition.", relevance="Direct timing requirement.", normative_type=NormativeType.MANDATORY,
        applicability=Applicability.APPLICABLE, applicability_evidence_ids=["Q1"], trigger="FunctionRequest becomes ACTIVE", required_behavior="FunctionStatus shall become PREPARED", timing_constraint="within 200 ms", evaluation_evidence_ids=["P"], evaluation_sufficiency=Sufficiency.SUFFICIENT_CONFORMANCE,
    )
    req2 = RequirementAnalysis(
        requirement_id="REQ-702", requirement_text="When FunctionStatus becomes PREPARED, FunctionStatus shall become ACTIVE within 300 ms.",
        faithful_meaning="FunctionStatus must become ACTIVE within 300 ms after PREPARED.", relevance="Direct timing requirement.", normative_type=NormativeType.MANDATORY,
        applicability=Applicability.APPLICABLE, applicability_evidence_ids=["P"], trigger="FunctionStatus becomes PREPARED", required_behavior="FunctionStatus shall become ACTIVE", timing_constraint="within 300 ms", evaluation_evidence_ids=["A"], evaluation_sufficiency=Sufficiency.SUFFICIENT_NONCONFORMANCE,
    )
    semantic = SemanticAnalysis(affected_functionality="two-stage activation", evidence_inventory=evidence, requirements=[req1, req2])
    canonical = CanonicalCase(
        evidence_inventory=evidence,
        requirements=[RequirementSource(requirement_id=r.requirement_id, requirement_text=r.requirement_text) for r in [req1, req2]],
        atomic_claims=[
            CanonicalAtomicClaim(claim_id="C1", parent_evidence_id="REP", source_category="REPORTED_OBSERVATION", source_span=evidence[0].text, claim_text="The PREPARED transition was timely.", claim_kind=AtomicClaimKind.TIMING, subject="FunctionStatus", object_value="PREPARED", timing_assessment=AtomicTimingAssessment.WITHIN_LIMIT),
            CanonicalAtomicClaim(claim_id="C2", parent_evidence_id="REP", source_category="REPORTED_OBSERVATION", source_span=evidence[0].text, claim_text="The ACTIVE transition was late.", claim_kind=AtomicClaimKind.TIMING, subject="FunctionStatus", object_value="ACTIVE", timing_assessment=AtomicTimingAssessment.EXCEEDS_LIMIT),
        ],
    )
    return semantic, canonical


def test_v070_tc8_atomic_claims_prevent_false_reported_direct_conflicts():
    semantic, canonical = _tc8_semantic_and_canonical_with_atomic_claims()
    validated = DeterministicValidator().normalize_and_validate(semantic, canonical_case=canonical)
    statuses = {x.analysis.requirement_id: x.evaluation_status for x in validated.requirement_results}
    assert statuses["REQ-701"] == EvaluationStatus.SATISFIED
    assert statuses["REQ-702"] == EvaluationStatus.VIOLATED
    assert validated.evidence_conflicts == []
    assert not any(x.code == "EVIDENCE_SOURCE_CONFLICT_IDENTIFIED" for x in validated.issues)


def test_v070_large_chunker_keeps_explicit_requirement_relationship_component_together():
    reqs = []
    for i in range(1, 10):
        text = f"If X{i} is ON, Y{i} shall be ON."
        if i == 2:
            text = "Relationship: REQ-2 is a child of REQ-1. If X2 is ON, Y2 shall be ON."
        if i == 3:
            text = "Relationship: REQ-3 is a child of REQ-1. If X3 is ON, Y3 shall be ON."
        reqs.append(RequirementSource(requirement_id=f"REQ-{i}", requirement_text=text))
    pipe = RCAPipeline(EmptyFast(), primary_large_case_requirement_threshold=8, primary_phase_a_chunk_size=3)
    chunks = pipe._build_requirement_chunks(CanonicalCase(requirements=reqs))
    related = next(chunk for chunk in chunks if "REQ-1" in chunk)
    assert set(related) == {"REQ-1", "REQ-2", "REQ-3"}
    assert all(len(chunk) <= 3 for chunk in chunks)


def test_v070_phase_b_merge_cannot_change_authoritative_requirement_objects():
    source = make_test001()
    canonical = CanonicalCase(
        requirements=[RequirementSource(requirement_id=r.requirement_id, requirement_text=r.requirement_text) for r in source.requirements],
        evidence_inventory=source.evidence_inventory,
    )
    authoritative = source.model_copy(deep=True)
    synthesis = RCASynthesisReasoning(affected_functionality="RCA synthesis", hypotheses=[])
    merged = RCAPipeline._merge_rca_synthesis(authoritative, canonical, synthesis)
    assert [r.model_dump(mode="json") for r in merged.requirements] == [r.model_dump(mode="json") for r in authoritative.requirements]
    assert merged.affected_functionality == "RCA synthesis"


def test_v070_hypothesis_epistemic_gate_drops_compliance_restatement_and_can_rewrite_overclaim():
    data = make_test001()
    data.hypotheses = [HypothesisAnalysis(
        hypothesis="FunctionStatus failed the requirement.",
        support_basis=HypothesisSupportBasis.CURRENT_CASE_MECHANISM_MATCH,
        supporting_evidence_ids=["E1"],
        confidence="LOW",
    )]
    validator = DeterministicValidator()
    validated = validator.normalize_and_validate(data)
    review = HypothesisReviewResponse(reviews=[HypothesisEpistemicReview(
        hypothesis_index=0,
        semantic_type=HypothesisSemanticType.COMPLIANCE_RESTATEMENT,
        epistemic_strength=EpistemicStrength.POSSIBLE,
        support_sufficiency=ReviewEvidenceSufficiency.INSUFFICIENT,
        action=HypothesisReviewAction.DROP,
    )])
    dropped, accepted, rejected = HypothesisEpistemicGate.apply(validated, review, validator, None)
    assert dropped.semantic.hypotheses == []
    assert accepted == ["DROP hypothesis[0]"]
    assert not rejected

    data.hypotheses = [HypothesisAnalysis(
        hypothesis="Communication loss caused the failure.",
        support_basis=HypothesisSupportBasis.CURRENT_CASE_MECHANISM_MATCH,
        supporting_evidence_ids=["E1"],
        confidence="LOW",
    )]
    validated = validator.normalize_and_validate(data)
    review = HypothesisReviewResponse(reviews=[HypothesisEpistemicReview(
        hypothesis_index=0,
        semantic_type=HypothesisSemanticType.MECHANISM_CANDIDATE,
        epistemic_strength=EpistemicStrength.SUPPORTED_CANDIDATE,
        support_sufficiency=ReviewEvidenceSufficiency.SUFFICIENT,
        action=HypothesisReviewAction.REWRITE,
        replacement_hypothesis="Communication loss is a supported candidate mechanism for the observed failure.",
    )])
    rewritten, accepted, rejected = HypothesisEpistemicGate.apply(validated, review, validator, None)
    assert rewritten.semantic.hypotheses[0].hypothesis.startswith("Communication loss is a supported candidate")
    assert accepted == ["REWRITE hypothesis[0]"]
    assert not rejected


def test_v070_live_pipeline_exposes_phase_a_phase_b_and_new_fast_stages():
    raw = (Path(__file__).resolve().parent.parent / "examples" / "TEST-001.txt").read_text(encoding="utf-8")
    semantic = make_test001()
    phase_a = RequirementReasoningPhase(requirements=semantic.requirements)
    phase_b = RCASynthesisReasoning(affected_functionality=semantic.affected_functionality)
    primary = RecordingPrimary([phase_a, phase_b])
    events = []
    result = RCAPipeline(primary, max_repair_passes=0).run(raw, trace=events.append)
    assert result.validated.requirement_results
    stage_ids = {e["stage_id"] for e in events}
    expected = {
        "01_user_input", "02_intake_routing", "03_source_availability", "04_content_classification",
        "05_canonicalization", "06_atomic_claims", "07_requirement_language",
        "08_phase_a_requirement_reasoning", "08_phase_a_chunk_1", "09_requirement_validation",
        "10_requirement_repair", "11_authoritative_compliance", "12_phase_b_rca_synthesis",
        "13_rca_validation_repair", "14_hypothesis_review", "15_final_wording_review",
        "16_python_final_gate", "17_report_formatter", "18_final_output",
    }
    assert expected.issubset(stage_ids)
    phase_b_event = next(e for e in events if e["stage_id"] == "12_phase_b_rca_synthesis" and e["status"] == "running")
    assert "read-only" in phase_b_event["summary"].lower()


def test_v070_large_case_phase_a_uses_16000_output_budget():
    # Inject a deterministic preview directly so the test measures routing/budget behavior, not parser formatting.
    semantic = make_test001()
    reqs = []
    analyses = []
    for i in range(8):
        base = semantic.requirements[0].model_copy(deep=True)
        base.requirement_id = f"REQ-L{i+1}"
        base.requirement_text = f"If X{i+1} is ON, Y{i+1} may be accepted."
        base.faithful_meaning = f"When X{i+1} is ON, Y{i+1} is permitted."
        base.relevance = "Permissive requirement."
        base.normative_type = NormativeType.PERMISSIVE
        base.applicability = Applicability.UNKNOWN
        base.applicability_condition = f"X{i+1} is ON"
        base.required_behavior = f"Y{i+1} may be accepted"
        base.missing_applicability_evidence = []
        analyses.append(base)
        reqs.append(RequirementSource(requirement_id=base.requirement_id, requirement_text=base.requirement_text))
    canonical = CanonicalCase(ticket_id="LARGE", requirements=reqs, evidence_inventory=[])
    phase_a_chunks = [RequirementReasoningPhase(requirements=analyses[:6]), RequirementReasoningPhase(requirements=analyses[6:])]
    phase_b = RCASynthesisReasoning(affected_functionality="large")
    primary = RecordingPrimary(phase_a_chunks + [phase_b])
    pipe = RCAPipeline(primary, max_repair_passes=0, primary_large_case_requirement_threshold=8, primary_phase_a_chunk_size=6)
    pipe.intake_router.decide = lambda *a, **k: IntakeRouteDecision(False, "test", canonical)
    result = pipe.run("synthetic large case")
    assert result.validated.requirement_results
    phase_a_calls = [c for c in primary.calls if c["schema_name"] == "rca_requirement_reasoning_phase_a_v070"]
    assert len(phase_a_calls) == 2
    assert all(c["max_tokens_override"] == 16000 for c in phase_a_calls)
    phase_b_call = next(c for c in primary.calls if c["schema_name"] == "rca_phase_b_synthesis_v070")
    assert phase_b_call.get("max_tokens_override") is None


def test_v070_release_artifacts_exist_and_history_transition_is_documented():
    root = Path(__file__).resolve().parent.parent
    history = (root / "VERSION_HISTORY.md").read_text(encoding="utf-8")
    release = root / "docs" / "V0.7.0_RELEASE_NOTES.md"
    assert release.exists()
    assert "## v0.6.5 → v0.7.0" in history
