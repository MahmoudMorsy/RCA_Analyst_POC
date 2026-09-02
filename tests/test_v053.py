import json

import pytest

from rca_app.case_parser import DeterministicCaseParser
from rca_app.formatter import FinalReportFormatter
from rca_app.lmstudio_client import LMStudioClient, LMStudioError
from rca_app.models import (
    ApiStats,
    Applicability,
    CanonicalCase,
    EvaluationStatus,
    EvidenceClass,
    EvidenceItem,
    EvidenceNeed,
    NormativeType,
    ObservationType,
    RequirementAnalysis,
    RequirementElementType,
    RequirementPatchResponse,
    RequirementSource,
    SemanticAnalysis,
    SemanticReasoning,
    Sufficiency,
)
from rca_app.pipeline import PipelineValidationError, RCAPipeline
from rca_app.validator import DeterministicValidator


def _obs(eid, signal, value, kind=ObservationType.STATE_SAMPLE, *, group="", coverage=False, timestamp=None, clock=""):
    return EvidenceItem(
        id=eid,
        evidence_class=EvidenceClass.DIRECT_OBSERVATION,
        text=f"{signal} = {value}",
        source="Direct Observations / Trace",
        signal_name=signal,
        signal_value=value,
        observation_type=kind,
        observation_group=group,
        coverage_complete=coverage,
        timestamped=timestamp is not None,
        timestamp_seconds=timestamp,
        clock_id=clock,
    )


def test_v053_assignment_only_changed_value_is_canonical_transition_without_rewriting_raw_text():
    text = """CURRENT TRACE / DIRECT OBSERVATIONS
Clock ID: TRACE_X
Event Coverage Complete: true
9.900 s FunctionRequest = INACTIVE
10.100 s FunctionRequest = ACTIVE
10.100 s FunctionStatus = INACTIVE
10.650 s FunctionStatus = ACTIVE
"""
    items = DeterministicCaseParser()._parse_direct_observations(
        text.split("CURRENT TRACE / DIRECT OBSERVATIONS", 1)[1]
    )
    req = [x for x in items if x.signal_name == "FunctionRequest"]
    status = [x for x in items if x.signal_name == "FunctionStatus"]
    assert req[0].observation_type == ObservationType.STATE_SAMPLE
    assert req[1].observation_type == ObservationType.TRANSITION
    assert req[1].transition_from == "INACTIVE"
    assert req[1].transition_to == "ACTIVE"
    assert req[1].text == "10.100 s FunctionRequest = ACTIVE"
    assert "transition" not in req[1].text.lower()
    assert status[1].observation_type == ObservationType.TRANSITION
    assert status[1].transition_from == "INACTIVE"
    assert status[1].transition_to == "ACTIVE"


def test_v053_first_assignment_and_repeated_same_value_remain_state_samples():
    text = """CURRENT TRACE / DIRECT OBSERVATIONS
Clock ID: TRACE_X
Event Coverage Complete: true
10.000 s FunctionRequest = ACTIVE
10.100 s FunctionRequest = ACTIVE
10.200 s FunctionRequest = ACTIVE
"""
    items = DeterministicCaseParser()._parse_direct_observations(
        text.split("CURRENT TRACE / DIRECT OBSERVATIONS", 1)[1]
    )
    assert all(x.observation_type == ObservationType.STATE_SAMPLE for x in items)
    assert all(not x.transition_to for x in items)


def test_v053_prohibitive_point_counterexample_proves_violation_without_interval_response():
    app = _obs("E-APP", "GearPosition", "D", ObservationType.INTERVAL_STATE, group="DRIVE", coverage=True)
    counterexample = _obs("E-CAM", "ParkingCamera", "ACTIVE", group="DRIVE")
    semantic = SemanticAnalysis(
        affected_functionality="Parking camera",
        evidence_inventory=[app, counterexample],
        requirements=[RequirementAnalysis(
            requirement_id="REQ-501",
            requirement_text="If GearPosition is D, ParkingCamera shall not be ACTIVE.",
            faithful_meaning="While GearPosition is D, ParkingCamera must not be ACTIVE.",
            relevance="Directly governs camera state in Drive.",
            normative_type=NormativeType.PROHIBITIVE,
            applicability=Applicability.APPLICABLE,
            applicability_evidence_ids=["E-APP"],
            applicability_condition="GearPosition is D",
            required_behavior="ParkingCamera shall not be ACTIVE",
            observation_interval_requirement="Camera must stay outside ACTIVE while GearPosition is D",
            evaluation_evidence_ids=["E-CAM"],
            evaluation_sufficiency=Sufficiency.INSUFFICIENT,
        )],
    )
    validated = DeterministicValidator().normalize_and_validate(semantic)
    rr = validated.requirement_results[0]
    assert rr.analysis.evaluation_sufficiency == Sufficiency.SUFFICIENT_NONCONFORMANCE
    assert rr.evaluation_status == EvaluationStatus.VIOLATED
    assert not rr.analysis.missing_evaluation_evidence
    assert any(x.code.startswith("PERSISTENCE_POINT_COUNTEREXAMPLE_") for x in validated.issues)


