import json
from pathlib import Path

from rca_app.lmstudio_client import StructuredResponse
from rca_app.models import ApiStats, RequirementRepairResponse, SemanticReasoning
from rca_app.pipeline import RCAPipeline
from tests.test_validator import make_test001


class FakeClient:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = 0

    def structured_chat(self, **kwargs):
        obj = self.responses[self.calls]
        self.calls += 1
        return StructuredResponse(
            parsed=obj,
            raw_json=json.dumps(obj.model_dump(mode="json")),
            stats=ApiStats(elapsed_seconds=0.01, model="fake"),
        )


def _reasoning_from_good():
    s = make_test001()
    s.requirements[1].evaluation_evidence_ids = ["EVID-REPORTED-001"]
    return SemanticReasoning(
        affected_functionality=s.affected_functionality,
        requirements=s.requirements,
        historical_tickets=[],
        diagnostic_evidence_ids=[],
        hypotheses=[],
        case_validity_needs=[],
    )


def test_pipeline_repairs_bad_decomposition_before_formatter():
    good = _reasoning_from_good()
    bad = good.model_copy(deep=True)
    bad.requirements[1].trigger = ""
    bad.requirements[1].required_behavior = ""
    bad.requirements[1].timing_constraint = ""
    bad.requirements[1].evaluation_evidence_ids = []
    bad.requirements[2].applicability_condition = ""
    bad.requirements[2].required_behavior = ""
    bad.requirements[2].observation_interval_requirement = ""

    repair = RequirementRepairResponse(requirements=[good.requirements[1], good.requirements[2]])
    client = FakeClient([bad, repair])
    pipeline = RCAPipeline(client, max_repair_passes=1)
    case_text = (Path(__file__).resolve().parent.parent / "examples" / "TEST-001.txt").read_text(encoding="utf-8")
    result = pipeline.run(case_text)

    assert result.repair_performed is True
    assert client.calls == 2
    assert len(result.attempts) == 2
    assert result.attempts[0].stage == "phase_a_chunk_1"
    assert result.attempts[1].stage.startswith("primary_batch_repair_r1_a")
    assert result.attempts[0].validation_issues
    assert not pipeline.validator.critical_issues(result.validated)
    assert "FunctionStatus did not become ACTIVE." in result.final_report
    section10 = result.final_report.split("# 10. Minimum Next Evidence Required", 1)[1].split("# 11.", 1)[0]
    assert "FunctionRequest" in section10
    assert "FunctionStatus" in section10
    assert "AvailabilityStatus" in section10


def test_v060_pipeline_trace_exposes_multi_model_stage_inputs_and_outputs():
    client = FakeClient([_reasoning_from_good()])
    pipeline = RCAPipeline(client, max_repair_passes=0)
    case_text = (Path(__file__).resolve().parent.parent / "examples" / "TEST-001.txt").read_text(encoding="utf-8")
    events = []
    result = pipeline.run(case_text, trace=lambda event: events.append(dict(event)))

    assert result.final_report
    ids = [x["stage_id"] for x in events]
    for required in [
        "01_user_input",
        "02_intake_routing",
        "03_source_availability",
        "04_content_classification",
        "05_canonicalization",
        "06_atomic_claims",
        "07_requirement_language",
        "08_phase_a_requirement_reasoning",
        "09_requirement_validation",
        "10_requirement_repair",
        "11_authoritative_compliance",
        "12_phase_b_rca_synthesis",
        "13_rca_validation_repair",
        "14_hypothesis_review",
        "15_final_wording_review",
        "16_python_final_gate",
        "17_report_formatter",
        "18_final_output",
    ]:
        assert required in ids

    intake = next(x for x in events if x["stage_id"] == "03_source_availability")
    assert intake["status"] == "skipped"
    canonical_done = next(x for x in events if x["stage_id"] == "05_canonicalization" and x["status"] == "complete")
    assert "TEST-001" in canonical_done["output_text"]
    primary_running = next(x for x in events if x["stage_id"] == "08_phase_a_chunk_1" and x["status"] == "running")
    assert "system_prompt" in primary_running["input_text"]
    primary_done = next(x for x in events if x["stage_id"] == "08_phase_a_chunk_1" and x["status"] == "complete")
    assert "structured_json" in primary_done["output_text"]
    final = next(x for x in events if x["stage_id"] == "18_final_output")
    assert "# 1. Affected Functionality" in final["output_text"]
