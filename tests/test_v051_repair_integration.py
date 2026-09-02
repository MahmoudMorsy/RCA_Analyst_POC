import json
from pathlib import Path

from rca_app.case_parser import DeterministicCaseParser
from rca_app.lmstudio_client import StructuredResponse
from rca_app.models import (
    ApiStats,
    Applicability,
    EvidenceNeed,
    NormativeType,
    RepairRoute,
    RequirementAnalysis,
    RequirementElementType,
    RequirementPatch,
    RequirementPatchFields,
    RequirementPatchResponse,
    SemanticAnalysis,
    SemanticReasoning,
    Sufficiency,
)
from rca_app.pipeline import RCAPipeline
from rca_app.repair import RepairRouter
from rca_app.validator import DeterministicValidator


def _tc2_req102_semantic():
    path = Path(__file__).resolve().parent.parent / "examples" / "TEST-002.txt"
    canonical = DeterministicCaseParser().parse(path.read_text(encoding="utf-8"))
    by_text = {e.text: e for e in canonical.evidence_inventory}
    availability = next(e for e in canonical.evidence_inventory if e.signal_name == "AvailabilityStatus")
    warning = next(e for e in canonical.evidence_inventory if e.signal_name == "WarningIndicator")
    semantic = SemanticAnalysis(
        affected_functionality="Function X",
        evidence_inventory=canonical.evidence_inventory,
        requirements=[
            RequirementAnalysis(
                requirement_id="REQ-102",
                requirement_text="If AvailabilityStatus is AVAILABLE, WarningIndicator shall be OFF.",
                faithful_meaning="Whenever AvailabilityStatus is AVAILABLE, WarningIndicator shall be OFF.",
                relevance="This requirement defines the WarningIndicator state under AVAILABLE.",
                normative_type=NormativeType.MANDATORY,
                applicability=Applicability.APPLICABLE,
                applicability_evidence_ids=[availability.id],
                applicability_condition="AvailabilityStatus is AVAILABLE",
                required_behavior="WarningIndicator shall be OFF",
                evaluation_evidence_ids=[warning.id],
                evaluation_sufficiency=Sufficiency.INSUFFICIENT,
                missing_evaluation_evidence=[EvidenceNeed(
                    element=RequirementElementType.OBSERVATION_INTERVAL,
                    description="Need AvailabilityStatus = AVAILABLE interval evidence to confirm state persistence before evaluating WarningIndicator.",
                )],
            )
        ],
    )
    return canonical, semantic


def test_v051_semantic_target_guard_rejects_reasking_applicability_interval():
    canonical, semantic = _tc2_req102_semantic()
    validated = DeterministicValidator().normalize_and_validate(semantic, canonical_case=canonical)
    critical = DeterministicValidator().critical_issues(validated)
    assert any(x.code == "EVALUATION_NEED_TARGET_MISMATCH" for x in critical)
    plan = RepairRouter().build_plan(validated.semantic, critical, fast_model_available=True)
    task = next(x for x in plan if x.issues[0].code == "EVALUATION_NEED_TARGET_MISMATCH")
    assert task.route == RepairRoute.FAST_MODEL
    assert task.allowed_fields == ["missing_evaluation_evidence"]


def test_v051_semantic_target_guard_accepts_response_interval_target():
    canonical, semantic = _tc2_req102_semantic()
    semantic.requirements[0].missing_evaluation_evidence = [EvidenceNeed(
        element=RequirementElementType.OBSERVATION_INTERVAL,
        description="Need interval evidence confirming WarningIndicator remains OFF while AvailabilityStatus is AVAILABLE.",
    )]
    validated = DeterministicValidator().normalize_and_validate(semantic, canonical_case=canonical)
    critical = DeterministicValidator().critical_issues(validated)
    assert not any(x.code == "EVALUATION_NEED_TARGET_MISMATCH" for x in critical)


def test_v051_fast_patch_rejects_unauthorized_fields():
    _, semantic = _tc2_req102_semantic()
    response = RequirementPatchResponse(patches=[RequirementPatch(
        requirement_id="REQ-102",
        patch=RequirementPatchFields(
            missing_evaluation_evidence=[EvidenceNeed(
                element=RequirementElementType.OBSERVATION_INTERVAL,
                description="Need interval evidence confirming WarningIndicator remains OFF.",
            )],
            trigger="AvailabilityStatus becomes AVAILABLE",
        ),
    )])
    try:
        RCAPipeline._apply_patch_response(
            semantic, response, "REQ-102", ["missing_evaluation_evidence"]
        )
    except ValueError as exc:
        assert "unauthorized" in str(exc).lower()
    else:
        raise AssertionError("Unauthorized trigger patch was accepted")


class _FakeClient:
    def __init__(self, chat_responses=None, repair_responses=None, name="fake"):
        self.chat_responses = list(chat_responses or [])
        self.repair_responses = list(repair_responses or [])
        self.chat_calls = 0
        self.repair_calls = 0
        self.name = name

    def structured_chat(self, **kwargs):
        obj = self.chat_responses[self.chat_calls]
        self.chat_calls += 1
        return StructuredResponse(
            parsed=obj,
            raw_json=json.dumps(obj.model_dump(mode="json")),
            stats=ApiStats(elapsed_seconds=0.01, model=self.name),
        )

    def structured_repair(self, **kwargs):
        obj = self.repair_responses[self.repair_calls]
        self.repair_calls += 1
        return StructuredResponse(
            parsed=obj,
            raw_json=json.dumps(obj.model_dump(mode="json")),
            stats=ApiStats(elapsed_seconds=0.01, model=self.name),
            transport="qwen35-manual",
        )


