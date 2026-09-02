import json
from pathlib import Path

import pytest

from rca_app.case_parser import DeterministicCaseParser
from rca_app.intake import IntakeCanonicalizer, IntakeRouter
from rca_app.lmstudio_client import StructuredResponse
from rca_app.models import (
    ApiStats,
    Applicability,
    EvidenceNeed,
    IntakeField,
    IntakeNormalization,
    IntakeRequirement,
    IntakeRequirementSection,
    IntakeSourceSection,
    LinguisticReviewFinding,
    LinguisticReviewResponse,
    NormativeType,
    RelevanceWordingPatch,
    RequirementAnalysis,
    RequirementElementType,
    SemanticReasoning,
    SourceAvailability,
    Sufficiency,
)
from rca_app.pipeline import RCAPipeline
from tests.test_validator import make_test001


class FakeStructuredClient:
    def __init__(self, chat=None, repair=None, name="fake"):
        self.chat = list(chat or [])
        self.repair = list(repair or [])
        self.chat_calls = 0
        self.repair_calls = 0
        self.model = name

    def structured_chat(self, **kwargs):
        obj = self.chat[self.chat_calls]
        self.chat_calls += 1
        return StructuredResponse(
            parsed=obj,
            raw_json=json.dumps(obj.model_dump(mode="json")),
            stats=ApiStats(elapsed_seconds=0.01, model=self.model),
            transport="openai-chat",
        )

    def structured_repair(self, **kwargs):
        obj = self.repair[self.repair_calls]
        self.repair_calls += 1
        return StructuredResponse(
            parsed=obj,
            raw_json=json.dumps(obj.model_dump(mode="json")),
            stats=ApiStats(elapsed_seconds=0.01, model=self.model),
            transport="qwen35-manual",
        )


def test_v060_clean_template_bypasses_fast_intake():
    raw = (Path(__file__).resolve().parent.parent / "examples" / "TEST-001.txt").read_text(encoding="utf-8")
    parser = DeterministicCaseParser()
    decision = IntakeRouter(parser).decide(raw, mode="auto", fast_available=True)
    assert decision.use_fast_model is False
    assert decision.deterministic_preview.requirements


def _messy_case_and_intake():
    raw = """TEST-MESSY-001
Late Function X activation
Engineer note: FunctionStatus came active later than expected.
Do this: Set FunctionRequest to ACTIVE.
Observed: FunctionStatus became ACTIVE later than expected.
REQ-401 When FunctionRequest becomes ACTIVE, FunctionStatus shall become ACTIVE within 500 ms.
Trace dump:
Clock: TRACE_B
29.900 s FunctionRequest = INACTIVE
30.000 s FunctionRequest = ACTIVE
30.000 s FunctionStatus = INACTIVE
30.700 s FunctionStatus = ACTIVE
""".strip()
    intake = IntakeNormalization(
        ticket_id=IntakeField(value="TEST-MESSY-001", source_span="TEST-MESSY-001"),
        title=IntakeField(value="Late Function X activation", source_span="Late Function X activation"),
        description=IntakeField(
            value="Engineer note: FunctionStatus came active later than expected.",
            source_span="Engineer note: FunctionStatus came active later than expected.",
        ),
        test_steps=[IntakeField(
            value="Do this: Set FunctionRequest to ACTIVE.",
            source_span="Do this: Set FunctionRequest to ACTIVE.",
        )],
        reported_results=[IntakeField(
            value="FunctionStatus became ACTIVE later than expected.",
            source_span="Observed: FunctionStatus became ACTIVE later than expected.",
        )],
        requirements=IntakeRequirementSection(
            availability=SourceAvailability.PRESENT,
            items=[IntakeRequirement(
                requirement_id="REQ-401",
                requirement_text="When FunctionRequest becomes ACTIVE, FunctionStatus shall become ACTIVE within 500 ms.",
                source_span="REQ-401 When FunctionRequest becomes ACTIVE, FunctionStatus shall become ACTIVE within 500 ms.",
            )],
        ),
        trace=IntakeSourceSection(
            availability=SourceAvailability.PRESENT,
            blocks=[IntakeField(
                value="",
                source_span=(
                    "Clock: TRACE_B\n"
                    "29.900 s FunctionRequest = INACTIVE\n"
                    "30.000 s FunctionRequest = ACTIVE\n"
                    "30.000 s FunctionStatus = INACTIVE\n"
                    "30.700 s FunctionStatus = ACTIVE"
                ),
            )],
        ),
    )
    return raw, intake


def test_v060_fast_intake_sections_messy_input_but_python_owns_canonical_semantics():
    raw, intake = _messy_case_and_intake()
    parser = DeterministicCaseParser()
    decision = IntakeRouter(parser).decide(raw, mode="auto", fast_available=True)
    assert decision.use_fast_model is True

    canonical = IntakeCanonicalizer(parser).build(raw, intake)
    assert canonical.ticket_id == "TEST-MESSY-001"
    assert [x.requirement_id for x in canonical.requirements] == ["REQ-401"]
    assert canonical.requirements[0].raw_source_text.startswith("REQ-401")
    req_transition = next(x for x in canonical.evidence_inventory if x.signal_name == "FunctionRequest" and x.signal_value == "ACTIVE")
    status_transition = next(x for x in canonical.evidence_inventory if x.signal_name == "FunctionStatus" and x.signal_value == "ACTIVE")
    assert req_transition.observation_type.value == "TRANSITION"
    assert req_transition.transition_from == "INACTIVE"
    assert status_transition.observation_type.value == "TRANSITION"
    assert status_transition.clock_id == "TRACE_B"