def test_v053_positive_simple_point_condition_promotes_applicability_but_not_persistence_conformance():
    avail1 = _obs("A1", "AvailabilityStatus", "AVAILABLE", timestamp=10.0, clock="TRACE")
    avail2 = _obs("A2", "AvailabilityStatus", "AVAILABLE", timestamp=10.1, clock="TRACE")
    off1 = _obs("W1", "WarningIndicator", "OFF", timestamp=10.0, clock="TRACE")
    off2 = _obs("W2", "WarningIndicator", "OFF", timestamp=10.1, clock="TRACE")
    semantic = SemanticAnalysis(
        affected_functionality="Warning persistence",
        evidence_inventory=[avail1, avail2, off1, off2],
        requirements=[RequirementAnalysis(
            requirement_id="REQ-1501",
            requirement_text="If AvailabilityStatus is AVAILABLE, WarningIndicator shall remain OFF.",
            faithful_meaning="While AVAILABLE, WarningIndicator must remain OFF.",
            relevance="Direct warning persistence rule.",
            normative_type=NormativeType.MANDATORY,
            applicability=Applicability.UNKNOWN,
            applicability_evidence_ids=["A1", "A2"],
            applicability_condition="AvailabilityStatus is AVAILABLE",
            required_behavior="WarningIndicator shall remain OFF",
            observation_interval_requirement="WarningIndicator must remain OFF while AvailabilityStatus is AVAILABLE",
            evaluation_evidence_ids=["W1", "W2"],
            evaluation_sufficiency=Sufficiency.INSUFFICIENT,
        )],
    )
    validated = DeterministicValidator().normalize_and_validate(semantic)
    rr = validated.requirement_results[0]
    assert rr.analysis.applicability == Applicability.APPLICABLE
    assert rr.evaluation_status == EvaluationStatus.NOT_EVALUABLE
    assert any(x.code == "POSITIVE_APPLICABILITY_OBSERVED" for x in validated.issues)


def test_v053_dotted_variant_applicability_signal_is_removed_from_response_bucket():
    variant = _obs("V", "ActiveVariant", "A", ObservationType.INTERVAL_STATE, coverage=True)
    req = _obs("R", "VariantA.FunctionRequest", "ACTIVE", group="P")
    status = _obs("S", "VariantA.FunctionStatus", "INACTIVE", group="P")
    semantic = SemanticAnalysis(
        affected_functionality="Variant A",
        evidence_inventory=[variant, req, status],
        requirements=[RequirementAnalysis(
            requirement_id="REQ-2001",
            requirement_text="If ActiveVariant is A and VariantA.FunctionRequest is ACTIVE, VariantA.FunctionStatus shall be ACTIVE.",
            faithful_meaning="For variant A, an active request requires active status.",
            relevance="Variant A obligation.",
            normative_type=NormativeType.MANDATORY,
            applicability=Applicability.APPLICABLE,
            applicability_evidence_ids=["V", "R"],
            applicability_condition="ActiveVariant is A and VariantA.FunctionRequest is ACTIVE",
            required_behavior="VariantA.FunctionStatus shall be ACTIVE",
            evaluation_evidence_ids=["R", "S"],
            evaluation_sufficiency=Sufficiency.SUFFICIENT_NONCONFORMANCE,
        )],
    )
    validated = DeterministicValidator().normalize_and_validate(semantic)
    rr = validated.requirement_results[0]
    assert rr.evaluation_status == EvaluationStatus.VIOLATED
    assert "R" not in rr.analysis.evaluation_evidence_ids
    assert "S" in rr.analysis.evaluation_evidence_ids


def test_v053_supplied_historical_ticket_cannot_silently_disappear():
    canonical = CanonicalCase(
        ticket_id="HIST-CASE",
        evidence_inventory=[EvidenceItem(
            id="EVID-HIST-001",
            evidence_class=EvidenceClass.HISTORICAL_EVIDENCE,
            text="HIST-180-A\nSymptom: x\nFinal analysis: y",
            source="Historical Tickets",
        )],
        requirements=[RequirementSource(requirement_id="REQ-1", requirement_text="If A is ON, B shall be ON.")],
        historical_text="HIST-180-A\nSymptom: x\nFinal analysis: y",
    )
    semantic = SemanticAnalysis(
        affected_functionality="x",
        evidence_inventory=canonical.evidence_inventory,
        requirements=[RequirementAnalysis(
            requirement_id="REQ-1",
            requirement_text="If A is ON, B shall be ON.",
            faithful_meaning="If A is ON, B must be ON.",
            relevance="x",
            normative_type=NormativeType.MANDATORY,
            applicability=Applicability.UNKNOWN,
            applicability_evidence_ids=[],
            applicability_condition="A is ON",
            required_behavior="B shall be ON",
            evaluation_sufficiency=Sufficiency.INSUFFICIENT,
        )],
        historical_tickets=[],
    )
    validated = DeterministicValidator().normalize_and_validate(semantic, canonical_case=canonical)
    assert any(x.code == "HISTORICAL_SOURCE_UNACCOUNTED" and x.severity.value == "ERROR" for x in validated.issues)


