from pathlib import Path

from rca_app.case_parser import DeterministicCaseParser
from rca_app.models import (
    Applicability,
    EvaluationStatus,
    EvidenceItem,
    EvidenceClass,
    NormativeType,
    ObservationType,
    RequirementAnalysis,
    RequirementElementType,
    SemanticAnalysis,
    Sufficiency,
)
from rca_app.validator import DeterministicValidator


def _conditional_state_semantic(response_observation_type: ObservationType, response_value: str, sufficiency: Sufficiency):
    return SemanticAnalysis(
        affected_functionality="Warning indicator",
        evidence_inventory=[
            EvidenceItem(
                id="A",
                evidence_class=EvidenceClass.DIRECT_OBSERVATION,
                text="AvailabilityStatus remained AVAILABLE throughout the complete evaluated interval.",
                source="Direct Observations / Trace",
                signal_name="AvailabilityStatus",
                signal_value="AVAILABLE",
                observation_type=ObservationType.INTERVAL_STATE,
                coverage_complete=True,
                observation_group="VERIFY_POINT_1",
            ),
            EvidenceItem(
                id="W",
                evidence_class=EvidenceClass.DIRECT_OBSERVATION,
                text=f"WarningIndicator = {response_value}" if response_observation_type == ObservationType.STATE_SAMPLE else f"WarningIndicator remained {response_value} throughout the complete evaluated interval.",
                source="Direct Observations / Trace",
                signal_name="WarningIndicator",
                signal_value=response_value,
                observation_type=response_observation_type,
                coverage_complete=response_observation_type == ObservationType.INTERVAL_STATE,
                observation_group="VERIFY_POINT_1",
            ),
        ],
        requirements=[
            RequirementAnalysis(
                requirement_id="REQ-102",
                requirement_text="If AvailabilityStatus is AVAILABLE, WarningIndicator shall be OFF.",
                faithful_meaning="If AvailabilityStatus is AVAILABLE, WarningIndicator shall be OFF.",
                relevance="This requirement defines WarningIndicator state while AvailabilityStatus is AVAILABLE.",
                normative_type=NormativeType.MANDATORY,
                applicability=Applicability.APPLICABLE,
                applicability_evidence_ids=["A"],
                applicability_condition="AvailabilityStatus is AVAILABLE",
                required_behavior="WarningIndicator shall be OFF",
                evaluation_evidence_ids=["W"],
                evaluation_sufficiency=sufficiency,
            )
        ],
    )


def test_v052_interval_applicability_point_match_cannot_prove_conformance():
    data = _conditional_state_semantic(
        ObservationType.STATE_SAMPLE,
        "OFF",
        Sufficiency.SUFFICIENT_CONFORMANCE,
    )
    validated = DeterministicValidator().normalize_and_validate(data)
    rr = validated.requirement_results[0]
    assert rr.analysis.evaluation_sufficiency == Sufficiency.INSUFFICIENT
    assert rr.evaluation_status == EvaluationStatus.NOT_EVALUABLE
    assert any(
        n.element == RequirementElementType.OBSERVATION_INTERVAL
        and "WarningIndicator" in n.description
        for n in rr.analysis.missing_evaluation_evidence
    )
    assert any(x.code == "STATE_CONFORMANCE_COVERAGE_INSUFFICIENT" for x in validated.issues)


def test_v052_interval_applicability_interval_match_can_prove_conformance():
    data = _conditional_state_semantic(
        ObservationType.INTERVAL_STATE,
        "OFF",
        Sufficiency.SUFFICIENT_CONFORMANCE,
    )
    validated = DeterministicValidator().normalize_and_validate(data)
    rr = validated.requirement_results[0]
    assert rr.analysis.evaluation_sufficiency == Sufficiency.SUFFICIENT_CONFORMANCE
    assert rr.evaluation_status == EvaluationStatus.SATISFIED
    assert not any(x.code == "STATE_CONFORMANCE_COVERAGE_INSUFFICIENT" for x in validated.issues)


def test_v052_interval_applicability_point_counterexample_still_proves_violation():
    data = _conditional_state_semantic(
        ObservationType.STATE_SAMPLE,
        "ON",
        Sufficiency.SUFFICIENT_NONCONFORMANCE,
    )
    # Required behavior remains OFF, so the point observation is a counterexample.
    validated = DeterministicValidator().normalize_and_validate(data)
    rr = validated.requirement_results[0]
    assert rr.analysis.evaluation_sufficiency == Sufficiency.SUFFICIENT_NONCONFORMANCE
    assert rr.evaluation_status == EvaluationStatus.VIOLATED
    assert not any(x.code == "STATE_CONFORMANCE_COVERAGE_INSUFFICIENT" for x in validated.issues)