def test_v060_fast_intake_rejects_hallucinated_requirement_span():
    raw = "Ticket says no formal requirement text is included."
    intake = IntakeNormalization(requirements=IntakeRequirementSection(
        availability=SourceAvailability.PRESENT,
        items=[IntakeRequirement(
            requirement_id="REQ-999",
            requirement_text="Function shall activate.",
            source_span="REQ-999 Function shall activate.",
        )],
    ))
    canonical = IntakeCanonicalizer(DeterministicCaseParser()).build(raw, intake)
    assert canonical.requirements == []
    assert any("Rejected unsupported source_span" in note for note in canonical.parser_notes)


def test_v060_pipeline_uses_fast_intake_then_primary_on_messy_case():
    raw, intake = _messy_case_and_intake()
    canonical = IntakeCanonicalizer(DeterministicCaseParser()).build(raw, intake)
    trigger = next(x for x in canonical.evidence_inventory if x.signal_name == "FunctionRequest" and x.signal_value == "ACTIVE")
    response = next(x for x in canonical.evidence_inventory if x.signal_name == "FunctionStatus" and x.signal_value == "ACTIVE")
    req = RequirementAnalysis(
        requirement_id="REQ-401",
        requirement_text=canonical.requirements[0].requirement_text,
        faithful_meaning="When FunctionRequest becomes ACTIVE, FunctionStatus must become ACTIVE within 500 ms.",
        relevance="This requirement defines FunctionStatus activation timing.",
        normative_type=NormativeType.MANDATORY,
        applicability=Applicability.APPLICABLE,
        applicability_evidence_ids=[trigger.id],
        trigger="FunctionRequest becomes ACTIVE",
        required_behavior="FunctionStatus shall become ACTIVE",
        timing_constraint="within 500 ms",
        evaluation_evidence_ids=[response.id],
        evaluation_sufficiency=Sufficiency.INSUFFICIENT,
        missing_evaluation_evidence=[EvidenceNeed(
            element=RequirementElementType.RESPONSE,
            description="Complete transition-event coverage from the trigger through the 500 ms deadline is required to exclude an earlier omitted response transition.",
        )],
    )
    primary_reasoning = SemanticReasoning(affected_functionality="Function X", requirements=[req])
    primary = FakeStructuredClient(chat=[primary_reasoning], name="primary-27b")
    intake_client = FakeStructuredClient(repair=[intake], name="fast-4b")
    result = RCAPipeline(
        primary,
        intake_client=intake_client,
        fast_intake_enabled=True,
        fast_intake_mode="auto",
        max_repair_passes=0,
    ).run(raw)
    assert intake_client.repair_calls == 1
    assert primary.chat_calls == 1
    assert result.intake_normalization is not None
    assert result.canonical_case.requirements[0].requirement_id == "REQ-401"
    assert any(x.model_role == "FAST_SOURCE_AVAILABILITY" for x in result.attempts)


def test_v060_final_4b_review_can_patch_relevance_but_python_keeps_authoritative_verdicts():
    raw = (Path(__file__).resolve().parent.parent / "examples" / "TEST-001.txt").read_text(encoding="utf-8")
    semantic = make_test001()
    semantic.requirements[1].evaluation_evidence_ids = ["EVID-REPORTED-001"]
    primary_reasoning = SemanticReasoning(
        affected_functionality=semantic.affected_functionality,
        requirements=semantic.requirements,
        historical_tickets=[], diagnostic_evidence_ids=[], hypotheses=[], case_validity_needs=[],
    )
    review = LinguisticReviewResponse(
        findings=[LinguisticReviewFinding(
            code="WORDING_FACT_MISMATCH", requirement_id="REQ-002", field="relevance",
            message="Current wording can be made more explicit about the unresolved timing verdict.",
        )],
        relevance_patches=[RelevanceWordingPatch(
            requirement_id="REQ-002",
            relevance="REQ-002 defines the required activation response and timing constraint; the current evidence is relevant but does not establish a timing verdict.",
        )],
    )
    primary = FakeStructuredClient(chat=[primary_reasoning], name="primary-27b")
    review_client = FakeStructuredClient(repair=[review], name="fast-4b")
    result = RCAPipeline(
        primary,
        final_review_client=review_client,
        fast_final_review_enabled=True,
        max_repair_passes=0,
    ).run(raw)
    assert review_client.repair_calls == 1
    assert result.final_linguistic_review is not None
    req2 = next(x for x in result.validated.requirement_results if x.analysis.requirement_id == "REQ-002")
    assert req2.evaluation_status.value == "NOT EVALUABLE"
    assert "does not establish a timing verdict" in req2.analysis.relevance
    assert any(x.model_role == "FAST_FINAL_REVIEW" for x in result.attempts)