def test_v053_explicit_parent_relationship_cannot_silently_disappear():
    text = (
        "Relationship: REQ-2 is a child of REQ-1 and applies only when the applicability condition of REQ-1 is established.\n"
        "When Request becomes ACTIVE, Status shall become ACTIVE within 1000 ms."
    )
    canonical = CanonicalCase(
        requirements=[RequirementSource(requirement_id="REQ-2", requirement_text=text)],
    )
    semantic = SemanticAnalysis(
        affected_functionality="x",
        evidence_inventory=[],
        requirements=[RequirementAnalysis(
            requirement_id="REQ-2",
            requirement_text=text,
            faithful_meaning="Within parent scope, request triggers status.",
            relevance="x",
            normative_type=NormativeType.MANDATORY,
            applicability=Applicability.UNKNOWN,
            applicability_evidence_ids=[],
            trigger="Request becomes ACTIVE",
            required_behavior="Status shall become ACTIVE",
            timing_constraint="within 1000 ms",
            explicit_relationships=[],
            evaluation_sufficiency=Sufficiency.INSUFFICIENT,
        )],
    )
    validated = DeterministicValidator().normalize_and_validate(semantic, canonical_case=canonical)
    assert any(x.code == "EXPLICIT_RELATIONSHIP_UNACCOUNTED" for x in validated.issues)


def test_v053_conflicting_reported_timing_is_explicitly_surfaced():
    trigger = _obs("T", "FunctionRequest", "ACTIVE", ObservationType.TRANSITION, timestamp=20.0, clock="TRACE")
    trigger.transition_from = "INACTIVE"
    trigger.transition_to = "ACTIVE"
    trigger.event_coverage_complete = True
    response = _obs("R", "FunctionStatus", "ACTIVE", ObservationType.TRANSITION, timestamp=20.65, clock="TRACE")
    response.transition_from = "INACTIVE"
    response.transition_to = "ACTIVE"
    response.event_coverage_complete = True
    reported = EvidenceItem(
        id="REP",
        evidence_class=EvidenceClass.REPORTED_OBSERVATION,
        text="FunctionStatus became ACTIVE within approximately 250 ms and the step was marked passed.",
        source="Reported Test Result",
    )
    semantic = SemanticAnalysis(
        affected_functionality="timing",
        evidence_inventory=[trigger, response, reported],
        requirements=[RequirementAnalysis(
            requirement_id="REQ-1601",
            requirement_text="When FunctionRequest becomes ACTIVE, FunctionStatus shall become ACTIVE within 300 ms.",
            faithful_meaning="Trigger to response must be within 300 ms.",
            relevance="timing",
            normative_type=NormativeType.MANDATORY,
            applicability=Applicability.APPLICABLE,
            applicability_evidence_ids=["T"],
            trigger="FunctionRequest becomes ACTIVE",
            required_behavior="FunctionStatus shall become ACTIVE",
            timing_constraint="within 300 ms",
            evaluation_evidence_ids=["R", "REP"],
            evaluation_sufficiency=Sufficiency.SUFFICIENT_NONCONFORMANCE,
        )],
    )
    validated = DeterministicValidator().normalize_and_validate(semantic)
    assert validated.requirement_results[0].evaluation_status == EvaluationStatus.VIOLATED
    assert validated.evidence_conflicts
    assert validated.evidence_conflicts[0].reported_evidence_ids == ["REP"]
    report = FinalReportFormatter().format(validated)
    assert "Evidence conflicts" in report
    assert "deterministic direct transition timing" in report


def test_v053_diagnostic_temporal_summary_distinguishes_new_preexisting_and_after_only():
    before_after = EvidenceItem(
        id="D1", evidence_class=EvidenceClass.DIRECT_OBSERVATION, source="Current BZD / Diagnostics",
        text=("Before test:\n- DTC C101 Low voltage was present.\n- DTC U2200 Communication timeout was not present.\n"
              "After failure:\n- DTC C101 Low voltage was still present.\n- DTC U2200 Communication timeout was present."),
    )
    lines = FinalReportFormatter._diagnostic_temporal_summary([before_after])
    assert any("C101" in x and "pre-existing / unchanged" in x for x in lines)
    assert any("U2200" in x and "newly present" in x for x in lines)

    after_only = EvidenceItem(
        id="D2", evidence_class=EvidenceClass.DIRECT_OBSERVATION, source="Current BZD / Diagnostics",
        text="After failure only:\n- DTC U3000 Sensor communication fault was present.\nNo pre-test BZD snapshot was captured.",
    )
    lines = FinalReportFormatter._diagnostic_temporal_summary([after_only])
    assert any("U3000" in x and "cannot be classified as newly introduced" in x for x in lines)