def test_v052_tc2_expected_statuses_from_validated_semantics():
    raw = (Path(__file__).resolve().parent.parent / "examples" / "TEST-002.txt").read_text(encoding="utf-8")
    canonical = DeterministicCaseParser().parse(raw)
    by_signal = {e.signal_name: e for e in canonical.evidence_inventory if e.signal_name}
    reported = next(e for e in canonical.evidence_inventory if e.evidence_class == EvidenceClass.REPORTED_OBSERVATION)

    semantic = SemanticAnalysis(
        affected_functionality="Function X activation state",
        evidence_inventory=canonical.evidence_inventory,
        requirements=[
            RequirementAnalysis(
                requirement_id="REQ-101",
                requirement_text="If IgnitionState is ON and AvailabilityStatus is AVAILABLE, FunctionStatus shall be ACTIVE.",
                faithful_meaning="If both conditions hold, FunctionStatus shall be ACTIVE.",
                relevance="Primary activation-state obligation.",
                normative_type=NormativeType.MANDATORY,
                applicability=Applicability.APPLICABLE,
                applicability_evidence_ids=[by_signal["IgnitionState"].id, by_signal["AvailabilityStatus"].id],
                applicability_condition="IgnitionState is ON and AvailabilityStatus is AVAILABLE",
                required_behavior="FunctionStatus shall be ACTIVE",
                evaluation_evidence_ids=[by_signal["FunctionStatus"].id, reported.id],
                evaluation_sufficiency=Sufficiency.SUFFICIENT_NONCONFORMANCE,
            ),
            RequirementAnalysis(
                requirement_id="REQ-102",
                requirement_text="If AvailabilityStatus is AVAILABLE, WarningIndicator shall be OFF.",
                faithful_meaning="If AvailabilityStatus is AVAILABLE, WarningIndicator shall be OFF.",
                relevance="Warning state under AVAILABLE.",
                normative_type=NormativeType.MANDATORY,
                applicability=Applicability.APPLICABLE,
                applicability_evidence_ids=[by_signal["AvailabilityStatus"].id],
                applicability_condition="AvailabilityStatus is AVAILABLE",
                required_behavior="WarningIndicator shall be OFF",
                evaluation_evidence_ids=[by_signal["WarningIndicator"].id],
                evaluation_sufficiency=Sufficiency.SUFFICIENT_CONFORMANCE,
            ),
            RequirementAnalysis(
                requirement_id="REQ-103",
                requirement_text="If AvailabilityStatus is NOT_AVAILABLE, FunctionStatus shall remain INACTIVE.",
                faithful_meaning="If AvailabilityStatus is NOT_AVAILABLE, FunctionStatus shall remain INACTIVE.",
                relevance="Boundary requirement under NOT_AVAILABLE.",
                normative_type=NormativeType.MANDATORY,
                applicability=Applicability.NOT_APPLICABLE,
                applicability_evidence_ids=[by_signal["AvailabilityStatus"].id],
                applicability_condition="AvailabilityStatus is NOT_AVAILABLE",
                required_behavior="FunctionStatus shall remain INACTIVE",
                observation_interval_requirement="Persist while NOT_AVAILABLE",
                evaluation_sufficiency=Sufficiency.NOT_REQUIRED,
            ),
        ],
    )
    validated = DeterministicValidator().normalize_and_validate(semantic, canonical_case=canonical)
    statuses = {rr.analysis.requirement_id: rr.evaluation_status for rr in validated.requirement_results}
    assert statuses == {
        "REQ-101": EvaluationStatus.VIOLATED,
        "REQ-102": EvaluationStatus.NOT_EVALUABLE,
        "REQ-103": EvaluationStatus.NO_COMPLIANCE_VERDICT,
    }


def test_v052_batch_worker_is_strictly_sequential_by_construction():
    # Keep this GUI architecture test dependency-free: CI may intentionally run
    # validator tests without installing the optional desktop runtime.
    source = (Path(__file__).resolve().parent.parent / "rca_app" / "gui.py").read_text(encoding="utf-8")
    assert "class BatchAnalysisWorker" in source
    assert "for index, (case_id, raw_case) in enumerate(self.cases, start=1):" in source
    assert "pipeline = _build_pipeline(self.config, self.cancellation_token)" in source
    assert "ThreadPoolExecutor" not in source
    assert "ProcessPoolExecutor" not in source
    assert "QtConcurrent" not in source