def _tc5_style_validated(relevance: str = "The visible 700 ms gap proves the 500 ms timing requirement was violated."):
    from rca_app.models import EvidenceClass, EvidenceItem, ObservationType, SemanticAnalysis
    from rca_app.validator import DeterministicValidator

    trigger = EvidenceItem(
        id="T",
        evidence_class=EvidenceClass.DIRECT_OBSERVATION,
        text="30.000 s FunctionRequest = ACTIVE",
        source="Direct Observations / Trace",
        timestamped=True,
        timestamp_seconds=30.0,
        event_coverage_complete=False,
        clock_id="TRACE_B",
        signal_name="FunctionRequest",
        signal_value="ACTIVE",
        observation_type=ObservationType.TRANSITION,
        transition_from="INACTIVE",
        transition_to="ACTIVE",
    )
    response = EvidenceItem(
        id="R",
        evidence_class=EvidenceClass.DIRECT_OBSERVATION,
        text="30.700 s FunctionStatus = ACTIVE",
        source="Direct Observations / Trace",
        timestamped=True,
        timestamp_seconds=30.7,
        event_coverage_complete=False,
        clock_id="TRACE_B",
        signal_name="FunctionStatus",
        signal_value="ACTIVE",
        observation_type=ObservationType.TRANSITION,
        transition_from="INACTIVE",
        transition_to="ACTIVE",
    )
    semantic = SemanticAnalysis(
        affected_functionality="Function X activation timing",
        evidence_inventory=[trigger, response],
        requirements=[RequirementAnalysis(
            requirement_id="REQ-401",
            requirement_text="When FunctionRequest becomes ACTIVE, FunctionStatus shall become ACTIVE within 500 ms.",
            faithful_meaning="FunctionRequest activation requires FunctionStatus activation within 500 ms.",
            relevance=relevance,
            normative_type=NormativeType.MANDATORY,
            applicability=Applicability.APPLICABLE,
            applicability_evidence_ids=["T"],
            trigger="FunctionRequest becomes ACTIVE",
            required_behavior="FunctionStatus shall become ACTIVE",
            timing_constraint="within 500 ms",
            evaluation_evidence_ids=["R"],
            evaluation_sufficiency=Sufficiency.INSUFFICIENT,
            missing_evaluation_evidence=[EvidenceNeed(
                element=RequirementElementType.RESPONSE,
                description="Complete transition-event coverage is required to exclude an earlier omitted response transition.",
            )],
        )],
    )
    return DeterministicValidator().normalize_and_validate(semantic)


def test_v060_tc5_final_wording_requests_only_remaining_event_coverage():
    validated = _tc5_style_validated(
        "The timing constraint cannot be evaluated without trigger/response timing and sufficient window coverage."
    )
    rr = validated.requirement_results[0]
    assert rr.evaluation_status.value == "NOT EVALUABLE"
    assert rr.timing_fact is None
    rel = rr.analysis.relevance.lower()
    assert "same clock" in rel
    assert "700 ms" in rel
    assert "500 ms" in rel
    assert "complete transition-event coverage" in rel
    assert "without trigger/response timing" not in rel
    assert len(validated.compliance_evidence) == 1
    next_need = validated.compliance_evidence[0].lower()
    assert "complete transition-event coverage" in next_need
    assert "earlier omitted" in next_need
    assert "observe the response/state" not in next_need
    assert "alignable timebase" not in next_need


def test_v060_unsafe_4b_relevance_patch_is_rewritten_by_python_final_gate():
    from rca_app.review import LinguisticReviewGate
    from rca_app.validator import DeterministicValidator

    validated = _tc5_style_validated("Timing remains unevaluable because event coverage is incomplete.")
    review = LinguisticReviewResponse(relevance_patches=[RelevanceWordingPatch(
        requirement_id="REQ-401",
        relevance="The observed 700 ms response definitively violates the 500 ms requirement.",
    )])
    from rca_app.models import CanonicalCase, RequirementSource
    canonical = CanonicalCase(
        ticket_id="TEST-005",
        title="Late activation",
        description="coverage incomplete",
        evidence_inventory=list(validated.semantic.evidence_inventory),
        requirements=[RequirementSource(
            requirement_id="REQ-401",
            requirement_text="When FunctionRequest becomes ACTIVE, FunctionStatus shall become ACTIVE within 500 ms.",
        )],
    )
    # Revalidate using the same authoritative semantic evidence. The review gate
    # may accept the field mechanically, but Python must normalize any wording
    # that contradicts the frozen timing semantics before it can become final.
    gated, accepted, rejected = LinguisticReviewGate.apply(
        validated, review, canonical, DeterministicValidator()
    )
    assert accepted == ["REQ-401"]
    assert rejected == []
    rr = gated.requirement_results[0]
    assert rr.evaluation_status.value == "NOT EVALUABLE"
    assert rr.timing_fact is None
    assert "definitively violates" not in rr.analysis.relevance.lower()
    assert "complete transition-event coverage" in rr.analysis.relevance.lower()