class _FakeHTTPResponse:
    def __init__(self, data, status_code=200):
        self._data = data
        self.status_code = status_code
        self.text = json.dumps(data)

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")

    def json(self):
        return self._data


def test_v053_primary_empty_final_content_gets_one_bounded_structured_retry(monkeypatch):
    calls = []
    valid = {"patches": [{"requirement_id": "REQ-1", "patch": {"faithful_meaning": "correct"}}]}
    responses = [
        _FakeHTTPResponse({
            "choices": [{"message": {"content": "", "reasoning_content": "long reasoning"}, "finish_reason": "length"}],
            "usage": {"prompt_tokens": 10, "completion_tokens": 100, "total_tokens": 110, "completion_tokens_details": {"reasoning_tokens": 100}},
        }),
        _FakeHTTPResponse({
            "choices": [{"message": {"content": json.dumps(valid), "reasoning_content": "short"}, "finish_reason": "stop"}],
            "usage": {"prompt_tokens": 11, "completion_tokens": 20, "total_tokens": 31, "completion_tokens_details": {"reasoning_tokens": 5}},
        }),
    ]

    def fake_post(*args, **kwargs):
        calls.append(kwargs["json"])
        return responses.pop(0)

    monkeypatch.setattr("rca_app.lmstudio_client.requests.post", fake_post)
    client = LMStudioClient("http://localhost:1234/v1", "primary", max_tokens=1000, reasoning_effort="medium")
    out = client.structured_chat("sys", "user", RequirementPatchResponse, "patch_schema")
    assert len(calls) == 2
    assert out.parsed.patches[0].patch.faithful_meaning == "correct"
    assert out.stats.retries == 1
    assert out.retry_diagnostics
    assert calls[1]["max_tokens"] > calls[0]["max_tokens"]
    assert calls[1].get("reasoning_effort") == "low"


def test_v053_fast_manual_malformed_json_gets_one_bounded_retry(monkeypatch):
    calls = []
    malformed = '{"patches":[{"requirement_id":"REQ-1","patch":{"faithful_meaning":"x"}}]'
    valid = {"patches": [{"requirement_id": "REQ-1", "patch": {"faithful_meaning": "x"}}]}
    responses = [
        _FakeHTTPResponse({"choices": [{"text": malformed, "finish_reason": "stop"}], "usage": {"prompt_tokens": 5, "completion_tokens": 5, "total_tokens": 10}}),
        _FakeHTTPResponse({"choices": [{"text": json.dumps(valid), "finish_reason": "stop"}], "usage": {"prompt_tokens": 5, "completion_tokens": 5, "total_tokens": 10}}),
    ]

    def fake_post(*args, **kwargs):
        calls.append(kwargs["json"])
        return responses.pop(0)

    monkeypatch.setattr("rca_app.lmstudio_client.requests.post", fake_post)
    client = LMStudioClient("http://localhost:1234/v1", "qwen3.5-4b", max_tokens=1400, thinking_mode="off", transport="auto")
    out = client.structured_repair("sys", "user", RequirementPatchResponse, "patch_schema")
    assert len(calls) == 2
    assert out.parsed.patches[0].patch.faithful_meaning == "x"
    assert out.stats.retries == 1
    assert out.transport == "qwen35-manual"
    assert out.retry_diagnostics


def test_v053_primary_failure_persists_canonical_case_and_failed_attempt():
    class FailingClient:
        def structured_chat(self, **kwargs):
            raise LMStudioError(
                "empty final content",
                raw_json="{raw api}",
                reasoning_content="reasoning was produced",
                stats=ApiStats(elapsed_seconds=12.3, model="primary", completion_tokens=1000),
                finish_reason="length",
                transport="openai-chat",
                retry_diagnostics=["attempt 1 empty", "attempt 2 empty"],
            )

    raw = """CURRENT TICKET
Ticket ID: FAIL-1
Title: Failure persistence
Description: Test.
TEST INFORMATION
Test Steps:
1. Do X.
Reported Test Result:
Failed.
SYSTEM REQUIREMENTS
REQ-1
If A is ON, B shall be ON.
CURRENT TRACE / DIRECT OBSERVATIONS
A = ON
B = OFF
TASK
Analyze.
"""
    with pytest.raises(PipelineValidationError) as exc_info:
        RCAPipeline(FailingClient(), max_repair_passes=1).run(raw)
    exc = exc_info.value
    assert exc.canonical_case is not None
    assert exc.canonical_case.ticket_id == "FAIL-1"
    assert len(exc.attempts) == 1
    assert exc.attempts[0].reasoning_content == "reasoning was produced"
    assert exc.attempts[0].finish_reason == "length"
    assert exc.attempts[0].retry_diagnostics == ["attempt 1 empty", "attempt 2 empty"]
    assert exc.stats and exc.stats[0].elapsed_seconds == 12.3


