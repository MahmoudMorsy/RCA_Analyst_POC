from pathlib import Path

from rca_app.case_parser import DeterministicCaseParser
from rca_app.models import EvidenceClass


def test_test001_source_boundaries_are_deterministic():
    path = Path(__file__).resolve().parent.parent / "examples" / "TEST-001.txt"
    case = DeterministicCaseParser().parse(path.read_text(encoding="utf-8"))
    by_source = {e.source: e for e in case.evidence_inventory}

    assert by_source["Reported Test Result"].evidence_class == EvidenceClass.REPORTED_OBSERVATION
    assert by_source["Reported Test Result"].text == "FunctionStatus did not become ACTIVE."
    assert by_source["Ticket Description"].evidence_class == EvidenceClass.CURRENT_TICKET
    assert by_source["Ticket Description"].text == "The user activates Function X, but the function remains inactive."
    assert len([e for e in case.evidence_inventory if e.evidence_class == EvidenceClass.TEST_INSTRUCTION]) == 4
    assert [r.requirement_id for r in case.requirements] == ["REQ-001", "REQ-002", "REQ-003"]
    assert case.historical_text == ""
    assert case.diagnostics_text == ""


def test_v040_test002_direct_observations_are_atomized():
    path = Path(__file__).resolve().parent.parent / "examples" / "TEST-002.txt"
    case = DeterministicCaseParser().parse(path.read_text(encoding="utf-8"))
    direct = [e for e in case.evidence_inventory if e.evidence_class == EvidenceClass.DIRECT_OBSERVATION and e.source == "Direct Observations / Trace"]

    assert len(direct) == 4
    by_signal = {e.signal_name: e for e in direct}
    assert by_signal["IgnitionState"].signal_value == "ON"
    assert by_signal["FunctionStatus"].signal_value == "INACTIVE"
    assert by_signal["WarningIndicator"].signal_value == "OFF"
    assert by_signal["AvailabilityStatus"].signal_value == "AVAILABLE"
    assert by_signal["AvailabilityStatus"].coverage_complete is True
    assert by_signal["IgnitionState"].coverage_complete is False


def test_v043_timestamp_clock_event_coverage_and_interval_state_are_parsed():
    from rca_app.models import ObservationType

    path = Path(__file__).resolve().parent.parent / "examples" / "TEST-003-timing-template.txt"
    case = DeterministicCaseParser().parse(path.read_text(encoding="utf-8"))
    direct = [e for e in case.evidence_inventory if e.evidence_class == EvidenceClass.DIRECT_OBSERVATION and e.source == "Direct Observations / Trace"]

    assert len(direct) == 8
    assert all(e.clock_id == "TRACE_A" for e in direct)
    assert all(e.event_coverage_complete for e in direct)
    # Explicit event completeness is intentionally distinct from the legacy/generic coverage flag.
    assert all(not e.coverage_complete for e in direct if e.observation_type != ObservationType.INTERVAL_STATE)

    availability = next(e for e in direct if e.signal_name == "AvailabilityStatus")
    trigger = next(e for e in direct if e.signal_name == "FunctionRequest" and e.observation_type == ObservationType.TRANSITION)
    response = next(e for e in direct if e.signal_name == "FunctionStatus" and e.observation_type == ObservationType.TRANSITION)

    assert availability.observation_type == ObservationType.INTERVAL_STATE
    assert availability.coverage_complete is True
    assert availability.timestamped is False
    assert trigger.signal_value == "ACTIVE"
    assert trigger.timestamp_seconds == 10.1
    assert trigger.observation_type == ObservationType.TRANSITION
    assert response.timestamp_seconds == 10.65


def test_v043_legacy_generic_coverage_does_not_claim_event_completeness():
    text = """CURRENT TRACE / DIRECT OBSERVATIONS
Clock ID: TRACE_A
Coverage Complete: true
10.100 s FunctionRequest transitioned to ACTIVE
10.650 s FunctionStatus transitioned to ACTIVE
"""
    items = DeterministicCaseParser()._parse_direct_observations(text.split("CURRENT TRACE / DIRECT OBSERVATIONS", 1)[1])
    assert items
    assert all(e.coverage_complete for e in items)
    assert all(not e.event_coverage_complete for e in items)


def test_v043_direct_observation_types_distinguish_samples_transitions_and_intervals():
    from rca_app.models import ObservationType

    path = Path(__file__).resolve().parent.parent / "examples" / "TEST-003.txt"
    case = DeterministicCaseParser().parse(path.read_text(encoding="utf-8"))
    direct = [e for e in case.evidence_inventory if e.evidence_class == EvidenceClass.DIRECT_OBSERVATION]

    trigger = next(e for e in direct if e.signal_name == "FunctionRequest" and e.observation_type == ObservationType.TRANSITION)
    response = next(e for e in direct if e.signal_name == "FunctionStatus" and e.observation_type == ObservationType.TRANSITION)
    samples = [e for e in direct if e.signal_name == "FunctionStatus" and e.observation_type == ObservationType.STATE_SAMPLE]

    assert trigger.observation_type == ObservationType.TRANSITION
    assert trigger.transition_to == "ACTIVE"
    assert trigger.timestamp_seconds == 10.1
    assert response.observation_type == ObservationType.TRANSITION
    assert response.transition_to == "ACTIVE"
    assert response.timestamp_seconds == 10.65
    assert len(samples) == 3

    test2 = Path(__file__).resolve().parent.parent / "examples" / "TEST-002.txt"
    case2 = DeterministicCaseParser().parse(test2.read_text(encoding="utf-8"))
    avail = next(e for e in case2.evidence_inventory if e.signal_name == "AvailabilityStatus")
    assert avail.observation_type == ObservationType.INTERVAL_STATE