def test_v051_pipeline_can_retry_new_semantic_target_error_with_second_fast_patch():
    path = Path(__file__).resolve().parent.parent / "examples" / "TEST-002.txt"
    raw = path.read_text(encoding="utf-8")
    canonical = DeterministicCaseParser().parse(raw)
    availability = next(e for e in canonical.evidence_inventory if e.signal_name == "AvailabilityStatus")
    warning = next(e for e in canonical.evidence_inventory if e.signal_name == "WarningIndicator")
    ignition = next(e for e in canonical.evidence_inventory if e.signal_name == "IgnitionState")
    function_status = next(e for e in canonical.evidence_inventory if e.signal_name == "FunctionStatus")

    # Build a primary response where only REQ-102 has the original invalid trigger
    # bucket. REQ-101/103 are already valid enough for this routing test.
    req101 = RequirementAnalysis(
        requirement_id="REQ-101",
        requirement_text="If IgnitionState is ON and AvailabilityStatus is AVAILABLE, FunctionStatus shall be ACTIVE.",
        faithful_meaning="If IgnitionState is ON and AvailabilityStatus is AVAILABLE, FunctionStatus shall be ACTIVE.",
        relevance="This requirement defines the required FunctionStatus state under the stated condition.",
        normative_type=NormativeType.MANDATORY,
        applicability=Applicability.APPLICABLE,
        applicability_evidence_ids=[ignition.id, availability.id],
        applicability_condition="IgnitionState is ON and AvailabilityStatus is AVAILABLE",
        required_behavior="FunctionStatus shall be ACTIVE",
        evaluation_evidence_ids=[function_status.id],
        evaluation_sufficiency=Sufficiency.SUFFICIENT_NONCONFORMANCE,
    )
    req102 = RequirementAnalysis(
        requirement_id="REQ-102",
        requirement_text="If AvailabilityStatus is AVAILABLE, WarningIndicator shall be OFF.",
        faithful_meaning="Whenever AvailabilityStatus is AVAILABLE, WarningIndicator shall be OFF.",
        relevance="This requirement defines the required WarningIndicator state under AVAILABLE.",
        normative_type=NormativeType.MANDATORY,
        applicability=Applicability.APPLICABLE,
        applicability_evidence_ids=[availability.id],
        applicability_condition="AvailabilityStatus is AVAILABLE",
        required_behavior="WarningIndicator shall be OFF",
        evaluation_evidence_ids=[warning.id],
        evaluation_sufficiency=Sufficiency.INSUFFICIENT,
        missing_evaluation_evidence=[EvidenceNeed(
            element=RequirementElementType.TRIGGER,
            description="Need AvailabilityStatus = AVAILABLE trigger evidence before evaluating WarningIndicator.",
        )],
    )
    req103 = RequirementAnalysis(
        requirement_id="REQ-103",
        requirement_text="If AvailabilityStatus is NOT_AVAILABLE, FunctionStatus shall remain INACTIVE.",
        faithful_meaning="If AvailabilityStatus is NOT_AVAILABLE, FunctionStatus shall remain INACTIVE.",
        relevance="This requirement defines FunctionStatus persistence under NOT_AVAILABLE.",
        normative_type=NormativeType.MANDATORY,
        applicability=Applicability.NOT_APPLICABLE,
        applicability_evidence_ids=[availability.id],
        applicability_condition="AvailabilityStatus is NOT_AVAILABLE",
        required_behavior="FunctionStatus shall remain INACTIVE",
        observation_interval_requirement="Remain INACTIVE while the condition holds",
        evaluation_sufficiency=Sufficiency.NOT_REQUIRED,
    )
    primary_reasoning = SemanticReasoning(
        affected_functionality="Function X",
        requirements=[req101, req102, req103],
    )

    bad_target_patch = RequirementPatchResponse(patches=[RequirementPatch(
        requirement_id="REQ-102",
        patch=RequirementPatchFields(missing_evaluation_evidence=[EvidenceNeed(
            element=RequirementElementType.OBSERVATION_INTERVAL,
            description="Need AvailabilityStatus = AVAILABLE interval evidence to confirm state persistence before evaluating WarningIndicator.",
        )]),
    )])
    good_target_patch = RequirementPatchResponse(patches=[RequirementPatch(
        requirement_id="REQ-102",
        patch=RequirementPatchFields(missing_evaluation_evidence=[EvidenceNeed(
            element=RequirementElementType.OBSERVATION_INTERVAL,
            description="Need interval evidence confirming WarningIndicator remains OFF while AvailabilityStatus is AVAILABLE.",
        )]),
    )])

    primary = _FakeClient(chat_responses=[primary_reasoning], name="primary-27b")
    fast = _FakeClient(repair_responses=[bad_target_patch, good_target_patch], name="fast-4b")
    result = RCAPipeline(primary, repair_client=fast, max_repair_passes=1).run(raw)

    assert primary.chat_calls == 1
    assert fast.repair_calls == 2
    assert not RCAPipeline(primary).validator.critical_issues(result.validated)
    fast_codes = [code for e in result.repair_log if e.route == RepairRoute.FAST_MODEL for code in e.issue_codes]
    assert "NONEXISTENT_TRIGGER_IN_EVALUATION_BUCKET" in fast_codes
    assert "EVALUATION_NEED_TARGET_MISMATCH" in fast_codes