def test_v053_trigger_not_applicable_from_lone_target_state_is_corrected_to_unknown():
    request = _obs("REQ", "FunctionRequest", "ACTIVE", timestamp=50.0, clock="TRACE_D")
    request.event_coverage_complete = True
    response = _obs("RES", "FunctionStatus", "ACTIVE", ObservationType.TRANSITION, timestamp=50.1, clock="TRACE_D")
    response.transition_from = "INACTIVE"
    response.transition_to = "ACTIVE"
    response.event_coverage_complete = True
    semantic = SemanticAnalysis(
        affected_functionality="activation",
        evidence_inventory=[request, response],
        requirements=[RequirementAnalysis(
            requirement_id="REQ-1001",
            requirement_text="When FunctionRequest becomes ACTIVE, FunctionStatus shall become ACTIVE within 500 ms.",
            faithful_meaning="When the request transitions to ACTIVE, status must transition within 500 ms.",
            relevance="Activation timing.",
            normative_type=NormativeType.MANDATORY,
            applicability=Applicability.NOT_APPLICABLE,
            applicability_evidence_ids=["REQ"],
            trigger="FunctionRequest becomes ACTIVE",
            required_behavior="FunctionStatus shall become ACTIVE",
            timing_constraint="within 500 ms",
            evaluation_sufficiency=Sufficiency.NOT_REQUIRED,
        )],
    )
    validated = DeterministicValidator().normalize_and_validate(semantic)
    rr = validated.requirement_results[0]
    assert rr.analysis.applicability == Applicability.UNKNOWN
    assert rr.evaluation_status == EvaluationStatus.NOT_EVALUABLE
    assert rr.timing_fact is None
    assert any(x.code == "TRIGGER_NOT_APPLICABLE_SCOPE_NOT_ESTABLISHED" for x in validated.issues)


def test_v053_correlated_point_state_match_proves_nonpersistent_condition_conformance():
    lost = _obs("LOST", "DriverSeatControllerCommunication", "LOST", timestamp=70.1, clock="TRACE_SEAT")
    inactive = _obs("INACTIVE", "DriverSeatHeatingStatus", "INACTIVE", timestamp=70.1, clock="TRACE_SEAT")
    semantic = SemanticAnalysis(
        affected_functionality="seat heating",
        evidence_inventory=[lost, inactive],
        requirements=[RequirementAnalysis(
            requirement_id="REQ-2105",
            requirement_text="If DriverSeatControllerCommunication is LOST, DriverSeatHeatingStatus shall be INACTIVE.",
            faithful_meaning="At an observed point where communication is LOST, the heating status must be INACTIVE.",
            relevance="Communication/state relation.",
            normative_type=NormativeType.MANDATORY,
            applicability=Applicability.APPLICABLE,
            applicability_evidence_ids=["LOST"],
            applicability_condition="DriverSeatControllerCommunication is LOST",
            required_behavior="DriverSeatHeatingStatus shall be INACTIVE",
            evaluation_evidence_ids=["INACTIVE"],
            evaluation_sufficiency=Sufficiency.INSUFFICIENT,
            missing_evaluation_evidence=[EvidenceNeed(element=RequirementElementType.OBSERVATION_INTERVAL, description="Need persistence")],
        )],
    )
    validated = DeterministicValidator().normalize_and_validate(semantic)
    rr = validated.requirement_results[0]
    assert rr.analysis.evaluation_sufficiency == Sufficiency.SUFFICIENT_CONFORMANCE
    assert rr.evaluation_status == EvaluationStatus.SATISFIED
    assert rr.analysis.missing_evaluation_evidence == []
    assert any(x.code == "CORRELATED_POINT_STATE_CONFORMANCE_DERIVED" for x in validated.issues)


def test_v053_correlated_transition_condition_and_state_sample_prove_point_conformance():
    active = _obs("ACTIVE", "DriverSeatHeatingStatus", "ACTIVE", ObservationType.TRANSITION, timestamp=70.8, clock="TRACE_SEAT")
    active.transition_from = "INACTIVE"
    active.transition_to = "ACTIVE"
    indicator = _obs("IND", "DriverSeatHeatingIndicator", "ON", timestamp=70.8, clock="TRACE_SEAT")
    semantic = SemanticAnalysis(
        affected_functionality="indicator",
        evidence_inventory=[active, indicator],
        requirements=[RequirementAnalysis(
            requirement_id="REQ-2108",
            requirement_text="If DriverSeatHeatingStatus is ACTIVE, DriverSeatHeatingIndicator shall be ON.",
            faithful_meaning="If heating status is ACTIVE, indicator must be ON.",
            relevance="Indicator relation.",
            normative_type=NormativeType.MANDATORY,
            applicability=Applicability.APPLICABLE,
            applicability_evidence_ids=["ACTIVE"],
            applicability_condition="DriverSeatHeatingStatus is ACTIVE",
            required_behavior="DriverSeatHeatingIndicator shall be ON",
            evaluation_evidence_ids=["IND"],
            evaluation_sufficiency=Sufficiency.INSUFFICIENT,
        )],
    )
    validated = DeterministicValidator().normalize_and_validate(semantic)
    rr = validated.requirement_results[0]
    assert rr.evaluation_status == EvaluationStatus.SATISFIED


