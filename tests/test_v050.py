import json
from pathlib import Path

from rca_app.case_parser import DeterministicCaseParser
from rca_app.lmstudio_client import StructuredResponse
from rca_app.models import (
    ApiStats,
    Applicability,
    EvidenceClass,
    EvidenceItem,
    EvidenceNeed,
    EvaluationStatus,
    NormativeType,
    ObservationType,
    RepairRoute,
    RequirementAnalysis,
    RequirementElementType,
    RequirementPatch,
    RequirementPatchFields,
    RequirementPatchResponse,
    RequirementRepairResponse,
    SemanticAnalysis,
    SemanticReasoning,
    Sufficiency,
    ValidationIssue,
    ValidationSeverity,
)
from rca_app.pipeline import RCAPipeline
from rca_app.repair import DeterministicRepairEngine, RepairRouter
from rca_app.validator import DeterministicValidator
from tests.test_validator import make_test001


class FakeClient:
    def __init__(self, responses, name):
        self.responses = list(responses)
        self.calls = 0
        self.name = name

    def structured_chat(self, **kwargs):
        obj = self.responses[self.calls]
        self.calls += 1
        return StructuredResponse(
            parsed=obj,
            raw_json=json.dumps(obj.model_dump(mode="json")),
            stats=ApiStats(elapsed_seconds=0.01, model=self.name),
        )

    def structured_repair(self, **kwargs):
        return self.structured_chat(**kwargs)


def test_v050_snapshot_id_is_attached_to_following_observations():
    text = """
Snapshot ID: SNAP_A
IgnitionState = ON
FunctionStatus = INACTIVE
Observation Group: SNAP_B
WarningIndicator = OFF
"""
    items = DeterministicCaseParser()._parse_direct_observations(text)
    assert [x.observation_group for x in items] == ["SNAP_A", "SNAP_A", "SNAP_B"]


def _state_requirement(grouped: bool) -> SemanticAnalysis:
    group = "VERIFY_1" if grouped else ""
    return SemanticAnalysis(
        affected_functionality="Function X",
        evidence_inventory=[
            EvidenceItem(
                id="E1", evidence_class=EvidenceClass.DIRECT_OBSERVATION,
                text="IgnitionState = ON", source="Direct Observations / Trace",
                signal_name="IgnitionState", signal_value="ON",
                observation_type=ObservationType.STATE_SAMPLE, observation_group=group,
            ),
            EvidenceItem(
                id="E2", evidence_class=EvidenceClass.DIRECT_OBSERVATION,
                text="AvailabilityStatus remained AVAILABLE throughout the complete evaluated interval.",
                source="Direct Observations / Trace", signal_name="AvailabilityStatus", signal_value="AVAILABLE",
                observation_type=ObservationType.INTERVAL_STATE, coverage_complete=True,
            ),
            EvidenceItem(
                id="E3", evidence_class=EvidenceClass.DIRECT_OBSERVATION,
                text="FunctionStatus = INACTIVE", source="Direct Observations / Trace",
                signal_name="FunctionStatus", signal_value="INACTIVE",
                observation_type=ObservationType.STATE_SAMPLE, observation_group=group,
            ),
        ],
        requirements=[
            RequirementAnalysis(
                requirement_id="REQ-X",
                requirement_text="If IgnitionState is ON and AvailabilityStatus is AVAILABLE, FunctionStatus shall be ACTIVE.",
                faithful_meaning="When both conditions hold, FunctionStatus is required to be ACTIVE.",
                relevance="This requirement defines the required FunctionStatus state under the stated runtime condition.",
                normative_type=NormativeType.MANDATORY,
                applicability=Applicability.APPLICABLE,
                applicability_evidence_ids=["E1", "E2"],
                applicability_condition="IgnitionState is ON and AvailabilityStatus is AVAILABLE",
                required_behavior="FunctionStatus shall be ACTIVE",
                evaluation_evidence_ids=["E3"],
                evaluation_sufficiency=Sufficiency.SUFFICIENT_NONCONFORMANCE,
            )
        ],
    )


def test_v050_uncorrelated_point_samples_cannot_prove_state_violation():
    validated = DeterministicValidator().normalize_and_validate(_state_requirement(grouped=False))
    rr = validated.requirement_results[0]
    assert rr.analysis.applicability == Applicability.APPLICABLE
    assert rr.analysis.evaluation_sufficiency == Sufficiency.INSUFFICIENT
    assert rr.evaluation_status == EvaluationStatus.NOT_EVALUABLE
    assert any(x.code == "POINT_OBSERVATION_CORRELATION_MISSING" for x in validated.issues)


def test_v050_shared_snapshot_allows_point_state_violation():
    validated = DeterministicValidator().normalize_and_validate(_state_requirement(grouped=True))
    rr = validated.requirement_results[0]
    assert rr.analysis.applicability == Applicability.APPLICABLE
    assert rr.analysis.evaluation_sufficiency == Sufficiency.SUFFICIENT_NONCONFORMANCE
    assert rr.evaluation_status == EvaluationStatus.VIOLATED


