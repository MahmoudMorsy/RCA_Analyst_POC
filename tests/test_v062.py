import json
from pathlib import Path

from rca_app.lmstudio_client import LMStudioClient, StructuredResponse
from rca_app.models import ApiStats, IntakeNormalization, SemanticReasoning
from rca_app.pipeline import RCAPipeline
from tests.test_v053 import _FakeHTTPResponse
from tests.test_validator import make_test001


def test_v062_manual_4b_rejects_yaml_with_embedded_json_and_retries_with_schema(monkeypatch):
    calls = []
    yaml_like = (
        'ticket_id: "TEST-005"\n'
        'requirements: [{"id":"REQ-401","text":"When FunctionRequest becomes ACTIVE, FunctionStatus shall become ACTIVE within 500 ms."}]\n'
    )
    req_span = 'REQ-401 When FunctionRequest becomes ACTIVE, FunctionStatus shall become ACTIVE within 500 ms.'
    valid = {
        "ticket_id": {"value": "TEST-005", "source_span": "TEST-005"},
        "title": {"value": "", "source_span": ""},
        "description": {"value": "", "source_span": ""},
        "test_steps": [],
        "reported_results": [],
        "requirements": {
            "availability": "PRESENT",
            "items": [{
                "requirement_id": "REQ-401",
                "requirement_text": "When FunctionRequest becomes ACTIVE, FunctionStatus shall become ACTIVE within 500 ms.",
                "source_span": req_span,
            }],
            "availability_statement": {"value": "", "source_span": ""},
        },
        "historical": {"availability": "NOT_MENTIONED", "blocks": [], "availability_statement": {"value": "", "source_span": ""}},
        "diagnostics": {"availability": "NOT_MENTIONED", "blocks": [], "availability_statement": {"value": "", "source_span": ""}},
        "trace": {"availability": "NOT_MENTIONED", "blocks": [], "availability_statement": {"value": "", "source_span": ""}},
        "user_instructions": [],
        "unclassified_spans": [],
        "notes": [],
    }
    responses = [
        _FakeHTTPResponse({"choices": [{"text": yaml_like, "finish_reason": "stop"}], "usage": {"prompt_tokens": 10, "completion_tokens": 20, "total_tokens": 30}}),
        _FakeHTTPResponse({"choices": [{"text": json.dumps(valid), "finish_reason": "stop"}], "usage": {"prompt_tokens": 12, "completion_tokens": 30, "total_tokens": 42}}),
    ]

    def fake_post(*args, **kwargs):
        calls.append(kwargs["json"])
        return responses.pop(0)

    monkeypatch.setattr("rca_app.lmstudio_client.requests.post", fake_post)
    client = LMStudioClient(
        "http://localhost:1234/v1", "qwen3.5-4b", max_tokens=2200,
        thinking_mode="off", transport="qwen35-manual",
    )
    out = client.structured_repair("intake sys", "intake user", IntakeNormalization, "intake")

    assert len(calls) == 2
    assert out.stats.retries == 1
    assert out.parsed.requirements.items[0].requirement_id == "REQ-401"
    assert out.retry_diagnostics
    # Manual /v1/completions has no response_format support, so the schema must
    # be explicitly embedded into the prompt sent to the 4B model.
    assert 'STRICT STRUCTURED OUTPUT CONTRACT' in calls[0]["prompt"]
    assert 'source_span' in calls[0]["prompt"]
    assert 'Do not use YAML' in calls[0]["prompt"]


class _FakeClient:
    def __init__(self, *, chat=None, repair=None, name="fake"):
        self.chat = list(chat or [])
        self.repair = list(repair or [])
        self.chat_calls = 0
        self.repair_calls = 0
        self.model = name

    def structured_chat(self, **kwargs):
        obj = self.chat[self.chat_calls]
        self.chat_calls += 1
        return StructuredResponse(
            parsed=obj, raw_json=json.dumps(obj.model_dump(mode="json")),
            stats=ApiStats(elapsed_seconds=0.01, model=self.model), transport="openai-chat",
        )

    def structured_repair(self, **kwargs):
        obj = self.repair[self.repair_calls]
        self.repair_calls += 1
        return StructuredResponse(
            parsed=obj, raw_json=json.dumps(obj.model_dump(mode="json")),
            stats=ApiStats(elapsed_seconds=0.01, model=self.model), transport="qwen35-manual",
        )


def test_v062_forced_intake_cannot_erase_valid_deterministic_requirements():
    raw = (Path(__file__).resolve().parent.parent / "examples" / "TEST-001.txt").read_text(encoding="utf-8")
    semantic = make_test001()
    primary_reasoning = SemanticReasoning(
        affected_functionality=semantic.affected_functionality,
        requirements=semantic.requirements,
        historical_tickets=[], diagnostic_evidence_ids=[], hypotheses=[], case_validity_needs=[],
    )
    primary = _FakeClient(chat=[primary_reasoning], name="primary")
    # Structurally valid but useless intake output. v0.6.1 allowed this to erase
    # the valid deterministic preview and then failed with no requirements.
    intake = _FakeClient(repair=[IntakeNormalization()], name="fast")

    trace_events = []
    result = RCAPipeline(
        primary,
        intake_client=intake,
        fast_intake_enabled=True,
        fast_intake_mode="always",
        max_repair_passes=0,
    ).run(raw, trace=trace_events.append)

    assert intake.repair_calls == 1
    assert primary.chat_calls == 1
    assert result.canonical_case.requirements
    assert any("FAST_INTAKE_FALLBACK" in note for note in result.canonical_case.parser_notes)
    stage = next(x for x in trace_events if x["stage_id"] == "04_content_classification" and x["status"] == "attention")
    assert 'fallback_to_deterministic' in stage["output_text"]
    assert 'true' in stage["output_text"].lower()