def test_v053_late_incomplete_event_coverage_needs_only_event_coverage_not_fast_repair():
    trigger = _obs("T", "FunctionRequest", "ACTIVE", ObservationType.TRANSITION, timestamp=30.0, clock="TRACE_B")
    trigger.transition_from = "INACTIVE"
    trigger.transition_to = "ACTIVE"
    response = _obs("R", "FunctionStatus", "ACTIVE", ObservationType.TRANSITION, timestamp=30.7, clock="TRACE_B")
    response.transition_from = "INACTIVE"
    response.transition_to = "ACTIVE"
    semantic = SemanticAnalysis(
        affected_functionality="timing",
        evidence_inventory=[trigger, response],
        requirements=[RequirementAnalysis(
            requirement_id="REQ-401",
            requirement_text="When FunctionRequest becomes ACTIVE, FunctionStatus shall become ACTIVE within 500 ms.",
            faithful_meaning="Request transition requires status transition within 500 ms.",
            relevance="Timing.",
            normative_type=NormativeType.MANDATORY,
            applicability=Applicability.APPLICABLE,
            applicability_evidence_ids=["T"],
            trigger="FunctionRequest becomes ACTIVE",
            required_behavior="FunctionStatus shall become ACTIVE",
            timing_constraint="within 500 ms",
            evaluation_evidence_ids=["T", "R"],
            evaluation_sufficiency=Sufficiency.INSUFFICIENT,
            missing_evaluation_evidence=[EvidenceNeed(element=RequirementElementType.APPLICABILITY, description="already established")],
        )],
    )
    validated = DeterministicValidator().normalize_and_validate(semantic)
    rr = validated.requirement_results[0]
    assert rr.evaluation_status == EvaluationStatus.NOT_EVALUABLE
    assert rr.timing_fact is None
    assert len(rr.analysis.missing_evaluation_evidence) == 1
    assert rr.analysis.missing_evaluation_evidence[0].element == RequirementElementType.RESPONSE
    assert "event coverage" in rr.analysis.missing_evaluation_evidence[0].description.lower() or "transition-event coverage" in rr.analysis.missing_evaluation_evidence[0].description.lower()
    assert not any(x.code == "APPLICABILITY_NEED_IN_EVALUATION_BUCKET" and x.severity.value == "ERROR" for x in validated.issues)
    assert not [x for x in validated.issues if x.severity.value == "ERROR"]


def test_v053_primary_structured_retry_preserves_both_transport_attempts(monkeypatch):
    responses = [
        _FakeHTTPResponse({
            "choices": [{"message": {"content": "", "reasoning_content": "first reasoning"}, "finish_reason": "length"}],
            "usage": {"prompt_tokens": 10, "completion_tokens": 100, "total_tokens": 110, "completion_tokens_details": {"reasoning_tokens": 95}},
        }),
        _FakeHTTPResponse({
            "choices": [{"message": {"content": '{"patches":[]}', "reasoning_content": "second reasoning"}, "finish_reason": "stop"}],
            "usage": {"prompt_tokens": 11, "completion_tokens": 20, "total_tokens": 31, "completion_tokens_details": {"reasoning_tokens": 5}},
        }),
    ]
    monkeypatch.setattr("rca_app.lmstudio_client.requests.post", lambda *a, **k: responses.pop(0))
    out = LMStudioClient("http://localhost:1234/v1", "primary", max_tokens=6144).structured_chat(
        "sys", "user", RequirementPatchResponse, "schema"
    )
    assert len(out.structured_attempts) == 2
    assert out.structured_attempts[0].reasoning_content == "first reasoning"
    assert out.structured_attempts[0].finish_reason == "length"
    assert out.structured_attempts[0].retry_reason
    assert out.structured_attempts[0].stats.completion_tokens == 100
    assert out.structured_attempts[1].reasoning_content == "second reasoning"


def test_v053_fast_second_malformed_retry_can_only_recover_missing_terminal_delimiters(monkeypatch):
    calls = []
    # Both calls are malformed by a missing final top-level closing brace. The
    # first must still trigger the bounded retry; only the second may receive the
    # mechanical terminal-delimiter recovery.
    malformed = '{"patches":[{"requirement_id":"REQ-1","patch":{"faithful_meaning":"x"}}]'
    responses = [
        _FakeHTTPResponse({"choices": [{"text": malformed, "finish_reason": "stop"}], "usage": {"prompt_tokens": 5, "completion_tokens": 5, "total_tokens": 10}}),
        _FakeHTTPResponse({"choices": [{"text": malformed, "finish_reason": "stop"}], "usage": {"prompt_tokens": 5, "completion_tokens": 5, "total_tokens": 10}}),
    ]
    def fake_post(*args, **kwargs):
        calls.append(kwargs["json"])
        return responses.pop(0)
    monkeypatch.setattr("rca_app.lmstudio_client.requests.post", fake_post)
    client = LMStudioClient("http://localhost:1234/v1", "qwen3.5-4b", max_tokens=1400, thinking_mode="off", transport="auto")
    out = client.structured_repair("sys", "user", RequirementPatchResponse, "patch_schema")
    assert len(calls) == 2
    assert out.parsed.patches[0].patch.faithful_meaning == "x"
    assert out.raw_schema_valid is False
    assert any("terminal JSON delimiters" in x["before"] for x in out.tier0_adjustments)
    assert len(out.structured_attempts) == 2
    assert out.structured_attempts[0].error
    assert out.structured_attempts[1].retry_reason


