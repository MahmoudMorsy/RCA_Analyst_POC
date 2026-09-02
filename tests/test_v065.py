from __future__ import annotations

import json
from pathlib import Path

from rca_app.config import AppConfig
from rca_app.formatter import FinalReportFormatter
from rca_app.lmstudio_client import LMStudioError, StructuredResponse
from rca_app.models import (
    ApiStats,
    EvidenceClass,
    EvidenceItem,
    HypothesisAnalysis,
    HypothesisSupportBasis,
    LinguisticReviewResponse,
    SemanticReasoning,
)
from rca_app.pipeline import RCAPipeline
from rca_app.validator import DeterministicValidator
from tests.test_v060 import FakeStructuredClient, _tc5_style_validated
from tests.test_validator import make_test001


def test_v065_final_review_defaults_are_nonthinking_auto():
    cfg = AppConfig()
    assert cfg.fast_final_review_reasoning_effort == "provider_default"
    assert cfg.fast_final_review_thinking_mode == "off"
    assert cfg.fast_final_review_transport == "auto"


def test_v065_builds_manual_nonthinking_fallback_only_for_structured_chat_failure():
    from rca_app.lmstudio_client import LMStudioClient

    primary = LMStudioClient("http://127.0.0.1:1234/v1", "primary")
    review = LMStudioClient(
        "http://127.0.0.1:1234/v1",
        "qwen3.5-4b",
        temperature=0.0,
        reasoning_effort="low",
        max_tokens=1200,
        thinking_mode="provider_default",
        transport="openai-chat",
    )
    pipe = RCAPipeline(primary, final_review_client=review, fast_final_review_enabled=True)
    err = LMStudioError(
        "LM Studio returned an invalid structured response after one bounded retry: assistant content is empty",
        transport="openai-chat",
        reasoning_content="long reasoning",
    )
    fallback = pipe._build_nonthinking_final_review_fallback(err)
    assert fallback is not None
    assert fallback.thinking_mode == "off"
    assert fallback.transport == "qwen35-manual"
    assert fallback.reasoning_effort == "provider_default"

    network = LMStudioError("LM Studio request failed: connection reset", transport="openai-chat")
    assert pipe._build_nonthinking_final_review_fallback(network) is None


def _tc5_with_hypothesis(independent_mechanism_evidence: bool = False):
    validated = _tc5_style_validated(
        "The observed 700 ms interval is relevant, but the timing verdict remains unevaluable because complete transition-event coverage is unavailable."
    )
    semantic = validated.semantic.model_copy(deep=True)
    support = ["T", "R"]
    if independent_mechanism_evidence:
        semantic.evidence_inventory.append(EvidenceItem(
            id="D",
            evidence_class=EvidenceClass.DIRECT_OBSERVATION,
            text="DTC U1123 communication fault present after failure",
            source="Current BZD / Diagnostics",
        ))
        support.append("D")
    semantic.hypotheses = [HypothesisAnalysis(
        hypothesis="FunctionStatus response is delayed beyond the 500 ms requirement.",
        support_basis=HypothesisSupportBasis.CURRENT_CASE_MECHANISM_MATCH,
        supporting_evidence_ids=support,
        weakening_evidence_ids=[],
        source_references=list(support),
        confidence="LOW",
    )]
    return DeterministicValidator().normalize_and_validate(semantic)


def test_v065_tc5_unresolved_compliance_hypothesis_is_removed():
    validated = _tc5_with_hypothesis(False)
    assert validated.requirement_results[0].evaluation_status.value == "NOT EVALUABLE"
    assert validated.requirement_results[0].timing_fact is None
    assert validated.hypotheses == []
    assert validated.semantic.hypotheses == []
    assert any(x.code == "UNRESOLVED_COMPLIANCE_HYPOTHESIS_REMOVED" for x in validated.issues)


def test_v065_independent_mechanism_evidence_can_keep_hypothesis_candidate():
    validated = _tc5_with_hypothesis(True)
    assert len(validated.hypotheses) == 1
    assert "D" in validated.hypotheses[0].supporting_evidence_ids
    assert not any(x.code == "UNRESOLVED_COMPLIANCE_HYPOTHESIS_REMOVED" for x in validated.issues)


def test_v065_formatter_does_not_double_terminal_hypothesis_punctuation():
    validated = _tc5_with_hypothesis(True)
    report = FinalReportFormatter().format(validated)
    assert "requirement.." not in report
    assert "requirement.." not in report.lower()
    assert "**Supported hypotheses:** FunctionStatus response is delayed beyond the 500 ms requirement." in report


def test_v065_pipeline_recovers_failed_chat_review_via_manual_fallback(monkeypatch):
    raw = (Path(__file__).resolve().parent.parent / "examples" / "TEST-001.txt").read_text(encoding="utf-8")
    semantic = make_test001()
    primary_reasoning = SemanticReasoning(
        affected_functionality=semantic.affected_functionality,
        requirements=semantic.requirements,
        historical_tickets=[], diagnostic_evidence_ids=[], hypotheses=[], case_validity_needs=[],
    )
    primary = FakeStructuredClient(chat=[primary_reasoning], name="primary-27b")

    class FailingReviewClient:
        base_url = "http://127.0.0.1:1234/v1"
        model = "qwen3.5-4b"
        temperature = 0.0
        reasoning_effort = "low"
        max_tokens = 1200
        timeout_seconds = 60
        api_token = ""
        thinking_mode = "provider_default"
        transport = "openai-chat"

        def resolve_transport(self):
            return "openai-chat"

        def structured_repair(self, **kwargs):
            raise LMStudioError(
                "LM Studio returned an invalid structured response after one bounded retry: assistant content is empty",
                transport="openai-chat",
                reasoning_content="reasoning only",
                stats=ApiStats(elapsed_seconds=1.0, model=self.model),
            )

    class FallbackClient:
        def __init__(self, **kwargs):
            self.kwargs = kwargs

        def structured_repair(self, **kwargs):
            obj = LinguisticReviewResponse()
            return StructuredResponse(
                parsed=obj,
                raw_json=json.dumps(obj.model_dump(mode="json")),
                stats=ApiStats(elapsed_seconds=0.1, model="qwen3.5-4b"),
                transport="qwen35-manual",
            )

    monkeypatch.setattr("rca_app.pipeline.LMStudioClient", FallbackClient)
    result = RCAPipeline(
        primary,
        final_review_client=FailingReviewClient(),
        fast_final_review_enabled=True,
        max_repair_passes=0,
    ).run(raw)
    assert result.final_linguistic_review is not None
    roles = [x.model_role for x in result.attempts]
    assert "FAST_FINAL_REVIEW" in roles
    assert "FAST_FINAL_REVIEW_FALLBACK" in roles


def test_v065_version_history_records_064_to_065_transition():
    root = Path(__file__).resolve().parent.parent
    history = (root / "VERSION_HISTORY.md").read_text(encoding="utf-8")
    # This assertion is populated by the release packaging step and prevents
    # future versions from silently dropping the cumulative history file.
    assert "## v0.6.4 → v0.6.5" in history