def test_v050_positive_applicability_need_does_not_require_interval_scope():
    data = make_test001()
    req = data.requirements[2]
    req.missing_applicability_evidence = [
        EvidenceNeed(
            element=RequirementElementType.APPLICABILITY,
            description="Current-case INTERVAL_STATE establishing AvailabilityStatus was NOT_AVAILABLE over the case scope. A lone STATE_SAMPLE is insufficient.",
        )
    ]
    validated = DeterministicValidator().normalize_and_validate(data)
    reqv = validated.requirement_results[2].analysis
    text = " ".join(n.description for n in reqv.missing_applicability_evidence)
    assert "INTERVAL_STATE" not in text
    assert "relevant evaluation point" in text
    assert any(x.code == "POSITIVE_APPLICABILITY_SCOPE_NEED_NORMALIZED" for x in validated.issues)


def test_v050_minimum_evidence_preserves_interval_specificity():
    data = SemanticAnalysis(
        affected_functionality="Warning indicator",
        evidence_inventory=[
            EvidenceItem(
                id="A", evidence_class=EvidenceClass.DIRECT_OBSERVATION,
                text="AvailabilityStatus remained AVAILABLE throughout the complete evaluated interval.",
                source="Direct Observations / Trace", signal_name="AvailabilityStatus", signal_value="AVAILABLE",
                observation_type=ObservationType.INTERVAL_STATE, coverage_complete=True,
            ),
            EvidenceItem(
                id="W", evidence_class=EvidenceClass.DIRECT_OBSERVATION,
                text="WarningIndicator = OFF", source="Direct Observations / Trace",
                signal_name="WarningIndicator", signal_value="OFF", observation_type=ObservationType.STATE_SAMPLE,
            ),
        ],
        requirements=[
            RequirementAnalysis(
                requirement_id="REQ-W",
                requirement_text="If AvailabilityStatus is AVAILABLE, WarningIndicator shall be OFF.",
                faithful_meaning="When AvailabilityStatus is AVAILABLE, WarningIndicator is required to be OFF.",
                relevance="This requirement defines WarningIndicator state under AVAILABLE.",
                normative_type=NormativeType.MANDATORY,
                applicability=Applicability.APPLICABLE,
                applicability_evidence_ids=["A"],
                applicability_condition="AvailabilityStatus is AVAILABLE",
                required_behavior="WarningIndicator shall be OFF",
                evaluation_evidence_ids=["W"],
                evaluation_sufficiency=Sufficiency.INSUFFICIENT,
                missing_evaluation_evidence=[EvidenceNeed(
                    element=RequirementElementType.RESPONSE,
                    description="INTERVAL_STATE evidence confirming WarningIndicator remained OFF across the full interval is not supplied.",
                )],
            )
        ],
    )
    validated = DeterministicValidator().normalize_and_validate(data)
    minimum = "\n".join(validated.compliance_evidence)
    assert "INTERVAL_STATE / interval coverage" in minimum
    assert "WarningIndicator shall be OFF" in minimum


def test_v051_wrong_evaluation_bucket_is_fast_model_owned_not_deterministic():
    data = make_test001()
    issue = ValidationIssue(
        code="APPLICABILITY_NEED_IN_EVALUATION_BUCKET",
        severity=ValidationSeverity.ERROR,
        path="semantic.requirements[1].missing_evaluation_evidence[0]",
        message="wrong bucket",
    )
    repaired, applied = DeterministicRepairEngine().apply(data, [issue])
    assert applied == []
    assert repaired.model_dump(mode="json") == data.model_dump(mode="json")
    assert RepairRouter().route([issue], True) == RepairRoute.FAST_MODEL


def test_v050_repair_router_prefers_least_expensive_safe_route():
    det = ValidationIssue(code="MISSING_RESPONSE_EVALUATION_NEED", severity=ValidationSeverity.ERROR, path="semantic.requirements[0]", message="x")
    fast = ValidationIssue(code="CAUSAL_RELEVANCE_LANGUAGE", severity=ValidationSeverity.ERROR, path="semantic.requirements[0]", message="x")
    primary = ValidationIssue(code="MISSING_REQUIRED_BEHAVIOR", severity=ValidationSeverity.ERROR, path="semantic.requirements[0]", message="x")
    router = RepairRouter()
    assert router.route([det], True) == RepairRoute.DETERMINISTIC
    assert router.route([fast], True) == RepairRoute.FAST_MODEL
    assert router.route([primary], True) == RepairRoute.PRIMARY_MODEL


def test_v050_pipeline_uses_fast_model_for_local_semantic_repair():
    base = make_test001()
    bad = SemanticReasoning(
        affected_functionality=base.affected_functionality,
        requirements=[r.model_copy(deep=True) for r in base.requirements],
        historical_tickets=[], diagnostic_evidence_ids=[], hypotheses=[], case_validity_needs=[],
    )
    bad.requirements[0].faithful_meaning = "FunctionRequest may be accepted only if IgnitionState is ON."
    fast_response = RequirementPatchResponse(patches=[
        RequirementPatch(
            requirement_id="REQ-001",
            patch=RequirementPatchFields(
                faithful_meaning=base.requirements[0].faithful_meaning
            ),
        )
    ])
    primary = FakeClient([bad], "primary-27b")
    fast = FakeClient([fast_response], "fast-4b")
    case_text = (Path(__file__).resolve().parent.parent / "examples" / "TEST-001.txt").read_text(encoding="utf-8")
    result = RCAPipeline(primary, repair_client=fast, max_repair_passes=1).run(case_text)
    assert primary.calls == 1
    assert fast.calls == 1
    assert any(e.route == RepairRoute.FAST_MODEL for e in result.repair_log)
    assert result.attempts[-1].model_role == "FAST_REPAIR_PATCH"