def test_v053_late_incomplete_event_coverage_has_no_repairable_validator_error():
    trigger = _obs("T", "FunctionRequest", "ACTIVE", ObservationType.TRANSITION, timestamp=30.0, clock="TRACE_B")
    trigger.transition_from = "INACTIVE"
    trigger.transition_to = "ACTIVE"
    response = _obs("R", "FunctionStatus", "ACTIVE", ObservationType.TRANSITION, timestamp=30.7, clock="TRACE_B")
    response.transition_from = "INACTIVE"
    response.transition_to = "ACTIVE"
    semantic = SemanticAnalysis(
        affected_functionality="timing",
        evidence_inventory=[trigger, response],
        requirements=[RequirementAnalysis(
            requirement_id="REQ-401",
            requirement_text="When FunctionRequest becomes ACTIVE, FunctionStatus shall become ACTIVE within 500 ms.",
            faithful_meaning="Request transition requires status transition within 500 ms.",
            relevance="Timing.",
            normative_type=NormativeType.MANDATORY,
            applicability=Applicability.APPLICABLE,
            applicability_evidence_ids=["T"],
            trigger="FunctionRequest becomes ACTIVE",
            required_behavior="FunctionStatus shall become ACTIVE",
            timing_constraint="within 500 ms",
            evaluation_evidence_ids=["R"],
            evaluation_sufficiency=Sufficiency.INSUFFICIENT,
            missing_evaluation_evidence=[EvidenceNeed(element=RequirementElementType.APPLICABILITY, description="already established")],
        )],
    )
    validated = DeterministicValidator().normalize_and_validate(semantic)
    assert validated.requirement_results[0].evaluation_status == EvaluationStatus.NOT_EVALUABLE
    assert not [x for x in validated.issues if x.severity.value == "ERROR"]


def test_v053_trigger_not_applicable_is_preserved_with_explicit_parent_scope_interval_evidence():
    parent_scope = _obs("SCOPE", "VehicleState", "DRIVING", ObservationType.INTERVAL_STATE, clock="TRACE_REL")
    parent_scope.coverage_complete = True
    trigger = _obs("TRIG", "RemoteUnlockRequest", "ACTIVE", ObservationType.TRANSITION, timestamp=30.0, clock="TRACE_REL")
    trigger.transition_from = "INACTIVE"
    trigger.transition_to = "ACTIVE"
    semantic = SemanticAnalysis(
        affected_functionality="remote access",
        evidence_inventory=[parent_scope, trigger],
        requirements=[RequirementAnalysis(
            requirement_id="REQ-1902",
            requirement_text="Relationship: REQ-1902 is a child of REQ-1901 and applies only when the applicability condition of REQ-1901 is established. When RemoteUnlockRequest becomes ACTIVE, DoorLockStatus shall become UNLOCKED within 1000 ms.",
            faithful_meaning="The child timing rule applies only inside its parent scope.",
            relevance="Parent scope is absent.",
            normative_type=NormativeType.MANDATORY,
            applicability=Applicability.NOT_APPLICABLE,
            applicability_evidence_ids=["SCOPE"],
            trigger="RemoteUnlockRequest becomes ACTIVE",
            required_behavior="DoorLockStatus shall become UNLOCKED",
            timing_constraint="within 1000 ms",
            explicit_relationships=["REQ-1902 is a child of REQ-1901 and applies only when REQ-1901 applicability is established."],
            evaluation_sufficiency=Sufficiency.NOT_REQUIRED,
        )],
    )
    validated = DeterministicValidator().normalize_and_validate(semantic)
    rr = validated.requirement_results[0]
    assert rr.analysis.applicability == Applicability.NOT_APPLICABLE
    assert rr.evaluation_status == EvaluationStatus.NO_COMPLIANCE_VERDICT
    assert not any(x.code == "TRIGGER_NOT_APPLICABLE_SCOPE_NOT_ESTABLISHED" for x in validated.issues)


def test_v053_missing_persistence_decomposition_repairs_deterministically():
    from rca_app.models import ValidationIssue, ValidationSeverity
    from rca_app.repair import DeterministicRepairEngine, RepairRouter

    semantic = SemanticAnalysis(
        affected_functionality="tailgate",
        evidence_inventory=[],
        requirements=[RequirementAnalysis(
            requirement_id="REQ-P",
            requirement_text="If VehicleSpeed is above 0, TailgateRequest shall not be accepted.",
            faithful_meaning="Moving vehicle prohibits tailgate request acceptance.",
            relevance="Prohibitive rule.",
            normative_type=NormativeType.PROHIBITIVE,
            applicability=Applicability.UNKNOWN,
            applicability_evidence_ids=[],
            applicability_condition="VehicleSpeed is above 0",
            required_behavior="TailgateRequest shall not be accepted",
            observation_interval_requirement="",
            evaluation_sufficiency=Sufficiency.INSUFFICIENT,
        )],
    )
    issue = ValidationIssue(
        code="MISSING_PERSISTENCE_DECOMPOSITION",
        severity=ValidationSeverity.ERROR,
        path="semantic.requirements[0].observation_interval_requirement",
        message="missing",
    )
    task = RepairRouter().build_plan(semantic, [issue], fast_model_available=True)[0]
    assert task.route.value == "DETERMINISTIC"
    repaired, changed = DeterministicRepairEngine().apply_task(semantic, task)
    assert "observation_interval_requirement" in changed
    assert "throughout" in repaired.requirements[0].observation_interval_requirement.lower()


def test_v055_same_clock_timing_does_not_request_timebase_alignment():
    trigger = _obs("T", "FunctionRequest", "ACTIVE", ObservationType.TRANSITION, timestamp=30.0, clock="TRACE_B")
    trigger.transition_from = "INACTIVE"
    trigger.transition_to = "ACTIVE"
    response = _obs("R", "FunctionStatus", "ACTIVE", ObservationType.TRANSITION, timestamp=30.7, clock="TRACE_B")
    response.transition_from = "INACTIVE"
    response.transition_to = "ACTIVE"
    semantic = SemanticAnalysis(
        affected_functionality="timing",
        evidence_inventory=[trigger, response],
        requirements=[RequirementAnalysis(
            requirement_id="REQ-401",
            requirement_text="When FunctionRequest becomes ACTIVE, FunctionStatus shall become ACTIVE within 500 ms.",
            faithful_meaning="Request transition requires status transition within 500 ms.",
            relevance="Timing.",
            normative_type=NormativeType.MANDATORY,
            applicability=Applicability.APPLICABLE,
            applicability_evidence_ids=["T"],
            trigger="FunctionRequest becomes ACTIVE",
            required_behavior="FunctionStatus shall become ACTIVE",
            timing_constraint="within 500 ms",
            evaluation_evidence_ids=["R"],
            evaluation_sufficiency=Sufficiency.INSUFFICIENT,
            missing_evaluation_evidence=[
                EvidenceNeed(
                    element=RequirementElementType.RESPONSE,
                    description="Complete transition-event coverage on the aligned trace from trigger through the deadline.",
                )
            ],
        )],
    )
    validated = DeterministicValidator().normalize_and_validate(semantic)
    assert validated.requirement_results[0].evaluation_status == EvaluationStatus.NOT_EVALUABLE
    assert not any("alignable timebase" in item.lower() for item in validated.compliance_evidence)
    assert not any(item.startswith("REQ-401 — Timing") for item in validated.compliance_evidence)


def test_v055_different_timing_clocks_request_alignment_when_needed():
    trigger = _obs("T", "FunctionRequest", "ACTIVE", ObservationType.TRANSITION, timestamp=30.0, clock="CLOCK_A")
    trigger.transition_from = "INACTIVE"
    trigger.transition_to = "ACTIVE"
    response = _obs("R", "FunctionStatus", "ACTIVE", ObservationType.TRANSITION, timestamp=30.2, clock="CLOCK_B")
    response.transition_from = "INACTIVE"
    response.transition_to = "ACTIVE"
    semantic = SemanticAnalysis(
        affected_functionality="timing",
        evidence_inventory=[trigger, response],
        requirements=[RequirementAnalysis(
            requirement_id="REQ-CLOCK",
            requirement_text="When FunctionRequest becomes ACTIVE, FunctionStatus shall become ACTIVE within 500 ms.",
            faithful_meaning="Request transition requires status transition within 500 ms.",
            relevance="Timing.",
            normative_type=NormativeType.MANDATORY,
            applicability=Applicability.APPLICABLE,
            applicability_evidence_ids=["T"],
            trigger="FunctionRequest becomes ACTIVE",
            required_behavior="FunctionStatus shall become ACTIVE",
            timing_constraint="within 500 ms",
            evaluation_evidence_ids=["R"],
            evaluation_sufficiency=Sufficiency.INSUFFICIENT,
            missing_evaluation_evidence=[
                EvidenceNeed(element=RequirementElementType.TIMING, description="Need an alignable/common timebase between trigger and response clocks."),
            ],
        )],
    )
    validated = DeterministicValidator().normalize_and_validate(semantic)
    assert validated.requirement_results[0].evaluation_status == EvaluationStatus.NOT_EVALUABLE
    assert any(item.startswith("REQ-CLOCK — Timing") and "different clocks" in item for item in validated.compliance_evidence)
